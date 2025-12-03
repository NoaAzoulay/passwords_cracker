"""Main entry point for Pentera Distributed Password Cracker."""

import asyncio
import logging
import sys
import re
from pathlib import Path
from shared.config.config import config
from shared.consts import HashAlgorithm, HashDisplay
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


def load_hashes_from_file(filename: str) -> list[str]:
    """
    Load and validate MD5 hashes from file.
    
    Returns:
        List of valid, normalized (lowercase) hashes
    """
    valid_hashes = []
    
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
                    continue
                
                valid_hashes.append(hash_value)
    
    except FileNotFoundError:
        logger.error(f"Input file not found: {filename}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        sys.exit(1)
    
    return valid_hashes


async def main():
    """Main execution function."""
    # Get input file from command line
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Load hashes
    logger.info(f"Loading hashes from {input_file}")
    hashes = load_hashes_from_file(input_file)
    
    # Handle empty input
    if not hashes:
        print("No valid hashes found. Nothing to process.")
        # Truncate output file
        try:
            with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
                pass  # Truncate to empty
        except Exception as e:
            logger.error(f"Failed to truncate output file: {e}")
        sys.exit(0)
    
    logger.info(f"Loaded {len(hashes)} valid hashes")
    
    # Initialize output file (truncate on start)
    # Create output directory if it doesn't exist
    output_path = Path(config.OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
            pass  # Truncate to empty
    except Exception as e:
        logger.error(f"Failed to initialize output file: {e}")
        sys.exit(1)
    
    # Initialize components
    cache = CrackedCache()
    registry = MinionRegistry(config.MINION_URLS)
    client = MinionClient(registry)
    job_manager = JobManager(cache)
    scheduler = Scheduler(
        registry=registry,
        client=client,
        job_manager=job_manager,
        output_file=config.OUTPUT_FILE,
    )
    
    # Process each hash
    for hash_value in hashes:
        logger.info(f"Processing hash {hash_value[:HashDisplay.PREFIX_LENGTH]}...")
        
        # Create job
        job = job_manager.create_job(hash_value)
        
        # Process job
        await scheduler.process_job(job)
    
    # Cleanup
    await client.close()
    
    logger.info("All jobs completed")


if __name__ == "__main__":
    asyncio.run(main())



