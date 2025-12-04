"""Tests for ChunkManager functionality."""

import pytest
from master.services.chunk_manager import ChunkManager
from shared.domain.models import HashJob, WorkChunk
from shared.domain.status import JobStatus, ChunkStatus
from shared.config.config import config


class TestChunkManager:
    """Tests for ChunkManager."""
    
    @pytest.fixture
    def chunk_manager(self):
        """Create a ChunkManager for testing."""
        return ChunkManager()
    
    @pytest.fixture
    def sample_job(self):
        """Create a sample job with chunks."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=200,
            status=JobStatus.PENDING
        )
        
        # Add some chunks
        job.chunks = [
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=99, status=ChunkStatus.DONE),
            WorkChunk(id="chunk-2", job_id="test-job", start_index=100, end_index=199, status=ChunkStatus.PENDING),
            WorkChunk(id="chunk-3", job_id="test-job", start_index=200, end_index=200, status=ChunkStatus.PENDING),
        ]
        
        return job
    
    def test_get_next_pending_chunk(self, chunk_manager, sample_job):
        """Test getting next pending chunk."""
        chunk = chunk_manager.get_next_pending_chunk(sample_job)
        
        assert chunk is not None
        assert chunk.id == "chunk-2"  # First pending chunk
        assert chunk.status == ChunkStatus.PENDING
    
    def test_get_next_pending_chunk_returns_none_when_all_done(self, chunk_manager):
        """Test that get_next_pending_chunk returns None when all chunks are done."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        
        job.chunks = [
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=100, status=ChunkStatus.DONE)
        ]
        
        chunk = chunk_manager.get_next_pending_chunk(job)
        assert chunk is None
    
    def test_mark_chunk_in_progress(self, chunk_manager, sample_job):
        """Test marking chunk as in progress."""
        chunk = sample_job.chunks[1]  # Pending chunk
        
        chunk_manager.mark_chunk_in_progress(chunk, "http://minion1:8000")
        
        assert chunk.status == ChunkStatus.IN_PROGRESS
        assert chunk.assigned_minion == "http://minion1:8000"
    
    def test_handle_found_result(self, chunk_manager, sample_job):
        """Test handling FOUND result."""
        chunk = sample_job.chunks[1]
        password = "050-0000000"
        
        result = chunk_manager.handle_found_result(sample_job, chunk, password)
        
        assert result is True  # First FOUND
        assert chunk.status == ChunkStatus.DONE
        assert chunk.last_index_processed == chunk.end_index
    
    def test_handle_found_result_idempotent(self, chunk_manager):
        """Test that duplicate FOUND after job DONE is ignored."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.DONE,  # Already done
            password_found="050-0000000"
        )
        
        chunk = WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=100, status=ChunkStatus.PENDING)
        
        result = chunk_manager.handle_found_result(job, chunk, "050-0000000")
        
        assert result is False  # Ignored
    
    def test_handle_not_found_result(self, chunk_manager, sample_job):
        """Test handling NOT_FOUND result."""
        chunk = sample_job.chunks[1]
        
        chunk_manager.handle_not_found_result(sample_job, chunk)
        
        assert chunk.status == ChunkStatus.DONE
        assert chunk.last_index_processed == chunk.end_index
    
    def test_handle_not_found_result_idempotent(self, chunk_manager):
        """Test that late NOT_FOUND after job DONE is ignored."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.DONE  # Already done
        )
        
        chunk = WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=100, status=ChunkStatus.IN_PROGRESS)
        
        # Should not raise error, just ignore
        chunk_manager.handle_not_found_result(job, chunk)
    
    def test_handle_cancelled_result(self, chunk_manager, sample_job):
        """Test handling CANCELLED result."""
        chunk = sample_job.chunks[1]
        
        chunk_manager.handle_cancelled_result(sample_job, chunk)
        
        assert chunk.status == ChunkStatus.CANCELLED
        # Attempts should NOT increase
        assert chunk.attempts == 0
    
    def test_handle_cancelled_result_not_counted_towards_retries(self, chunk_manager, sample_job):
        """Test that CANCELLED does not count towards MAX_ATTEMPTS."""
        chunk = sample_job.chunks[1]
        initial_attempts = chunk.attempts
        
        # Handle cancelled multiple times
        chunk_manager.handle_cancelled_result(sample_job, chunk)
        chunk.status = ChunkStatus.PENDING  # Reset for test
        chunk_manager.handle_cancelled_result(sample_job, chunk)
        
        # Attempts should still be 0
        assert chunk.attempts == initial_attempts
    
    def test_handle_error_result_retries(self, chunk_manager, sample_job):
        """Test that ERROR result triggers retry."""
        chunk = sample_job.chunks[1]
        initial_attempts = chunk.attempts
        
        should_retry = chunk_manager.handle_error_result(sample_job, chunk, 50)
        
        assert should_retry is True
        assert chunk.attempts == initial_attempts + 1
        assert chunk.status == ChunkStatus.PENDING  # Reset for retry
        assert chunk.assigned_minion is None
    
    def test_handle_error_result_exceeds_max_attempts(self, chunk_manager, sample_job):
        """Test that ERROR result fails after MAX_ATTEMPTS."""
        chunk = sample_job.chunks[1]
        max_attempts = config.MAX_ATTEMPTS
        
        # Retry up to max_attempts
        for _ in range(max_attempts):
            should_retry = chunk_manager.handle_error_result(sample_job, chunk, 50)
            if not should_retry:
                break
        
        assert should_retry is False
        assert chunk.attempts == max_attempts
        assert chunk.status == ChunkStatus.FAILED
    
    def test_check_all_chunks_done(self, chunk_manager):
        """Test checking if all chunks are done."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        
        # All chunks done
        job.chunks = [
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=50, status=ChunkStatus.DONE),
            WorkChunk(id="chunk-2", job_id="test-job", start_index=51, end_index=100, status=ChunkStatus.CANCELLED),
        ]
        
        assert chunk_manager.check_all_chunks_done(job) is True
        
        # One chunk still pending
        job.chunks.append(
            WorkChunk(id="chunk-3", job_id="test-job", start_index=101, end_index=150, status=ChunkStatus.PENDING)
        )
        
        assert chunk_manager.check_all_chunks_done(job) is False
    
    def test_check_any_chunk_failed(self, chunk_manager):
        """Test checking if any chunk has failed."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        
        # No failed chunks
        job.chunks = [
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=50, status=ChunkStatus.DONE),
        ]
        
        assert chunk_manager.check_any_chunk_failed(job) is False
        
        # One failed chunk
        job.chunks.append(
            WorkChunk(id="chunk-2", job_id="test-job", start_index=51, end_index=100, status=ChunkStatus.FAILED)
        )
        
        assert chunk_manager.check_any_chunk_failed(job) is True


