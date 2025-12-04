"""Main entry point for Distributed Password Cracker."""

import asyncio
import json
import logging
import sys
import re
import uuid
from pathlib import Path
from shared.config.config import config
from shared.domain.consts import HashAlgorithm, HashDisplay, OutputStatus
from master.infrastructure.cache import CrackedCache
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.minion_client import MinionClient
from master.services.job_manager import JobManager
from master.services.scheduler import Scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


def validate_md5_hash(hash_value: str) -> bool:
    """Validate that hash is exactly 32 hex characters."""
    pattern = f"^[0-9a-f]{{{HashAlgorithm.MD5_LENGTH}}}$"
    return bool(re.match(pattern, hash_value.lower()))


def load_hashes_from_file(filename: str) -> tuple[list[str], list[str]]:
    """
    Load and validate MD5 hashes from file.
    
    Returns:
        Tuple of (valid_hashes, invalid_hashes) - both normalized (lowercase)
    """
    valid_hashes = []
    invalid_hashes = []
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Strip and normalize to lowercase
                hash_value = line.strip().lower()
                
                # Skip empty lines
                if not hash_value:
                    continue
                
                # Validate
                if not validate_md5_hash(hash_value):
                    logger.warning(f"Line {line_num}: Invalid MD5 hash format: {hash_value}")
                    invalid_hashes.append(hash_value)
                    continue
                
                valid_hashes.append(hash_value)
    
    except FileNotFoundError:
        logger.error(f"Input file not found: {filename}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        sys.exit(1)
    
    return valid_hashes, invalid_hashes


async def main():
    """Main execution function."""
    # Get input file from command line
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Initialize cache and clear it at startup to ensure fresh state for each run
    # This happens early so cache is always cleared, even if we exit early
    cache = CrackedCache()
    cache.clear()
    logger.info("Cache cleared at startup")
    
    # Load hashes
    logger.info(f"Loading hashes from {input_file}")
    valid_hashes, invalid_hashes = load_hashes_from_file(input_file)
    
    # Handle invalid hashes - write them to output immediately
    if invalid_hashes:
        logger.info(f"Found {len(invalid_hashes)} invalid hashes - will write as INVALID_INPUT")
        # Create output directory if it doesn't exist
        output_path = Path(config.OUTPUT_FILE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write invalid hashes to output
        output_data = {}
        for invalid_hash in invalid_hashes:
            job_id = str(uuid.uuid4())
            entry = {
                "cracked_password": None,
                "status": OutputStatus.INVALID_INPUT,
                "job_id": job_id
            }
            output_data[invalid_hash] = entry
            print(f"{invalid_hash} {OutputStatus.INVALID_INPUT} {job_id}")
        
        # Write to file
        try:
            with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write invalid hashes to output file: {e}")
    
    # Handle empty input
    if not valid_hashes and not invalid_hashes:
        print("No hashes found. Nothing to process.")
        # Truncate output file
        try:
            with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
                pass  # Truncate to empty
        except Exception as e:
            logger.error(f"Failed to truncate output file: {e}")
        sys.exit(0)
    
    if not valid_hashes:
        logger.info("No valid hashes to process (only invalid hashes found)")
        sys.exit(0)
    
    logger.info(f"Loaded {len(valid_hashes)} valid hashes")
    
    # Initialize output file (append if invalid hashes were written, otherwise truncate)
    # Create output directory if it doesn't exist
    output_path = Path(config.OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # If invalid hashes were written, we need to append to the file instead of truncating
    if not invalid_hashes:
        try:
            with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
                pass  # Truncate to empty
        except Exception as e:
            logger.error(f"Failed to initialize output file: {e}")
            sys.exit(1)
    
    # Initialize remaining components (cache already created and cleared above)
    registry = MinionRegistry(config.MINION_URLS)
    client = MinionClient(registry)
    job_manager = JobManager(cache)
    scheduler = Scheduler(
        registry=registry,
        client=client,
        job_manager=job_manager,
        output_file=config.OUTPUT_FILE,
    )
    
    # Process hashes in parallel with semaphore to limit concurrency
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
    logger.info(
        f"Processing {len(valid_hashes)} hashes with max {config.MAX_CONCURRENT_JOBS} "
        f"concurrent jobs"
    )
    
    async def process_single_hash(hash_value: str) -> None:
        """Process a single hash with semaphore-controlled concurrency."""
        async with sem:
            logger.info(f"Processing hash {hash_value[:HashDisplay.PREFIX_LENGTH]}...")
            
            # Create job
            job = job_manager.create_job(hash_value)
            
            # Process job
            await scheduler.process_job(job)
    
    # Launch all hash processing tasks concurrently
    tasks = [
        asyncio.create_task(process_single_hash(hash_value))
        for hash_value in valid_hashes
    ]
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks)
    
    # Cleanup
    await client.close()
    
    logger.info("All jobs completed")


if __name__ == "__main__":
    asyncio.run(main())
