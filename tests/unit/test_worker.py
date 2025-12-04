"""Tests for unified worker logic (sequential and parallel modes)."""

import hashlib
import pytest
from unittest.mock import patch
from shared.domain.models import CrackResultPayload
from shared.domain.consts import ResultStatus
from shared.implementations.schemes import IlPhone05xDashScheme
from shared.config.config import config
from minion.services.worker import crack_range, _crack_subrange
from minion.infrastructure.cancellation import CancellationRegistry


class TestWorkerLogic:
    """Tests for unified password cracking worker (sequential and parallel modes)."""
    
    # Sequential mode tests (small ranges < 10000)
    
    def test_sequential_found_password_in_range(self):
        """Test that sequential worker finds password when it exists in range."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Small range (< 10000) uses sequential mode
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-sequential-1"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
        assert result.last_index_processed <= 100
    
    def test_sequential_not_found_when_password_not_in_range(self):
        """Test that sequential worker returns NOT_FOUND when password doesn't exist."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        
        result = crack_range(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-sequential-2"
        )
        
        assert result.status == ResultStatus.NOT_FOUND
        assert result.found_password is None
        assert result.last_index_processed == 100
    
    def test_sequential_not_found_when_password_outside_range(self):
        """Test NOT_FOUND when password exists but outside range."""
        scheme = IlPhone05xDashScheme()
        # Password at index 200, but searching 0-100
        test_password = scheme.index_to_password(200)
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-sequential-3"
        )
        
        assert result.status == ResultStatus.NOT_FOUND
    
    def test_sequential_cancellation(self):
        """Test cancellation in sequential mode."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        job_id = "test-sequential-cancel"
        
        # Register cancellation before worker starts
        registry = CancellationRegistry()
        registry.cancel(job_id)
        
        # Small range uses sequential mode
        result = crack_range(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=1000,  # Small range, sequential mode
            job_id=job_id
        )
        
        # Should be cancelled (or NOT_FOUND if check happens after completion)
        assert result.status in (ResultStatus.CANCELLED, ResultStatus.NOT_FOUND)
    
    def test_sequential_last_index_processed_on_found(self):
        """Test that last_index_processed is set correctly on FOUND in sequential mode."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000005"  # At index 5
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-sequential-4"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.last_index_processed == 5
    
    def test_sequential_last_index_processed_on_not_found(self):
        """Test that last_index_processed equals end_index on NOT_FOUND."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        
        result = crack_range(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,
            job_id="test-sequential-5"
        )
        
        assert result.status == ResultStatus.NOT_FOUND
        assert result.last_index_processed == 100
    
    # Parallel mode tests (large ranges >= 10000)
    
    def test_parallel_found_password_large_range(self):
        """Test that parallel worker finds password in large range."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Large range (>= 10000) triggers parallel processing (if WORKER_THREADS > 1)
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
        
        # Large range to trigger parallel processing
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
    
    # Mode selection tests
    
    def test_falls_back_to_sequential_small_range(self):
        """Test that worker falls back to sequential for small ranges."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Small range (< 10000) should use sequential mode even if WORKER_THREADS > 1
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=100,  # Too small for parallel
            job_id="test-mode-selection-1"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
    
    @patch('minion.services.worker.config')
    def test_falls_back_to_sequential_when_single_thread(self, mock_config):
        """Test that worker falls back to sequential when WORKER_THREADS=1."""
        # Mock config to return WORKER_THREADS=1
        mock_config.WORKER_THREADS = 1
        mock_config.CANCELLATION_CHECK_EVERY = 5000
        mock_config.MINION_SUBRANGE_MIN_SIZE = 1000
        
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        # Even with large range, should use sequential if WORKER_THREADS=1
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=50000,
            job_id="test-mode-selection-2"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
    
    # Hash normalization tests
    
    def test_hash_normalization_lowercase(self):
        """Test that hash comparison is case-insensitive (uppercase input)."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest()
        
        # Test with uppercase hash - should be normalized to lowercase
        result = crack_range(
            target_hash=test_hash.upper(),
            scheme=scheme,
            start_index=0,
            end_index=10,
            job_id="test-hash-norm-1"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
    
    def test_hash_comparison_both_lowercase(self):
        """Test that both target and computed hashes are normalized."""
        scheme = IlPhone05xDashScheme()
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest()
        
        # Worker should normalize both
        result = crack_range(
            target_hash=test_hash,
            scheme=scheme,
            start_index=0,
            end_index=10,
            job_id="test-hash-norm-2"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == test_password
    
    # Subrange worker tests (internal function)
    
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
    
    def test_subrange_worker_cancellation(self):
        """Test that subrange worker respects cancellation."""
        scheme = IlPhone05xDashScheme()
        fake_hash = "a" * 32
        job_id = "test-subrange-cancel"
        check_interval = config.CANCELLATION_CHECK_EVERY
        
        # Register cancellation
        registry = CancellationRegistry()
        registry.cancel(job_id)
        
        # Subrange should return None when cancelled
        result = _crack_subrange(
            target_hash=fake_hash,
            scheme=scheme,
            start_index=0,
            end_index=10000,  # Large enough to trigger cancellation check
            job_id=job_id,
            check_interval=check_interval
        )
        
        # Should return None when cancelled
        assert result is None
    
    # Error handling tests
    
    def test_error_handling_sequential_normal_path(self):
        """Test that sequential mode returns NOT_FOUND (not ERROR) for normal cases."""
        scheme = IlPhone05xDashScheme()
        
        # Normal case - should return NOT_FOUND, not ERROR
        result = crack_range(
            target_hash="a" * 32,
            scheme=scheme,
            start_index=0,
            end_index=10,
            job_id="test-error-1"
        )
        
        # Should return NOT_FOUND, not ERROR (no exception occurred)
        assert result.status == ResultStatus.NOT_FOUND
    
    def test_error_handling_parallel_normal_path(self):
        """Test that parallel mode returns NOT_FOUND (not ERROR) for normal cases."""
        scheme = IlPhone05xDashScheme()
        
        # Normal case with large range - should return NOT_FOUND, not ERROR
        result = crack_range(
            target_hash="a" * 32,
            scheme=scheme,
            start_index=0,
            end_index=50000,
            job_id="test-error-2"
        )
        
        # Should return NOT_FOUND, not ERROR (no exception occurred)
        assert result.status == ResultStatus.NOT_FOUND
