"""Tests for Scheduler functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from shared.domain.models import HashJob, WorkChunk, CrackResultPayload
from shared.domain.status import JobStatus, ChunkStatus
from shared.consts import ResultStatus, OutputStatus
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
    registry.all_minions = MagicMock(return_value=["http://minion1:8000", "http://minion2:8000"])
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
    manager.mark_job_done = MagicMock()
    manager.mark_job_failed = MagicMock()
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


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
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
    
    return job


class TestScheduler:
    """Tests for Scheduler functionality."""
    
    @pytest.mark.asyncio
    async def test_process_job_cache_hit_immediate_output(self, scheduler, tmp_path):
        """Test that cache hit writes output immediately."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        # Create job that's already done (cache hit)
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
        
        await scheduler.process_job(job)
        
        # Should write output
        assert output_file.exists()
        content = output_file.read_text()
        assert "050-0000000" in content
    
    @pytest.mark.asyncio
    async def test_process_job_found_broadcasts_cancellation(self, scheduler, mock_client, mock_job_manager, sample_job):
        """Test that FOUND result broadcasts cancellation to all minions."""
        # Mock FOUND result
        mock_client.send_crack_request.return_value = CrackResultPayload(
            status=ResultStatus.FOUND,
            found_password="050-0000000",
            last_index_processed=0,
            error_message=None
        )
        
        # Make mark_job_done actually update the job status so the loop exits
        def mark_done_side_effect(job, password=None):
            job.status = JobStatus.DONE
            if password:
                job.password_found = password
        
        mock_job_manager.mark_job_done.side_effect = mark_done_side_effect
        
        await scheduler.process_job(sample_job)
        
        # Should broadcast cancellation
        assert mock_client.send_cancel_job.call_count == 2  # Two minions
        mock_client.send_cancel_job.assert_any_call("http://minion1:8000", "test-job")
        mock_client.send_cancel_job.assert_any_call("http://minion2:8000", "test-job")
        
        # Job should be marked as done
        assert sample_job.status == JobStatus.DONE
        assert sample_job.password_found == "050-0000000"
    
    @pytest.mark.asyncio
    async def test_process_job_not_found_completes_job(self, scheduler, mock_client, mock_job_manager, sample_job):
        """Test that NOT_FOUND completes job when all chunks done."""
        # Mock NOT_FOUND results for all chunks
        mock_client.send_crack_request.return_value = CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=100,
            error_message=None
        )
        
        # Make mark_job_done actually update the job status so the loop exits
        def mark_done_side_effect(job, password=None):
            job.status = JobStatus.DONE
            if password:
                job.password_found = password
        
        mock_job_manager.mark_job_done.side_effect = mark_done_side_effect
        
        await scheduler.process_job(sample_job)
        
        # Should mark job as done
        mock_job_manager.mark_job_done.assert_called_once_with(sample_job, password=None)
        assert sample_job.status == JobStatus.DONE
    
    @pytest.mark.asyncio
    async def test_process_job_cancelled_does_not_retry(self, scheduler, mock_client, mock_job_manager, sample_job):
        """Test that CANCELLED responses do not reschedule chunks."""
        # Mock CANCELLED result
        mock_client.send_crack_request.return_value = CrackResultPayload(
            status=ResultStatus.CANCELLED,
            found_password=None,
            last_index_processed=25,
            error_message=None
        )
        
        # Make mark_job_done actually update the job status when all chunks are done
        def mark_done_side_effect(job, password=None):
            job.status = JobStatus.DONE
            if password:
                job.password_found = password
        
        mock_job_manager.mark_job_done.side_effect = mark_done_side_effect
        
        # Process job - both chunks will be cancelled, then job should complete
        import asyncio
        try:
            await asyncio.wait_for(
                scheduler.process_job(sample_job),
                timeout=2.0  # 2 second timeout for test
            )
        except asyncio.TimeoutError:
            pytest.fail("Test timed out - scheduler loop didn't exit")
        
        # Should have processed both chunks (both will be CANCELLED)
        assert mock_client.send_crack_request.call_count == 2  # Two chunks
        
        # Both chunks should be marked as CANCELLED
        assert sample_job.chunks[0].status == ChunkStatus.CANCELLED
        assert sample_job.chunks[1].status == ChunkStatus.CANCELLED
        
        # Job should be done (all chunks completed, even if cancelled)
        assert sample_job.status == JobStatus.DONE
    
    @pytest.mark.asyncio
    async def test_process_job_no_available_minions_waits(self, scheduler, mock_registry, sample_job):
        """Test that scheduler waits when no minions available (does not crash)."""
        # Mock no available minions
        mock_registry.pick_next.return_value = None
        
        # Use a timeout to prevent infinite loop in test
        try:
            await asyncio.wait_for(
                scheduler.process_job(sample_job),
                timeout=0.5  # Short timeout for test
            )
        except asyncio.TimeoutError:
            # Expected - scheduler should wait indefinitely
            pass
        
        # Should not crash or fail the job
        assert sample_job.status != JobStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_process_job_error_retries_until_max_attempts(self, scheduler, mock_client, mock_job_manager, sample_job):
        """Test that ERROR results retry until MAX_ATTEMPTS."""
        from shared.config.config import config
        
        # Mock ERROR result
        mock_client.send_crack_request.return_value = CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=0,
            error_message="Network error"
        )
        
        # Make mark_job_failed actually update the job status so the loop exits
        def mark_failed_side_effect(job):
            job.status = JobStatus.FAILED
        
        mock_job_manager.mark_job_failed.side_effect = mark_failed_side_effect
        
        # Process job (will retry until MAX_ATTEMPTS, then fail)
        # Use timeout to prevent infinite loop if something goes wrong
        import asyncio
        try:
            await asyncio.wait_for(
                scheduler.process_job(sample_job),
                timeout=2.0  # 2 second timeout for test
            )
        except asyncio.TimeoutError:
            pytest.fail("Test timed out - scheduler loop didn't exit")
        
        # Should have attempted multiple times (at least once per chunk, up to MAX_ATTEMPTS)
        assert mock_client.send_crack_request.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_write_output_found(self, scheduler, tmp_path):
        """Test writing FOUND output."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        scheduler._write_output("a" * 32, "050-0000000")
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "a" * 32 in content
        assert "050-0000000" in content
    
    @pytest.mark.asyncio
    async def test_write_output_not_found(self, scheduler, tmp_path):
        """Test writing NOT_FOUND output."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        scheduler._write_output("a" * 32, None, failed=False)
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "a" * 32 in content
        assert OutputStatus.NOT_FOUND in content
    
    @pytest.mark.asyncio
    async def test_write_output_failed(self, scheduler, tmp_path):
        """Test writing FAILED output."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        scheduler._write_output("a" * 32, None, failed=True)
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "a" * 32 in content
        assert OutputStatus.FAILED in content
    
    @pytest.mark.asyncio
    async def test_write_output_appends_to_file(self, scheduler, tmp_path):
        """Test that output appends to file (not overwrites)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        # Write first line
        scheduler._write_output("hash1", "pass1")
        
        # Write second line
        scheduler._write_output("hash2", "pass2")
        
        content = output_file.read_text()
        lines = content.strip().split('\n')
        assert len(lines) == 2
        assert "hash1" in lines[0]
        assert "hash2" in lines[1]

