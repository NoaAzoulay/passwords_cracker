"""Chunk manager for tracking and retrying chunks."""

import logging
from typing import Optional
from shared.domain.models import HashJob, WorkChunk
from shared.domain.status import ChunkStatus, JobStatus
from shared.config.config import config
from shared.domain.consts import HashDisplay

logger = logging.getLogger(__name__)


class ChunkManager:
    """
    Manages chunk states, retries, and completion tracking.
    
    Handles transitions between PENDING, IN_PROGRESS, DONE, CANCELLED, and FAILED states.
    Implements idempotent result handling and retry logic.
    
    Thread-safety: This class is stateless. All methods operate on HashJob and WorkChunk
    instances passed as parameters. Each job has its own chunks, so there's no shared
    mutable state across jobs. Safe for concurrent use across multiple async tasks.
    """
    
    def get_next_pending_chunk(self, job: HashJob) -> Optional[WorkChunk]:
        """
        Get next pending chunk for the job.
        
        Returns:
            Next pending WorkChunk, or None if no pending chunks.
        """
        for chunk in job.chunks:
            if chunk.status == ChunkStatus.PENDING:
                logger.debug(
                    f"Job {job.id[:8]}...: Found pending chunk {chunk.id[:8]}... "
                    f"range [{chunk.start_index}, {chunk.end_index}]"
                )
                return chunk
        return None
    
    def mark_chunk_in_progress(self, chunk: WorkChunk, minion_url: str) -> None:
        """
        Mark chunk as in progress and assign minion.
        """
        chunk.status = ChunkStatus.IN_PROGRESS
        chunk.assigned_minion = minion_url
        logger.info(
            f"Chunk {chunk.id[:8]}... (job {chunk.job_id[:8]}...): "
            f"PENDING → IN_PROGRESS, assigned to {minion_url}"
        )
    
    def handle_found_result(
        self,
        job: HashJob,
        chunk: WorkChunk,
        password: str,
    ) -> bool:
        """
        Handle FOUND result.
        
        Marks chunk as DONE and sets last_index_processed to end_index.
        Idempotent: ignores if job already done.
        
        Returns:
            True if this was the first FOUND (idempotent check), False if duplicate.
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"Ignoring duplicate FOUND (job already done)"
            )
            return False
        
        chunk.status = ChunkStatus.DONE
        chunk.last_index_processed = chunk.end_index
        logger.info(
            f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
            f"IN_PROGRESS → DONE (FOUND: password={password})"
        )
        return True
    
    def handle_not_found_result(self, job: HashJob, chunk: WorkChunk) -> None:
        """
        Handle NOT_FOUND result.
        
        Marks chunk as DONE and sets last_index_processed to end_index.
        Idempotent: ignores if job already done.
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"Ignoring late NOT_FOUND (job already done)"
            )
            return
        
        chunk.status = ChunkStatus.DONE
        chunk.last_index_processed = chunk.end_index
        logger.info(
            f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
            f"IN_PROGRESS → DONE (NOT_FOUND, processed [{chunk.start_index}, {chunk.end_index}])"
        )
    
    def handle_cancelled_result(self, job: HashJob, chunk: WorkChunk) -> None:
        """
        Handle CANCELLED result.
        
        Marks chunk as CANCELLED. Does NOT increment attempts.
        CANCELLED chunks count as "completed" for job termination.
        Idempotent: ignores if job already done.
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"Ignoring late CANCELLED (job already done)"
            )
            return
        
        chunk.status = ChunkStatus.CANCELLED
        logger.info(
            f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
            f"IN_PROGRESS → CANCELLED (attempts={chunk.attempts}, not counted)"
        )
    
    def handle_error_result(
        self,
        job: HashJob,
        chunk: WorkChunk,
        last_index_processed: int,
    ) -> bool:
        """
        Handle ERROR result.
        
        Increments attempt count. If attempts < MAX_ATTEMPTS, resets chunk to PENDING for retry.
        If attempts >= MAX_ATTEMPTS, marks chunk as FAILED.
        Idempotent: ignores if job already done.
        
        Returns:
            True if should retry, False if exceeded MAX_ATTEMPTS (chunk failed).
        """
        # Idempotency: ignore if job already done
        if job.status == JobStatus.DONE:
            logger.debug(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"Ignoring late ERROR (job already done)"
            )
            return False
        
        chunk.attempts += 1
        chunk.last_index_processed = last_index_processed
        
        if chunk.attempts >= config.MAX_ATTEMPTS:
            chunk.status = ChunkStatus.FAILED
            logger.warning(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"IN_PROGRESS → FAILED after {chunk.attempts} attempts "
                f"(max: {config.MAX_ATTEMPTS}, last_index={last_index_processed})"
            )
            return False
        else:
            # Reset to pending for retry
            chunk.status = ChunkStatus.PENDING
            chunk.assigned_minion = None
            logger.info(
                f"Chunk {chunk.id[:8]}... (job {job.id[:8]}...): "
                f"IN_PROGRESS → PENDING (will retry: attempt {chunk.attempts}/{config.MAX_ATTEMPTS}, "
                f"resume from index {last_index_processed})"
            )
            return True
    
    def check_all_chunks_done(self, job: HashJob) -> bool:
        """
        Check if all chunks are in a terminal state.
        
        Terminal states: DONE, CANCELLED, FAILED.
        
        Returns:
            True if all chunks are in terminal states, False otherwise.
        """
        for chunk in job.chunks:
            if chunk.status not in (ChunkStatus.DONE, ChunkStatus.CANCELLED, ChunkStatus.FAILED):
                return False
        return True
    
    def check_any_chunk_failed(self, job: HashJob) -> bool:
        """
        Check if any chunk has failed.
        
        Returns:
            True if any chunk status is FAILED, False otherwise.
        """
        return any(chunk.status == ChunkStatus.FAILED for chunk in job.chunks)


