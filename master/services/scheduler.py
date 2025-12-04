"""Scheduler for coordinating job execution across minions."""

import asyncio
import json
import logging
import os
from typing import Optional
from shared.domain.models import HashJob, WorkChunk, CrackResultPayload
from shared.domain.status import JobStatus
from shared.config.config import config
from shared.domain.consts import ResultStatus, OutputStatus, HashDisplay
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.minion_client import MinionClient
from master.services.chunk_manager import ChunkManager
from master.services.job_manager import JobManager

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Scheduler for distributing work to minions with true parallelism.
    
    Maintains a task pool limited by available minions, scheduling multiple
    chunks concurrently. Handles FOUND/NOT_FOUND/ERROR/CANCELLED results with
    proper retry logic and cancellation broadcasting.
    """
    
    def __init__(
        self,
        registry: MinionRegistry,
        client: MinionClient,
        job_manager: JobManager,
        output_file: str,
    ) -> None:
        """
        Initialize scheduler.
        """
        self.registry = registry
        self.client = client
        self.job_manager = job_manager
        self.output_file = output_file
        self.chunk_manager = ChunkManager()
        # Lock for atomic output file writes (protects against concurrent writes from parallel jobs)
        self.output_lock = asyncio.Lock()
    
    async def process_job(self, job: HashJob) -> None:
        """
        Process a single job to completion with true parallelism.
        
        Implements:
        - True parallel chunk scheduling (limited by available minions)
        - Task pool management (max pool size = number of available minions)
        - Immediate cancellation broadcast on FOUND (non-blocking)
        - Proper handling of FOUND/NOT_FOUND/ERROR/CANCELLED results
        """
        # Handle cache hit (job already done)
        if await self._handle_cache_hit(job):
            return
        
        # Track active tasks and job state
        active_tasks: set[asyncio.Task] = set()
        found_password: Optional[str] = None
        job_failed = False
        
        try:
            while not job.is_complete():
                # Handle password found
                if found_password:
                    await self._handle_password_found(job, found_password, active_tasks)
                    break
                
                # Check if job failed
                if job_failed:
                    break
                
                # Wait if no minions available
                if await self._wait_for_available_minions(job):
                    continue
                
                # Fill task pool with pending chunks
                await self._fill_task_pool(job, active_tasks)
                
                # Check job completion if no active tasks
                if not active_tasks:
                    job_failed = await self._check_job_completion(job)
                    continue
                
                # Wait for tasks to complete and process results
                done_tasks = await self._wait_for_task_completion(active_tasks)
                found_password, job_failed = await self._process_completed_tasks(
                    job, active_tasks, done_tasks, found_password, job_failed
                )
        
        finally:
            await self._cleanup_tasks(active_tasks)
    
    async def _handle_cache_hit(self, job: HashJob) -> bool:
        """
        Handle cache hit case (job already done).
        
        Returns:
            True if cache hit was handled, False otherwise.
        """
        if job.status == JobStatus.DONE and job.password_found:
            await self._write_output(
                hash_value=job.hash_value,
                password=job.password_found,
                job_id=job.id,
            )
            return True
        return False
    
    async def _handle_password_found(
        self,
        job: HashJob,
        password: str,
        active_tasks: set[asyncio.Task],
    ) -> None:
        """
        Handle password found: mark job done, write output, broadcast cancellation.
        """
        # Mark job done
        self.job_manager.mark_job_done(job, password=password)
        
        # Write output
        await self._write_output(
            hash_value=job.hash_value,
            password=password,
            job_id=job.id,
        )
        
        # Broadcast cancellation immediately (non-blocking)
        asyncio.create_task(self._broadcast_cancellation(job.id))
        
        # Cancel all pending tasks
        for task in active_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to finish (cancelled or completed)
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
    
    async def _wait_for_available_minions(self, job: HashJob) -> bool:
        """
        Wait if no minions are available.
        
        Returns:
            True if we waited (no minions available), False if minions are available.
        """
        available_minions = self.registry.get_available_minions()
        if len(available_minions) == 0:
            logger.debug(
                f"Job {job.id[:8]}...: No available minions, "
                f"waiting {config.NO_MINION_WAIT_TIME}s"
            )
            await asyncio.sleep(config.NO_MINION_WAIT_TIME)
            return True
        return False
    
    async def _fill_task_pool(
        self,
        job: HashJob,
        active_tasks: set[asyncio.Task],
    ) -> None:
        """
        Fill task pool with pending chunks up to available minion capacity.
        """
        available_minions = self.registry.get_available_minions()
        max_pool_size = len(available_minions)
        
        while len(active_tasks) < max_pool_size:
            # Get next pending chunk
            chunk = self.chunk_manager.get_next_pending_chunk(job)
            if chunk is None:
                # No more pending chunks
                break
            
            # Get available minion
            minion_url = self.registry.pick_next()
            if minion_url is None:
                # This shouldn't happen if get_available_minions() returned non-empty
                # But handle gracefully
                logger.warning(
                    f"Job {job.id[:8]}...: pick_next() returned None "
                    f"despite available minions, retrying..."
                )
                break  # Exit inner loop to check again
            
            # Mark chunk in progress
            self.chunk_manager.mark_chunk_in_progress(chunk, minion_url)
            
            # Create task for this chunk
            task = asyncio.create_task(
                self._process_chunk(job, chunk, minion_url)
            )
            active_tasks.add(task)
            
            logger.debug(
                f"Job {job.id[:8]}...: Scheduled chunk {chunk.id[:8]}... "
                f"to {minion_url} (active tasks: {len(active_tasks)})"
            )
    
    async def _check_job_completion(self, job: HashJob) -> bool:
        """
        Check if all chunks are done and handle job completion.
        
        Returns:
            True if job failed, False otherwise.
        """
        if not self.chunk_manager.check_all_chunks_done(job):
            # Not all chunks done, wait a bit
            await asyncio.sleep(0.1)
            return False
        
        # All chunks done
        if self.chunk_manager.check_any_chunk_failed(job):
            self.job_manager.mark_job_failed(job)
            await self._write_output(
                hash_value=job.hash_value,
                password=None,
                job_id=job.id,
                failed=True,
            )
            return True
        elif job.password_found is None:
            # All done, none found
            self.job_manager.mark_job_done(job, password=None)
            await self._write_output(
                hash_value=job.hash_value,
                password=None,
                job_id=job.id,
                failed=False,
            )
        
        return False
    
    async def _wait_for_task_completion(
        self,
        active_tasks: set[asyncio.Task],
    ) -> set[asyncio.Task]:
        """
        Wait for at least one task to complete.
        
        Returns:
            Set of completed tasks.
        """
        done, _ = await asyncio.wait(
            active_tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        return done
    
    async def _process_completed_tasks(
        self,
        job: HashJob,
        active_tasks: set[asyncio.Task],
        done_tasks: set[asyncio.Task],
        found_password: Optional[str],
        job_failed: bool,
    ) -> tuple[Optional[str], bool]:
        """
        Process completed tasks and handle their results.
        
        Returns:
            Tuple of (found_password, job_failed) updated after processing.
        """
        for task in done_tasks:
            active_tasks.remove(task)
            try:
                result = await task
                if result:
                    status, chunk, result_payload = result
                    found_password, job_failed = await self._handle_chunk_result(
                        job, status, chunk, result_payload, found_password, job_failed
                    )
            except asyncio.CancelledError:
                logger.debug(
                    f"Job {job.id[:8]}...: Task cancelled (password found)"
                )
            except Exception as e:
                logger.error(
                    f"Job {job.id[:8]}...: Error processing task result: {e}",
                    exc_info=True,
                )
        
        return found_password, job_failed
    
    async def _handle_chunk_result(
        self,
        job: HashJob,
        status: ResultStatus,
        chunk: WorkChunk,
        result_payload: CrackResultPayload,
        found_password: Optional[str],
        job_failed: bool,
    ) -> tuple[Optional[str], bool]:
        """
        Handle a single chunk result.
        
        Returns:
            Tuple of (found_password, job_failed) updated after handling.
        """
        if status == ResultStatus.FOUND:
            is_first_found = self.chunk_manager.handle_found_result(
                job, chunk, result_payload.found_password
            )
            if is_first_found:
                found_password = result_payload.found_password
                logger.info(
                    f"Job {job.id[:8]}...: Password FOUND: "
                    f"{result_payload.found_password}"
                )
        
        elif status == ResultStatus.NOT_FOUND:
            self.chunk_manager.handle_not_found_result(job, chunk)
        
        elif status == ResultStatus.CANCELLED:
            self.chunk_manager.handle_cancelled_result(job, chunk)
        
        elif status == ResultStatus.INVALID_INPUT:
            # Invalid input - mark job as done and write output immediately
            self.job_manager.mark_job_done(job, password=None)
            await self._write_output(
                hash_value=job.hash_value,
                password=None,
                job_id=job.id,
                invalid_input=True,
            )
            logger.warning(
                f"Job {job.id[:8]}...: INVALID_INPUT - {result_payload.error_message or 'Invalid input'}"
            )
        
        elif status == ResultStatus.ERROR:
            should_retry = self.chunk_manager.handle_error_result(
                job, chunk, result_payload.last_index_processed
            )
            if not should_retry:
                # Max attempts exceeded
                if self.chunk_manager.check_any_chunk_failed(job):
                    self.job_manager.mark_job_failed(job)
                    await self._write_output(
                        hash_value=job.hash_value,
                        password=None,
                        job_id=job.id,
                        failed=True,
                    )
                    job_failed = True
        
        return found_password, job_failed
    
    async def _cleanup_tasks(self, active_tasks: set[asyncio.Task]) -> None:
        """
        Clean up any remaining tasks in finally block.
        """
        if active_tasks:
            for task in active_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*active_tasks, return_exceptions=True)
    
    async def _process_chunk(
        self,
        job: HashJob,
        chunk: WorkChunk,
        minion_url: str,
    ) -> Optional[tuple[ResultStatus, WorkChunk, CrackResultPayload]]:
        """
        Process a single chunk by sending request to minion.
        
        Returns:
            Tuple of (status, chunk, result_payload) if successful, None on error.
        """
        try:
            result = await self.client.send_crack_request(
                minion_url=minion_url,
                chunk=chunk,
                hash_value=job.hash_value,
                hash_type=job.hash_type,
                password_scheme=job.scheme,
                job_id=job.id,
            )
            
            logger.debug(
                f"Job {job.id[:8]}...: Chunk {chunk.id[:8]}... "
                f"from {minion_url} returned {result.status}"
            )
            
            return (result.status, chunk, result)
        
        except asyncio.CancelledError:
            logger.debug(
                f"Job {job.id[:8]}...: Chunk {chunk.id[:8]}... "
                f"cancelled (task cancelled)"
            )
            raise
        except Exception as e:
            logger.error(
                f"Job {job.id[:8]}...: Chunk {chunk.id[:8]}... "
                f"error from {minion_url}: {e}",
                exc_info=True,
            )
            # Return ERROR result
            return (
                ResultStatus.ERROR,
                chunk,
                CrackResultPayload(
                    status=ResultStatus.ERROR,
                    found_password=None,
                    last_index_processed=chunk.start_index,
                    error_message=f"Unexpected error: {str(e)}",
                ),
            )
    
    async def _broadcast_cancellation(self, job_id: str) -> None:
        """
        Broadcast cancellation to all minions (best-effort, non-blocking).
        
        Uses asyncio.create_task() internally to avoid blocking.
        """
        logger.info(
            f"Job {job_id[:8]}...: Broadcasting cancellation to all minions"
        )
        tasks = [
            self.client.send_cancel_job(minion_url, job_id)
            for minion_url in self.registry.all_minions()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"Job {job_id[:8]}...: Cancellation broadcast complete")
    
    async def _write_output(
        self,
        hash_value: str,
        password: Optional[str],
        job_id: str,
        failed: bool = False,
        invalid_input: bool = False,
    ) -> None:
        """
        Write output to stdout and JSON file (non-blocking).
        
        JSON format: {hash: {cracked_password: str|null, status: str, job_id: str}}
        Uses asyncio.to_thread() to avoid blocking the event loop.
        Errors writing do not crash the system.
        """
        # Determine status
        if invalid_input:
            status_str = OutputStatus.INVALID_INPUT
        elif failed:
            status_str = OutputStatus.FAILED
        elif password:
            status_str = "FOUND"
        else:
            status_str = OutputStatus.NOT_FOUND
        
        # Create JSON entry
        entry = {
            "cracked_password": password if password else None,
            "status": status_str,
            "job_id": job_id
        }
        
        # Print to stdout (human-readable format)
        if invalid_input:
            line = f"{hash_value} {OutputStatus.INVALID_INPUT} {job_id}"
        elif failed:
            line = f"{hash_value} {OutputStatus.FAILED} {job_id}"
        elif password:
            line = f"{hash_value} {password} {job_id}"
        else:
            line = f"{hash_value} {OutputStatus.NOT_FOUND} {job_id}"
        print(line)
        
        # Write to JSON file (non-blocking, with lock for atomic writes)
        try:
            async with self.output_lock:
                await asyncio.to_thread(
                    self._write_json_entry_sync,
                    self.output_file,
                    hash_value,
                    entry,
                )
            logger.info(
                f"Job {job_id[:8]}...: Wrote output ({status_str}): "
                f"{hash_value[:HashDisplay.PREFIX_LENGTH]}..."
            )
        except Exception as e:
            logger.error(
                f"Job {job_id[:8]}...: Failed to write output to file "
                f"{self.output_file}: {e}",
                exc_info=True,
            )
            # Still print to stdout even if file write fails
    
    @staticmethod
    def _write_json_entry_sync(file_path: str, hash_value: str, entry: dict) -> None:
        """
        Synchronous JSON file write helper (called from asyncio.to_thread).
        
        Reads existing JSON, updates it with new entry, writes back.
        Thread-safe when called with output_lock.
        """
        try:
            # Read existing JSON or start with empty dict
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    # File exists but is invalid JSON or empty - start fresh
                    data = {}
            else:
                data = {}
            
            # Update with new entry
            data[hash_value] = entry
            
            # Write back to file (atomic write)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()  # Ensure data is written immediately
        except (IOError, OSError) as e:
            # Re-raise to be caught by caller
            raise Exception(f"File write error: {e}") from e
