"""Job manager for creating and managing hash jobs."""

import logging
import uuid
from typing import List, Optional
from shared.domain.models import HashJob, WorkChunk
from shared.domain.status import JobStatus, ChunkStatus
from shared.config.config import config
from shared.interfaces.password_scheme import PasswordScheme
from shared.factories.scheme_factory import create_scheme
from shared.consts import PasswordSchemeName, HashAlgorithm, HashDisplay
from master.infrastructure.cache import CrackedCache

logger = logging.getLogger(__name__)


class JobManager:
    """Manages hash jobs and their chunks."""
    
    def __init__(self, cache: CrackedCache):
        self.cache = cache
    
    def create_job(
        self,
        hash_value: str,
        hash_type: str = HashAlgorithm.MD5,
        scheme_name: str = PasswordSchemeName.IL_PHONE_05X_DASH,
    ) -> HashJob:
        """
        Create a new job for cracking a hash.
        
        Returns:
            HashJob with chunks already created
        """
        # Normalize hash to lowercase
        normalized_hash = hash_value.lower()
        
        # Check cache first
        cached_password = self.cache.get(normalized_hash)
        if cached_password:
            logger.info(f"Cache hit for hash {normalized_hash[:HashDisplay.PREFIX_LENGTH]}...")
            # Return a job that's already done
            job = HashJob(
                id=str(uuid.uuid4()),
                hash_value=normalized_hash,
                hash_type=hash_type,
                scheme=scheme_name,
                total_space_start=0,
                total_space_end=0,
                status=JobStatus.DONE,
                password_found=cached_password,
            )
            return job
        
        # Create scheme and get bounds
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
        
        # Split into chunks
        chunks = self._split_into_chunks(job_id, min_index, max_index)
        job.chunks = chunks
        
        logger.info(
            f"Created job {job_id} for hash {normalized_hash[:HashDisplay.PREFIX_LENGTH]}... "
            f"with {len(chunks)} chunks (space: [{min_index}, {max_index}])"
        )
        
        return job
    
    def _split_into_chunks(
        self,
        job_id: str,
        min_index: int,
        max_index: int,
    ) -> List[WorkChunk]:
        """
        Split index range into inclusive, gap-free chunks.
        
        Returns:
            List of WorkChunk objects
        """
        chunks = []
        chunk_size = config.CHUNK_SIZE
        current_start = min_index
        
        while current_start <= max_index:
            current_end = min(current_start + chunk_size - 1, max_index)
            
            chunk = WorkChunk(
                id=str(uuid.uuid4()),
                job_id=job_id,
                start_index=current_start,
                end_index=current_end,
                status=ChunkStatus.PENDING,
            )
            chunks.append(chunk)
            
            current_start = current_end + 1
        
        logger.debug(
            f"Split job {job_id} into {len(chunks)} chunks "
            f"(chunk_size={chunk_size}, range=[{min_index}, {max_index}])"
        )
        
        return chunks
    
    def mark_job_done(self, job: HashJob, password: Optional[str] = None) -> None:
        """Mark job as done and update cache if password found."""
        job.status = JobStatus.DONE
        if password:
            job.password_found = password
            self.cache.put(job.hash_value, password)
            logger.info(f"Job {job.id} completed: password found")
        else:
            logger.info(f"Job {job.id} completed: password not found")
    
    def mark_job_failed(self, job: HashJob) -> None:
        """Mark job as failed."""
        job.status = JobStatus.FAILED
        logger.warning(f"Job {job.id} failed")

