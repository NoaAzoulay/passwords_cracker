"""Chunk manager for tracking and retrying chunks."""

import logging
from typing import Optional
from shared.domain.models import HashJob, WorkChunk
from shared.domain.status import ChunkStatus, JobStatus
from shared.config.config import config

logger = logging.getLogger(__name__)


class ChunkManager:
    """Manages chunk states and retries."""
    
    def get_next_pending_chunk(self, job: HashJob) -> Optional[WorkChunk]:
        """
        Get next pending chunk for the job.
        Returns None if no pending chunks.
        """
        for chunk in job.chunks:
            if chunk.status == ChunkStatus.PENDING:
                return chunk
        return None
    
    def mark_chunk_in_progress(self, chunk: WorkChunk, minion_url: str) -> None:
        """Mark chunk as in progress and assign minion."""
        chunk.status = ChunkStatus.IN_PROGRESS
        chunk.assigned_minion = minion_url
        logger.debug(f"Chunk {chunk.id} assigned to {minion_url}")
    
    def handle_found_result(
        self,
        job: HashJob,
        chunk: WorkChunk,
        password: str,
    ) -> bool:
        """
        Handle FOUND result.
        
        Returns:
            True if this was the first FOUND (idempotent check)
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(f"Ignoring duplicate FOUND for chunk {chunk.id} (job already done)")
            return False
        
        chunk.status = ChunkStatus.DONE
        chunk.last_index_processed = chunk.end_index
        return True
    
    def handle_not_found_result(self, job: HashJob, chunk: WorkChunk) -> None:
        """
        Handle NOT_FOUND result.
        Idempotent: ignores if job already done.
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(f"Ignoring late NOT_FOUND for chunk {chunk.id} (job already done)")
            return
        
        chunk.status = ChunkStatus.DONE
        chunk.last_index_processed = chunk.end_index
        logger.debug(f"Chunk {chunk.id} completed: NOT_FOUND")
    
    def handle_cancelled_result(self, job: HashJob, chunk: WorkChunk) -> None:
        """
        Handle CANCELLED result.
        Do NOT retry, do NOT count towards MAX_ATTEMPTS.
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(f"Ignoring late CANCELLED for chunk {chunk.id} (job already done)")
            return
        
        chunk.status = ChunkStatus.CANCELLED
        logger.debug(f"Chunk {chunk.id} cancelled")
    
    def handle_error_result(
        self,
        job: HashJob,
        chunk: WorkChunk,
        last_index_processed: int,
    ) -> bool:
        """
        Handle ERROR result.
        
        Returns:
            True if should retry, False if exceeded MAX_ATTEMPTS
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(f"Ignoring late ERROR for chunk {chunk.id} (job already done)")
            return False
        
        chunk.attempts += 1
        chunk.last_index_processed = last_index_processed
        
        if chunk.attempts >= config.MAX_ATTEMPTS:
            chunk.status = ChunkStatus.FAILED
            logger.warning(
                f"Chunk {chunk.id} failed after {chunk.attempts} attempts "
                f"(max: {config.MAX_ATTEMPTS})"
            )
            return False
        else:
            # Reset to pending for retry
            chunk.status = ChunkStatus.PENDING
            chunk.assigned_minion = None
            logger.info(
                f"Chunk {chunk.id} will retry (attempt {chunk.attempts}/{config.MAX_ATTEMPTS})"
            )
            return True
    
    def check_all_chunks_done(self, job: HashJob) -> bool:
        """Check if all chunks are in a terminal state."""
        for chunk in job.chunks:
            if chunk.status not in (ChunkStatus.DONE, ChunkStatus.CANCELLED, ChunkStatus.FAILED):
                return False
        return True
    
    def check_any_chunk_failed(self, job: HashJob) -> bool:
        """Check if any chunk has failed."""
        return any(chunk.status == ChunkStatus.FAILED for chunk in job.chunks)

