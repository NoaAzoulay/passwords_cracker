"""End-to-end tests without Docker."""

import pytest
import asyncio
import hashlib
from pathlib import Path
from fastapi.testclient import TestClient
from minion.api.app import app as minion_app
from shared.domain.models import HashJob
from shared.domain.status import JobStatus
from master.infrastructure.cache import CrackedCache
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.minion_client import MinionClient
from master.services.job_manager import JobManager
from master.services.scheduler import Scheduler


@pytest.fixture
def mock_minion_servers():
    """Create mock minion FastAPI test clients."""
    return [
        TestClient(minion_app),
        TestClient(minion_app),
        TestClient(minion_app),
    ]


class TestEndToEnd:
    """End-to-end tests simulating full system."""
    
    @pytest.mark.asyncio
    async def test_e2e_found_case(self, tmp_path):
        """Test end-to-end with FOUND case."""
        output_file = tmp_path / "output.txt"
        
        # Initialize components
        cache = CrackedCache()
        registry = MinionRegistry(["http://localhost:8000", "http://localhost:8001"])
        
        # Mock the HTTP client to use test clients
        from unittest.mock import AsyncMock, MagicMock
        
        mock_client = MagicMock(spec=MinionClient)
        mock_client.registry = registry
        
        # Create test password and hash
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Mock successful FOUND response
        from shared.domain.models import CrackResultPayload
        from shared.consts import ResultStatus
        
        mock_client.send_crack_request = AsyncMock(return_value=CrackResultPayload(
            status=ResultStatus.FOUND,
            found_password=test_password,
            last_index_processed=0,
            error_message=None
        ))
        mock_client.send_cancel_job = AsyncMock()
        
        job_manager = JobManager(cache)
        scheduler = Scheduler(
            registry=registry,
            client=mock_client,
            job_manager=job_manager,
            output_file=str(output_file)
        )
        
        # Create and process job
        job = job_manager.create_job(test_hash)
        await scheduler.process_job(job)
        
        # Verify results
        assert job.status == JobStatus.DONE
        assert job.password_found == test_password
        assert output_file.exists()
        content = output_file.read_text()
        assert test_hash in content
        assert test_password in content
        
        # Verify cancellation was broadcast
        assert mock_client.send_cancel_job.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_e2e_not_found_case(self, tmp_path):
        """Test end-to-end with NOT_FOUND case."""
        output_file = tmp_path / "output.txt"
        
        cache = CrackedCache()
        registry = MinionRegistry(["http://localhost:8000"])
        
        from unittest.mock import AsyncMock, MagicMock
        from shared.domain.models import CrackResultPayload
        from shared.consts import ResultStatus
        
        mock_client = MagicMock(spec=MinionClient)
        mock_client.registry = registry
        mock_client.send_crack_request = AsyncMock(return_value=CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=100,
            error_message=None
        ))
        mock_client.send_cancel_job = AsyncMock()
        
        job_manager = JobManager(cache)
        scheduler = Scheduler(
            registry=registry,
            client=mock_client,
            job_manager=job_manager,
            output_file=str(output_file)
        )
        
        # Create job with fake hash
        fake_hash = "a" * 32
        job = job_manager.create_job(fake_hash)
        
        # Process job
        await scheduler.process_job(job)
        
        # Verify results
        assert job.status == JobStatus.DONE
        assert job.password_found is None
        assert output_file.exists()
        content = output_file.read_text()
        assert fake_hash in content
        assert "NOT_FOUND" in content
    
    @pytest.mark.asyncio
    async def test_e2e_failed_case(self, tmp_path):
        """Test end-to-end with FAILED case (exceeded retries)."""
        output_file = tmp_path / "output.txt"
        
        cache = CrackedCache()
        registry = MinionRegistry(["http://localhost:8000"])
        
        from unittest.mock import AsyncMock, MagicMock
        from shared.domain.models import CrackResultPayload
        from shared.consts import ResultStatus
        from shared.config.config import config
        
        mock_client = MagicMock(spec=MinionClient)
        mock_client.registry = registry
        
        # Mock ERROR responses (will exceed MAX_ATTEMPTS)
        mock_client.send_crack_request = AsyncMock(return_value=CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=0,
            error_message="Network error"
        ))
        mock_client.send_cancel_job = AsyncMock()
        
        job_manager = JobManager(cache)
        scheduler = Scheduler(
            registry=registry,
            client=mock_client,
            job_manager=job_manager,
            output_file=str(output_file)
        )
        
        fake_hash = "a" * 32
        job = job_manager.create_job(fake_hash)
        
        # Process job (will retry until MAX_ATTEMPTS)
        await scheduler.process_job(job)
        
        # Verify job failed
        assert job.status == JobStatus.FAILED
        assert output_file.exists()
        content = output_file.read_text()
        assert fake_hash in content
        assert "FAILED" in content
    
    @pytest.mark.asyncio
    async def test_e2e_cache_hit_skips_scheduling(self, tmp_path):
        """Test that cache hit skips scheduling completely."""
        output_file = tmp_path / "output.txt"
        
        cache = CrackedCache()
        test_hash = "a" * 32
        test_password = "050-0000000"
        
        # Put in cache
        cache.put(test_hash, test_password)
        
        registry = MinionRegistry(["http://localhost:8000"])
        
        from unittest.mock import AsyncMock, MagicMock
        
        mock_client = MagicMock(spec=MinionClient)
        mock_client.send_crack_request = AsyncMock()
        
        job_manager = JobManager(cache)
        scheduler = Scheduler(
            registry=registry,
            client=mock_client,
            job_manager=job_manager,
            output_file=str(output_file)
        )
        
        # Create job (should be DONE immediately due to cache)
        job = job_manager.create_job(test_hash)
        
        assert job.status == JobStatus.DONE
        assert job.password_found == test_password
        
        # Process job
        await scheduler.process_job(job)
        
        # Should NOT call minion (cache hit)
        mock_client.send_crack_request.assert_not_called()
        
        # But should write output
        assert output_file.exists()
        content = output_file.read_text()
        assert test_hash in content
        assert test_password in content
    
    @pytest.mark.asyncio
    async def test_e2e_multiple_jobs_sequential(self, tmp_path):
        """Test processing multiple jobs sequentially."""
        output_file = tmp_path / "output.txt"
        
        cache = CrackedCache()
        registry = MinionRegistry(["http://localhost:8000"])
        
        from unittest.mock import AsyncMock, MagicMock
        from shared.domain.models import CrackResultPayload
        from shared.consts import ResultStatus
        
        mock_client = MagicMock(spec=MinionClient)
        mock_client.registry = registry
        
        # First job: FOUND
        test_password1 = "050-0000000"
        test_hash1 = hashlib.md5(test_password1.encode()).hexdigest().lower()
        
        # Second job: NOT_FOUND
        fake_hash2 = "b" * 32
        
        # Setup mock to return different results
        call_count = 0
        def mock_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CrackResultPayload(
                    status=ResultStatus.FOUND,
                    found_password=test_password1,
                    last_index_processed=0,
                    error_message=None
                )
            else:
                return CrackResultPayload(
                    status=ResultStatus.NOT_FOUND,
                    found_password=None,
                    last_index_processed=100,
                    error_message=None
                )
        
        mock_client.send_crack_request = AsyncMock(side_effect=mock_response)
        mock_client.send_cancel_job = AsyncMock()
        
        job_manager = JobManager(cache)
        scheduler = Scheduler(
            registry=registry,
            client=mock_client,
            job_manager=job_manager,
            output_file=str(output_file)
        )
        
        # Process first job
        job1 = job_manager.create_job(test_hash1)
        await scheduler.process_job(job1)
        
        # Process second job
        job2 = job_manager.create_job(fake_hash2)
        await scheduler.process_job(job2)
        
        # Verify both results in output
        content = output_file.read_text()
        lines = content.strip().split('\n')
        assert len(lines) == 2
        assert test_hash1 in lines[0]
        assert test_password1 in lines[0]
        assert fake_hash2 in lines[1]
        assert "NOT_FOUND" in lines[1]

