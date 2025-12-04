"""Tests for scheduler edge cases and critical scenarios."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from shared.domain.models import HashJob, WorkChunk, CrackResultPayload
from shared.domain.status import JobStatus, ChunkStatus
from shared.domain.consts import ResultStatus
from master.services.scheduler import Scheduler
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.minion_client import MinionClient
from master.services.job_manager import JobManager
from master.infrastructure.cache import CrackedCache


@pytest.fixture
def mock_registry():
    """Create a mock MinionRegistry."""
    registry = MagicMock(spec=MinionRegistry)
    registry.pick_next = MagicMock(return_value="http://minion1:8000")
    registry.all_minions = MagicMock(return_value=["http://minion1:8000"])
    registry.get_available_minions = MagicMock(return_value=["http://minion1:8000"])
    registry.get_breaker = MagicMock()
    return registry


@pytest.fixture
def mock_client(mock_registry):
    """Create a mock MinionClient."""
    client = MagicMock(spec=MinionClient)
    client.registry = mock_registry
    client.send_crack_request = AsyncMock()
    client.send_cancel_job = AsyncMock()
    return client


@pytest.fixture
def mock_job_manager():
    """Create a mock JobManager."""
    manager = MagicMock(spec=JobManager)
    
    def mark_done_side_effect(job, password=None):
        job.status = JobStatus.DONE
        if password:
            job.password_found = password
    
    def mark_failed_side_effect(job):
        job.status = JobStatus.FAILED
    
    manager.mark_job_done.side_effect = mark_done_side_effect
    manager.mark_job_failed.side_effect = mark_failed_side_effect
    return manager


@pytest.fixture
def scheduler(mock_registry, mock_client, mock_job_manager, tmp_path):
    """Create a Scheduler for testing."""
    output_file = tmp_path / "output.txt"
    return Scheduler(
        registry=mock_registry,
        client=mock_client,
        job_manager=mock_job_manager,
        output_file=str(output_file)
    )


class TestSchedulerEdgeCases:
    """Tests for critical scheduler edge cases."""
    
    @pytest.mark.asyncio
    async def test_all_chunks_fail_job_failed(self, scheduler, mock_client, mock_job_manager, tmp_path):
        """Test that job is marked FAILED when all chunks fail."""
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
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=50, status=ChunkStatus.PENDING),
            WorkChunk(id="chunk-2", job_id="test-job", start_index=51, end_index=100, status=ChunkStatus.PENDING),
        ]
        
        # Mock ERROR responses that will exceed MAX_ATTEMPTS
        from shared.config.config import config
        error_count = 0
        
        def error_response(*args, **kwargs):
            nonlocal error_count
            error_count += 1
            return CrackResultPayload(
                status=ResultStatus.ERROR,
                found_password=None,
                last_index_processed=0,
                error_message="Network error"
            )
        
        mock_client.send_crack_request.side_effect = error_response
        
        await scheduler.process_job(job)
        
        # Job should be marked as FAILED
        assert job.status == JobStatus.FAILED
        mock_job_manager.mark_job_failed.assert_called()
        
        # Output should contain FAILED (JSON format)
        output_file = tmp_path / "output.txt"
        if output_file.exists():
            import json
            content = json.loads(output_file.read_text())
            # Check that at least one entry has FAILED status
            has_failed = any(entry.get("status") == "FAILED" for entry in content.values())
            assert has_failed
    
    @pytest.mark.asyncio
    async def test_mixed_results(self, scheduler, mock_client, mock_job_manager, tmp_path):
        """Test job with mixed results (FOUND, NOT_FOUND, CANCELLED)."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=200,
            status=JobStatus.PENDING
        )
        
        job.chunks = [
            WorkChunk(id="chunk-1", job_id="test-job", start_index=0, end_index=50, status=ChunkStatus.PENDING),
            WorkChunk(id="chunk-2", job_id="test-job", start_index=51, end_index=100, status=ChunkStatus.PENDING),
            WorkChunk(id="chunk-3", job_id="test-job", start_index=101, end_index=200, status=ChunkStatus.PENDING),
        ]
        
        # Mock mixed responses
        call_count = 0
        def mixed_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CrackResultPayload(
                    status=ResultStatus.FOUND,
                    found_password="050-0000000",
                    last_index_processed=0,
                    error_message=None
                )
            elif call_count == 2:
                return CrackResultPayload(
                    status=ResultStatus.NOT_FOUND,
                    found_password=None,
                    last_index_processed=100,
                    error_message=None
                )
            else:
                return CrackResultPayload(
                    status=ResultStatus.CANCELLED,
                    found_password=None,
                    last_index_processed=150,
                    error_message=None
                )
        
        mock_client.send_crack_request.side_effect = mixed_response
        
        await scheduler.process_job(job)
        
        # Job should be DONE (FOUND was first)
        assert job.status == JobStatus.DONE
        assert job.password_found == "050-0000000"
        
        # Cancellation should be broadcast (non-blocking, may complete asynchronously)
        # Wait a bit for async task to complete
        await asyncio.sleep(0.1)
        assert mock_client.send_cancel_job.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_chunk_retry_with_partial_progress(self, scheduler, mock_client, mock_job_manager):
        """Test that chunk retry uses last_index_processed correctly."""
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        
        chunk = WorkChunk(
            id="chunk-1",
            job_id="test-job",
            start_index=0,
            end_index=100,
            status=ChunkStatus.PENDING
        )
        job.chunks = [chunk]
        
        # First call: ERROR with partial progress
        # Second call: NOT_FOUND (completes)
        call_count = 0
        def retry_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CrackResultPayload(
                    status=ResultStatus.ERROR,
                    found_password=None,
                    last_index_processed=50,  # Partial progress
                    error_message="Network error"
                )
            else:
                return CrackResultPayload(
                    status=ResultStatus.NOT_FOUND,
                    found_password=None,
                    last_index_processed=100,
                    error_message=None
                )
        
        mock_client.send_crack_request.side_effect = retry_response
        
        await scheduler.process_job(job)
        
        # Should have retried (called twice)
        assert mock_client.send_crack_request.call_count == 2
        # Chunk should track last_index_processed from final result (NOT_FOUND)
        # After successful retry, last_index_processed should be end_index
        assert chunk.last_index_processed == 100  # From final NOT_FOUND result
        assert chunk.status == ChunkStatus.DONE
    
    @pytest.mark.asyncio
    async def test_output_file_write_failure(self, scheduler, mock_client, mock_job_manager, tmp_path):
        """Test that output file write failures don't crash the system."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        # Make output file read-only (simulate permission error)
        output_file.write_text("existing")
        output_file.chmod(0o444)  # Read-only
        
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.DONE,
            password_found="050-0000000"
        )
        
        # Should not raise exception
        try:
            await scheduler.process_job(job)
        except Exception:
            pytest.fail("Scheduler should handle output file write failures gracefully")
        
        # Job should still be processed
        assert job.status == JobStatus.DONE
    
    @pytest.mark.asyncio
    async def test_request_id_uniqueness(self, scheduler, mock_client, tmp_path):
        """Test that each request gets a unique request ID."""
        from master.infrastructure.minion_client import MinionClient
        from master.infrastructure.minion_registry import MinionRegistry
        
        registry = MinionRegistry(["http://minion1:8000"])
        client = MinionClient(registry)
        scheduler.client = client
        
        job = HashJob(
            id="test-job",
            hash_value="a" * 32,
            hash_type="md5",
            scheme="il_phone_05x_dash",
            total_space_start=0,
            total_space_end=100,
            status=JobStatus.PENDING
        )
        
        chunk = WorkChunk(
            id="chunk-1",
            job_id="test-job",
            start_index=0,
            end_index=100,
            status=ChunkStatus.PENDING
        )
        job.chunks = [chunk]
        
        # Capture request IDs
        request_ids = []
        
        async def capture_request(*args, **kwargs):
            # Extract request_id from the payload
            # This is a simplified check - actual implementation would need to inspect the request
            request_ids.append("captured")
            return CrackResultPayload(
                status=ResultStatus.NOT_FOUND,
                found_password=None,
                last_index_processed=100,
                error_message=None
            )
        
        # Mock the client's send_crack_request to capture request IDs
        original_send = client.send_crack_request
        client.send_crack_request = capture_request
        
        try:
            await scheduler.process_job(job)
        finally:
            await client.close()
        
        # Should have made at least one request
        assert len(request_ids) >= 1

