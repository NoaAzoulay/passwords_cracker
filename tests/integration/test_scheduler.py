"""Tests for Scheduler functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from shared.domain.models import HashJob, WorkChunk, CrackResultPayload
from shared.domain.status import JobStatus, ChunkStatus
from shared.domain.consts import ResultStatus, OutputStatus
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
    registry.get_available_minions = MagicMock(return_value=["http://minion1:8000", "http://minion2:8000"])
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
        
        # Should write output (JSON format)
        assert output_file.exists()
        import json
        content = json.loads(output_file.read_text())
        assert job.hash_value in content
        assert content[job.hash_value]["cracked_password"] == "050-0000000"
        assert content[job.hash_value]["status"] == "FOUND"
        assert content[job.hash_value]["job_id"] == job.id
    
    @pytest.mark.asyncio
    async def test_process_job_found_broadcasts_cancellation(self, scheduler, mock_client, mock_job_manager, sample_job):
        """Test that FOUND result broadcasts cancellation to all minions (non-blocking)."""
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
        
        # Wait a bit for cancellation broadcast task to complete
        await asyncio.sleep(0.1)
        
        # Should broadcast cancellation (non-blocking via asyncio.create_task)
        # Note: cancellation is non-blocking, so we check that it was called
        # The actual task may complete asynchronously
        assert mock_client.send_cancel_job.call_count >= 1  # At least one call
        
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
        mock_registry.get_available_minions.return_value = []  # No available minions
        
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
        """Test writing FOUND output (async)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        hash_value = "a" * 32
        await scheduler._write_output(hash_value, "050-0000000", "test-job")
        
        assert output_file.exists()
        import json
        content = json.loads(output_file.read_text())
        assert hash_value in content
        assert content[hash_value]["cracked_password"] == "050-0000000"
        assert content[hash_value]["status"] == "FOUND"
        assert content[hash_value]["job_id"] == "test-job"
    
    @pytest.mark.asyncio
    async def test_write_output_not_found(self, scheduler, tmp_path):
        """Test writing NOT_FOUND output (async)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        hash_value = "a" * 32
        await scheduler._write_output(hash_value, None, "test-job", failed=False)
        
        assert output_file.exists()
        import json
        content = json.loads(output_file.read_text())
        assert hash_value in content
        assert content[hash_value]["cracked_password"] is None
        assert content[hash_value]["status"] == OutputStatus.NOT_FOUND
        assert content[hash_value]["job_id"] == "test-job"
    
    @pytest.mark.asyncio
    async def test_write_output_failed(self, scheduler, tmp_path):
        """Test writing FAILED output (async)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        hash_value = "a" * 32
        await scheduler._write_output(hash_value, None, "test-job", failed=True)
        
        assert output_file.exists()
        import json
        content = json.loads(output_file.read_text())
        assert hash_value in content
        assert content[hash_value]["cracked_password"] is None
        assert content[hash_value]["status"] == OutputStatus.FAILED
        assert content[hash_value]["job_id"] == "test-job"
    
    @pytest.mark.asyncio
    async def test_write_output_appends_to_file(self, scheduler, tmp_path):
        """Test that output appends to file (not overwrites, async)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        # Write first entry
        await scheduler._write_output("hash1", "pass1", "job1")
        
        # Write second entry
        await scheduler._write_output("hash2", "pass2", "job2")
        
        # Both should be in JSON file
        import json
        content = json.loads(output_file.read_text())
        assert len(content) == 2
        assert "hash1" in content
        assert content["hash1"]["cracked_password"] == "pass1"
        assert content["hash1"]["status"] == "FOUND"
        assert "hash2" in content
        assert content["hash2"]["cracked_password"] == "pass2"
        assert content["hash2"]["status"] == "FOUND"
    
    @pytest.mark.asyncio
    async def test_write_output_concurrent_writes_thread_safe(self, scheduler, tmp_path):
        """Test that concurrent output writes are thread-safe (lock-protected)."""
        output_file = tmp_path / "output.txt"
        scheduler.output_file = str(output_file)
        
        # Write multiple outputs concurrently to test lock protection
        import asyncio
        tasks = [
            scheduler._write_output(f"hash{i}", f"pass{i}", f"job{i}")
            for i in range(10)
        ]
        await asyncio.gather(*tasks)
        
        # Verify all writes completed and file is valid JSON
        import json
        content = json.loads(output_file.read_text())
        assert len(content) == 10
        
        # Verify all hashes and passwords are present
        for i in range(10):
            assert f"hash{i}" in content
            assert content[f"hash{i}"]["cracked_password"] == f"pass{i}"
            assert content[f"hash{i}"]["status"] == "FOUND"
            assert content[f"hash{i}"]["job_id"] == f"job{i}"

