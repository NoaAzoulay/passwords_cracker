"""Tests for JobManager functionality."""

import pytest
from master.services.job_manager import JobManager
from master.infrastructure.cache import CrackedCache
from shared.domain.models import HashJob
from shared.domain.status import JobStatus
from shared.config.config import config


class TestJobManager:
    """Tests for JobManager."""
    
    @pytest.fixture
    def cache(self):
        """Create a cache for testing."""
        return CrackedCache()
    
    @pytest.fixture
    def job_manager(self, cache):
        """Create a JobManager for testing."""
        return JobManager(cache)
    
    def test_create_job_from_hash(self, job_manager):
        """Test creating a job from a hash."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        
        assert isinstance(job, HashJob)
        assert job.hash_value == hash_value.lower()  # Normalized
        assert job.hash_type == "md5"
        assert job.scheme == "il_phone_05x_dash"
        assert job.status == JobStatus.PENDING
        assert len(job.chunks) > 0
    
    def test_create_job_normalizes_hash_to_lowercase(self, job_manager):
        """Test that job creation normalizes hash to lowercase."""
        hash_upper = "A" * 32
        
        job = job_manager.create_job(hash_upper)
        
        assert job.hash_value == hash_upper.lower()
    
    def test_create_job_cache_hit_returns_done_job(self, job_manager, cache):
        """Test that cache hit returns a job that's already done."""
        hash_value = "a" * 32
        password = "050-0000000"
        
        # Put in cache
        cache.put(hash_value, password)
        
        # Create job
        job = job_manager.create_job(hash_value)
        
        assert job.status == JobStatus.DONE
        assert job.password_found == password
        assert len(job.chunks) == 0  # No chunks needed for cache hit
    
    def test_create_job_chunks_inclusive_and_gap_free(self, job_manager):
        """Test that chunks are created with inclusive, gap-free ranges."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        chunks = job.chunks
        
        # Check chunks are inclusive and gap-free
        for i in range(len(chunks) - 1):
            current = chunks[i]
            next_chunk = chunks[i + 1]
            
            # No gaps
            assert next_chunk.start_index == current.end_index + 1
            
            # Inclusive
            assert current.end_index >= current.start_index
    
    def test_create_job_chunks_cover_entire_space(self, job_manager):
        """Test that chunks cover the entire search space."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        chunks = job.chunks
        
        # First chunk starts at min
        assert chunks[0].start_index == job.total_space_start
        
        # Last chunk ends at max
        assert chunks[-1].end_index == job.total_space_end
    
    def test_create_job_chunks_respect_chunk_size(self, job_manager):
        """Test that chunks respect CHUNK_SIZE (except last)."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        chunks = job.chunks
        
        chunk_size = config.CHUNK_SIZE
        
        # All chunks except last should be exactly CHUNK_SIZE
        for chunk in chunks[:-1]:
            size = chunk.end_index - chunk.start_index + 1
            assert size == chunk_size
        
        # Last chunk can be smaller
        if len(chunks) > 1:
            last_size = chunks[-1].end_index - chunks[-1].start_index + 1
            assert last_size <= chunk_size
    
    def test_mark_job_done_with_password(self, job_manager, cache):
        """Test marking job as done with password found."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        password = "050-0000000"
        
        job_manager.mark_job_done(job, password=password)
        
        assert job.status == JobStatus.DONE
        assert job.password_found == password
        
        # Should be in cache
        assert cache.get(hash_value) == password
    
    def test_mark_job_done_without_password(self, job_manager):
        """Test marking job as done without password (NOT_FOUND)."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        
        job_manager.mark_job_done(job, password=None)
        
        assert job.status == JobStatus.DONE
        assert job.password_found is None
    
    def test_mark_job_failed(self, job_manager):
        """Test marking job as failed."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value)
        
        job_manager.mark_job_failed(job)
        
        assert job.status == JobStatus.FAILED
    
    def test_job_creation_with_custom_hash_type(self, job_manager):
        """Test creating job with custom hash type."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value, hash_type="sha256")
        
        assert job.hash_type == "sha256"
    
    def test_job_creation_with_custom_scheme(self, job_manager):
        """Test creating job with custom scheme."""
        hash_value = "a" * 32
        
        job = job_manager.create_job(hash_value, scheme_name="il_phone_05x_dash")
        
        assert job.scheme == "il_phone_05x_dash"
    
    def test_clear_cache(self, job_manager, cache):
        """Test that clear_cache() clears the underlying cache."""
        hash_value = "a" * 32
        password = "050-0000000"
        
        # Add entry to cache
        cache.put(hash_value, password)
        assert cache.get(hash_value) == password
        
        # Clear via JobManager
        job_manager.clear_cache()
        
        # Verify cache is cleared
        assert cache.get(hash_value) is None
    
    def test_clear_cache_empty_cache(self, job_manager):
        """Test that clear_cache() on empty cache does not raise."""
        # Should not raise
        job_manager.clear_cache()
        
        # Cache should still be empty
        assert job_manager.cache.get("a" * 32) is None


