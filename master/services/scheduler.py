"""Scheduler for coordinating job execution across minions."""

import asyncio
import logging
from typing import Optional
from shared.domain.models import HashJob, WorkChunk, CrackResultPayload
from shared.domain.status import JobStatus
from shared.config.config import config
from shared.consts import ResultStatus, OutputStatus
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.minion_client import MinionClient
from master.services.chunk_manager import ChunkManager
from master.services.job_manager import JobManager

logger = logging.getLogger(__name__)


class Scheduler:
    """Scheduler for distributing work to minions."""
    
    def __init__(
        self,
        registry: MinionRegistry,
        client: MinionClient,
        job_manager: JobManager,
        output_file: str,
    ):
        self.registry = registry
        self.client = client
        self.job_manager = job_manager
        self.output_file = output_file
        self.chunk_manager = ChunkManager()
    
    async def process_job(self, job: HashJob) -> None:
        """
        Process a single job to completion.
        
        Handles:
        - Cache hits (immediate output)
        - Chunk scheduling
        - FOUND/NOT_FOUND/ERROR/CANCELLED results
        - Cancellation broadcast
        - Output writing
        """
        # Check if already done (cache hit)
        if job.status == JobStatus.DONE and job.password_found:
            self._write_output(job.hash_value, job.password_found)
            return
        
        # Process chunks
        while not job.is_complete():
            # Get next pending chunk
            chunk = self.chunk_manager.get_next_pending_chunk(job)
            if chunk is None:
                # Check if all chunks are done
                if self.chunk_manager.check_all_chunks_done(job):
                    # All chunks done, check if any failed
                    if self.chunk_manager.check_any_chunk_failed(job):
                        self.job_manager.mark_job_failed(job)
                        self._write_output(job.hash_value, None, failed=True)
                    elif job.password_found is None:
                        # All done, none found
                        self.job_manager.mark_job_done(job, password=None)
                        self._write_output(job.hash_value, None, failed=False)
                    # If password_found is set, job is already done
                else:
                    # Wait a bit before checking again
                    await asyncio.sleep(0.1)
                continue
            
            # Get available minion
            minion_url = self.registry.pick_next()
            if minion_url is None:
                # No available minions: wait and retry (do NOT fail)
                logger.debug(f"No available minions, waiting {config.NO_MINION_WAIT_TIME}s")
                await asyncio.sleep(config.NO_MINION_WAIT_TIME)
                continue
            
            # Mark chunk in progress
            self.chunk_manager.mark_chunk_in_progress(chunk, minion_url)
            
            # Send request
            result = await self.client.send_crack_request(
                minion_url=minion_url,
                chunk=chunk,
                hash_value=job.hash_value,
                hash_type=job.hash_type,
                password_scheme=job.scheme,
                job_id=job.id,
            )
            
            # Handle result
            await self._handle_result(job, chunk, result)
    
    async def _handle_result(
        self,
        job: HashJob,
        chunk: WorkChunk,
        result: CrackResultPayload,
    ) -> None:
        """Handle result from minion."""
        if result.status == ResultStatus.FOUND:
            is_first_found = self.chunk_manager.handle_found_result(
                job, chunk, result.found_password
            )
            
            if is_first_found:
                # Mark job done
                self.job_manager.mark_job_done(job, password=result.found_password)
                
                # Write output
                self._write_output(job.hash_value, result.found_password)
                
                # Broadcast cancellation to all minions
                await self._broadcast_cancellation(job.id)
        
        elif result.status == ResultStatus.NOT_FOUND:
            self.chunk_manager.handle_not_found_result(job, chunk)
        
        elif result.status == ResultStatus.CANCELLED:
            self.chunk_manager.handle_cancelled_result(job, chunk)
        
        elif result.status == ResultStatus.ERROR:
            should_retry = self.chunk_manager.handle_error_result(
                job, chunk, result.last_index_processed
            )
            
            if not should_retry:
                # Max attempts exceeded
                if self.chunk_manager.check_any_chunk_failed(job):
                    self.job_manager.mark_job_failed(job)
                    self._write_output(job.hash_value, None, failed=True)
    
    async def _broadcast_cancellation(self, job_id: str) -> None:
        """Broadcast cancellation to all minions (best-effort)."""
        logger.info(f"Broadcasting cancellation for job {job_id} to all minions")
        tasks = [
            self.client.send_cancel_job(minion_url, job_id)
            for minion_url in self.registry.all_minions()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def _write_output(
        self,
        hash_value: str,
        password: Optional[str],
        failed: bool = False,
    ) -> None:
        """Write output line to stdout and file."""
        if failed:
            line = f"{hash_value} {OutputStatus.FAILED}"
        elif password:
            line = f"{hash_value} {password}"
        else:
            line = f"{hash_value} {OutputStatus.NOT_FOUND}"
        
        # Print to stdout
        print(line)
        
        # Append to file
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()  # Ensure data is written immediately
            logger.info(f"Wrote output: {line}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to write output to file {self.output_file}: {e}", exc_info=True)
            # Still print to stdout even if file write fails
        except Exception as e:
            logger.error(f"Unexpected error writing output: {e}", exc_info=True)

