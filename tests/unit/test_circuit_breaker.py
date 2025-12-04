"""Tests for circuit breaker behavior."""

import pytest
from unittest.mock import patch
from master.infrastructure.circuit_breaker import MiniCircuitBreaker
from shared.config.config import config


class TestMiniCircuitBreaker:
    """Tests for circuit breaker functionality."""
    
    def test_initial_state_closed(self):
        """Test that circuit breaker starts in closed state."""
        breaker = MiniCircuitBreaker()
        assert breaker.is_unavailable() is False
        assert breaker.failure_count == 0
        assert breaker.opened_until is None
    
    def test_success_resets_failure_count(self):
        """Test that success resets failure count."""
        breaker = MiniCircuitBreaker()
        
        # Record some failures
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2
        
        # Record success
        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.is_unavailable() is False
        assert breaker.opened_until is None
    
    def test_failure_increments_count(self):
        """Test that failures increment the count."""
        breaker = MiniCircuitBreaker()
        
        for i in range(1, 5):
            breaker.record_failure()
            assert breaker.failure_count == i
    
    def test_breaker_opens_after_threshold(self):
        """Test that breaker becomes unavailable after MINION_FAILURE_THRESHOLD failures."""
        breaker = MiniCircuitBreaker()
        threshold = config.MINION_FAILURE_THRESHOLD
        
        # Record failures up to threshold
        for i in range(threshold - 1):
            breaker.record_failure()
            assert breaker.is_unavailable() is False
        
        # One more failure should make it unavailable
        breaker.record_failure()
        assert breaker.is_unavailable() is True
        assert breaker.failure_count >= threshold
        assert breaker.opened_until is not None
    
    def test_breaker_resets_after_window_expires(self):
        """Test that breaker resets after unavailable window expires."""
        breaker = MiniCircuitBreaker()
        threshold = config.MINION_FAILURE_THRESHOLD
        window = config.MINION_BREAKER_OPEN_SECONDS
        
        # Mock time to speed up test (instead of waiting 10+ seconds)
        with patch('master.infrastructure.circuit_breaker.time.time') as mock_time:
            # Set initial time
            current_time = 1000.0
            mock_time.return_value = current_time
            
            # Make the breaker unavailable
            for _ in range(threshold):
                breaker.record_failure()
            
            assert breaker.is_unavailable() is True
            
            # Fast-forward time past the window
            current_time += window + 0.1
            mock_time.return_value = current_time
            
            # Should be available now (is_unavailable checks and resets)
            assert breaker.is_unavailable() is False
            assert breaker.failure_count == 0
            assert breaker.opened_until is None
    
    def test_success_before_threshold_keeps_closed(self):
        """Test that success before threshold keeps breaker available."""
        breaker = MiniCircuitBreaker()
        threshold = config.MINION_FAILURE_THRESHOLD
        
        # Record some failures (but not enough to make unavailable)
        for _ in range(threshold - 1):
            breaker.record_failure()
        
        assert breaker.is_unavailable() is False
        
        # Record success
        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.is_unavailable() is False
    
    def test_not_found_does_not_count_as_failure(self):
        """Test that NOT_FOUND is treated as success (not failure)."""
        # This is tested implicitly - NOT_FOUND should call record_success
        # The actual behavior is in MinionClient, but breaker should handle success
        breaker = MiniCircuitBreaker()
        
        # Record some failures
        breaker.record_failure()
        breaker.record_failure()
        
        # Record success (simulating NOT_FOUND)
        breaker.record_success()
        
        # Should reset
        assert breaker.failure_count == 0
        assert breaker.is_open() is False
    
    def test_multiple_opens_and_resets(self):
        """Test that breaker can become unavailable and reset multiple times."""
        breaker = MiniCircuitBreaker()
        threshold = config.MINION_FAILURE_THRESHOLD
        window = config.MINION_BREAKER_OPEN_SECONDS
        
        # Mock time to speed up test (instead of waiting 10+ seconds)
        with patch('master.infrastructure.circuit_breaker.time.time') as mock_time:
            # Set initial time
            current_time = 1000.0
            mock_time.return_value = current_time
            
            # Make breaker unavailable
            for _ in range(threshold):
                breaker.record_failure()
            assert breaker.is_unavailable() is True
            
            # Fast-forward time past the window
            current_time += window + 0.1
            mock_time.return_value = current_time
            
            # Should be available now (is_unavailable checks and resets)
            assert breaker.is_unavailable() is False
            
            # Make unavailable again
            for _ in range(threshold):
                breaker.record_failure()
            assert breaker.is_unavailable() is True

