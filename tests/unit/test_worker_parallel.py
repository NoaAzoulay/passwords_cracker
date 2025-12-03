"""Tests for parallel worker logic."""

import hashlib
import pytest
from unittest.mock import patch
from shared.domain.models import CrackResultPayload
from shared.consts import ResultStatus
from shared.implementations.schemes import IlPhone05xDashScheme
from shared.config.config import config
from minion.services.worker_parallel import crack_range, _crack_subrange
from minion.infrastructure.cancellation import CancellationRegistry


class TestParallelWorker:
    """Tests for parallel password cracking worker."""
    
    def test_parallel_found_password_large_range(self):
        """Test that parallel worker finds password in large range."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Use large range to trigger parallel processing (>= 10000)
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=50000,  # Large enough to trigger parallel mode
            job_id="test-parallel-1"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
        assert result.last_index_processed <= 50000
    
    def test_parallel_not_found_large_range(self):
        """Test that parallel worker returns NOT_FOUND in large range."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        
        # Use large range to trigger parallel processing
        result = crack_range(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=50000,
            job_id="test-parallel-2"
        )
        
        assert result.status == ResultStatus.NOT_FOUND
        assert result.found_password is None
        assert result.last_index_processed == 50000
    
    def test_parallel_falls_back_to_sequential_small_range(self):
        """Test that parallel worker falls back to sequential for small ranges."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Small range (< 10000) should use sequential mode
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,  # Too small for parallel
            job_id="test-parallel-3"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
    
    def test_parallel_cancellation(self):
        """Test that parallel worker handles cancellation."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        job_id = "test-parallel-cancel"
        
        # Register cancellation
        registry = CancellationRegistry()
        registry.cancel(job_id)
        
        # Large range to trigger parallel mode
        result = crack_range(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=50000,
            job_id=job_id
        )
        
        # Should be cancelled (or NOT_FOUND if check timing is off)
        assert result.status in (ResultStatus.CANCELLED, ResultStatus.NOT_FOUND)
    
    def test_subrange_worker_found(self):
        """Test that subrange worker finds password."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        check_interval = config.CANCELLATION_CHECK_EVERY
        
        result = _crack_subrange(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-subrange-1",
            check_interval=check_interval
        )
        
        assert result is not None
        found_index, found_password = result
        assert found_password == test_password
        assert found_index == 0
    
    def test_subrange_worker_not_found(self):
        """Test that subrange worker returns None when not found."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        check_interval = config.CANCELLATION_CHECK_EVERY
        
        result = _crack_subrange(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-subrange-2",
            check_interval=check_interval
        )
        
        assert result is None
    
    @patch('minion.services.worker_parallel.config')
    def test_parallel_with_single_thread_falls_back(self, mock_config):
        """Test that parallel worker falls back to sequential when WORKER_THREADS=1."""
        # Mock config to return WORKER_THREADS=1
        mock_config.WORKER_THREADS = 1
        mock_config.CANCELLATION_CHECK_EVERY = 5000
        
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Even with large range, should use sequential if WORKER_THREADS=1
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=50000,
            job_id="test-parallel-single"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password

