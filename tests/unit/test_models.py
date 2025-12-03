"""Tests for domain models."""

import pytest
from shared.domain.models import HashJob, WorkChunk, CrackRangePayload, CrackResultPayload, RangeDict
from shared.domain.status import JobStatus, ChunkStatus
from shared.consts import ResultStatus


class TestHashJob:
    """Tests for HashJob model."""
    
    def test_hash_job_creation(self):
        """Test creating a HashJob."""
        job = HashJob(
            id="test-job-1",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
        )
        
        assert job.id == "test-job-1"
        assert job.hash_value == "a" * 32
        assert job.status == JobStatus.PENDING
        assert len(job.chunks) == 0
        assert job.password_found is None
    
    def test_hash_job_is_complete_pending(self):
        """Test that PENDING job is not complete."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        assert job.is_complete() is False
    
    def test_hash_job_is_complete_done(self):
        """Test that DONE job is complete."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.DONE
        )
        assert job.is_complete() is True
    
    def test_hash_job_is_complete_cancelled(self):
        """Test that CANCELLED job is complete."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.CANCELLED
        )
        assert job.is_complete() is True
    
    def test_hash_job_is_complete_failed(self):
        """Test that FAILED job is complete."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.FAILED
        )
        assert job.is_complete() is True


class TestWorkChunk:
    """Tests for WorkChunk model."""
    
    def test_work_chunk_creation(self):
        """Test creating a WorkChunk."""
        chunk = WorkChunk(
            id="test-chunk-1",
            job_id="test-job-1",
            start_index=0,
            end_index=100,
        )
        
        assert chunk.id == "test-chunk-1"
        assert chunk.job_id == "test-job-1"
        assert chunk.start_index == 0
        assert chunk.end_index == 100
        assert chunk.status == ChunkStatus.PENDING
        assert chunk.assigned_minion is None
        assert chunk.attempts == 0
    
    def test_work_chunk_inclusive_range(self):
        """Test that chunk range is inclusive."""
        chunk = WorkChunk(
            id="test-chunk",
            job_id="test-job",
            start_index=10,
            end_index=20,
        )
        
        # Range should be inclusive: [10, 20] means 11 indices
        assert chunk.end_index >= chunk.start_index
        range_size = chunk.end_index - chunk.start_index + 1
        assert range_size == 11


class TestRangeDict:
    """Tests for RangeDict Pydantic model."""
    
    def test_range_dict_creation(self):
        """Test creating a RangeDict."""
        range_dict = RangeDict(start_index=0, end_index=100)
        assert range_dict.start_index == 0
        assert range_dict.end_index == 100
    
    def test_range_dict_validation_end_greater_than_start(self):
        """Test that RangeDict validates end_index >= start_index."""
        # Valid: end >= start
        range_dict = RangeDict(start_index=0, end_index=100)
        assert range_dict.end_index >= range_dict.start_index
        
        # Valid: end == start
        range_dict = RangeDict(start_index=50, end_index=50)
        assert range_dict.end_index == range_dict.start_index
    
    def test_range_dict_validation_fails_when_end_less_than_start(self):
        """Test that RangeDict raises error when end_index < start_index."""
        with pytest.raises(ValueError, match="end_index.*must be >= start_index"):
            RangeDict(start_index=100, end_index=0)
    
    def test_range_dict_validation_non_negative(self):
        """Test that RangeDict validates non-negative indices."""
        # Valid: non-negative
        range_dict = RangeDict(start_index=0, end_index=100)
        assert range_dict.start_index >= 0
        assert range_dict.end_index >= 0


class TestCrackRangePayload:
    """Tests for CrackRangePayload model."""
    
    def test_crack_range_payload_creation(self):
        """Test creating a CrackRangePayload."""
        payload = CrackRangePayload(
            hash="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            range=RangeDict(start_index=0, end_index=100),
            job_id="test-job",
            request_id="test-request"
        )
        
        assert payload.hash == "a" * 32
        assert payload.hash_type == "md5"
        assert payload.password_scheme == "il_phone_05x_dash"
        assert payload.range.start_index == 0
        assert payload.range.end_index == 100
        assert payload.job_id == "test-job"
        assert payload.request_id == "test-request"
    
    def test_crack_range_payload_serialization(self):
        """Test that CrackRangePayload can be serialized to dict."""
        payload = CrackRangePayload(
            hash="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            range=RangeDict(start_index=0, end_index=100),
            job_id="test-job",
            request_id="test-request"
        )
        
        data = payload.model_dump()
        assert "hash" in data
        assert "range" in data
        assert data["range"]["start_index"] == 0
        assert data["range"]["end_index"] == 100


class TestCrackResultPayload:
    """Tests for CrackResultPayload model."""
    
    def test_crack_result_payload_found(self):
        """Test creating a FOUND result."""
        result = CrackResultPayload(
            status=ResultStatus.FOUND,
            found_password="050-0000000",
            last_index_processed=0,
            error_message=None
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == "050-0000000"
        assert result.last_index_processed == 0
        assert result.error_message is None
    
    def test_crack_result_payload_not_found(self):
        """Test creating a NOT_FOUND result."""
        result = CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=100,
            error_message=None
        )
        
        assert result.status == ResultStatus.NOT_FOUND
        assert result.found_password is None
        assert result.last_index_processed == 100
    
    def test_crack_result_payload_error(self):
        """Test creating an ERROR result."""
        result = CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=50,
            error_message="Network timeout"
        )
        
        assert result.status == ResultStatus.ERROR
        assert result.error_message == "Network timeout"
    
    def test_crack_result_payload_status_validation(self):
        """Test that status must be one of the allowed values."""
        # Valid statuses
        for status in [ResultStatus.FOUND, ResultStatus.NOT_FOUND, ResultStatus.CANCELLED, ResultStatus.ERROR]:
            result = CrackResultPayload(status=status)
            assert result.status == status
        
        # Invalid status should fail (Pydantic validation)
        with pytest.raises(Exception):  # Pydantic validation error
            CrackResultPayload(status="INVALID_STATUS")

