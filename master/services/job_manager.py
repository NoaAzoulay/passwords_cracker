"""Job manager for creating and managing hash jobs."""

import logging
import uuid
from typing import List, Optional
from shared.domain.models import HashJob, WorkChunk
from shared.domain.status import JobStatus, ChunkStatus
from shared.config.config import config
from shared.factories.scheme_factory import create_scheme
from shared.domain.consts import PasswordSchemeName, HashAlgorithm, HashDisplay
from master.infrastructure.cache import CrackedCache

logger = logging.getLogger(__name__)


class JobManager:
    """
    Manages hash jobs and their chunks.
    
    Thread-safety: This class is stateless except for the cache reference.
    Each job is independent, and create_job() creates new HashJob instances.
    Safe for concurrent use across multiple async tasks.
    """
    
    def __init__(self, cache: CrackedCache):
        self.cache = cache
    
    def clear_cache(self) -> None:
        """
        Clear the underlying cache.
        
        This is a convenience method that delegates to the cache's clear()
        method, providing clean encapsulation for cache management.
        """
        self.cache.clear()
    
    def create_job(
        self,
        hash_value: str,
        hash_type: str = HashAlgorithm.MD5,
        scheme_name: str = PasswordSchemeName.IL_PHONE_05X_DASH,
    ) -> HashJob:
        """
        Create a new job for cracking a hash.
        
        Cache lookup happens BEFORE chunk generation. If cache hit:
        - Returns a DONE job with password_found
        - Does NOT create chunks
        
        If cache miss:
        - Creates chunks covering entire search space
        - Chunks are gap-free, inclusive, and respect CHUNK_SIZE
        
        Returns:
            HashJob with status DONE (cache hit) or PENDING (cache miss) with chunks.
        """
        # Normalize hash to lowercase
        normalized_hash = hash_value.lower()
        
        # Check cache FIRST (before creating chunks)
        cached_password = self.cache.get(normalized_hash)
        if cached_password:
            logger.info(
                f"Cache hit for hash {normalized_hash[:HashDisplay.PREFIX_LENGTH]}... "
                f"(password: {cached_password})"
            )
            # Return a job that's already done (no chunks needed)
            job = HashJob(
                id=str(uuid.uuid4()),
                hash_value=normalized_hash,
                hash_type=hash_type,
                scheme=scheme_name,
                total_space_start=0,
                total_space_end=0,
                status=JobStatus.DONE,
                password_found=cached_password,
                chunks=[],  # No chunks needed for cache hit
            )
            return job
        
        # Cache miss: create scheme and get bounds
        scheme = create_scheme(scheme_name)
        min_index, max_index = scheme.get_space_bounds()
        
        # Create job
        job_id = str(uuid.uuid4())
        job = HashJob(
            id=job_id,
            hash_value=normalized_hash,
            hash_type=hash_type,
            scheme=scheme_name,
            total_space_start=min_index,
            total_space_end=max_index,
            status=JobStatus.PENDING,
        )
        
        # Split into chunks (gap-free, inclusive, covering entire space)
        chunks = self._split_into_chunks(job_id, min_index, max_index)
        job.chunks = chunks
        
        logger.info(
            f"Created job {job_id} for hash {normalized_hash[:HashDisplay.PREFIX_LENGTH]}... "
            f"with {len(chunks)} chunks (space: [{min_index}, {max_index}], "
            f"chunk_size={config.CHUNK_SIZE})"
        )
        
        return job
    
    def _split_into_chunks(
        self,
        job_id: str,
        min_index: int,
        max_index: int,
    ) -> List[WorkChunk]:
        """
        Split index range into inclusive, gap-free chunks covering entire search space.
        
        Chunks are:
        - Gap-free: end_index of chunk N = start_index of chunk N+1 - 1
        - Inclusive: both start_index and end_index are included
        - Cover entire space: from min_index to max_index with no gaps
        - Respect CHUNK_SIZE: each chunk (except last) has exactly CHUNK_SIZE indices
        
        Returns:
            List of WorkChunk objects covering [min_index, max_index] with no gaps.
        """
        chunks = []
        chunk_size = config.CHUNK_SIZE
        current_start = min_index
        
        while current_start <= max_index:
            # Calculate end_index: inclusive, so add (chunk_size - 1)
            # Cap at max_index to avoid going beyond search space
            current_end = min(current_start + chunk_size - 1, max_index)
            
            chunk = WorkChunk(
                id=str(uuid.uuid4()),
                job_id=job_id,
                start_index=current_start,
                end_index=current_end,  # inclusive
                status=ChunkStatus.PENDING,
            )
            chunks.append(chunk)
            
            # Next chunk starts right after this one (gap-free)
            current_start = current_end + 1
        
        # Verify gap-free property
        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                assert chunks[i].end_index + 1 == chunks[i + 1].start_index, \
                    f"Gap detected: chunk {i} ends at {chunks[i].end_index}, " \
                    f"chunk {i+1} starts at {chunks[i+1].start_index}"
        
        logger.debug(
            f"Split job {job_id[:8]}... into {len(chunks)} chunks "
            f"(chunk_size={chunk_size}, range=[{min_index}, {max_index}], "
            f"total_indices={max_index - min_index + 1})"
        )
        
        return chunks
    
    def mark_job_done(self, job: HashJob, password: Optional[str] = None) -> None:
        """
        Mark job as done and update cache if password found.
        
        Cache behavior:
        - If password found → save to cache
        - If NOT_FOUND → do NOT save to cache (avoid polluting cache with negatives)
        """
        job.status = JobStatus.DONE
        if password:
            job.password_found = password
            # Save to cache only if password found
            self.cache.put(job.hash_value, password)
            logger.info(
                f"Job {job.id[:8]}... (hash {job.hash_value[:HashDisplay.PREFIX_LENGTH]}...): "
                f"PENDING → DONE (password found: {password}, cached)"
            )
        else:
            # NOT_FOUND: do NOT save to cache
            logger.info(
                f"Job {job.id[:8]}... (hash {job.hash_value[:HashDisplay.PREFIX_LENGTH]}...): "
                f"PENDING → DONE (password not found, not cached)"
            )
    
    def mark_job_failed(self, job: HashJob) -> None:
        """Mark job as failed."""
        job.status = JobStatus.FAILED
        logger.warning(f"Job {job.id} failed")

