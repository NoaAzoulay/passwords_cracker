"""Tests for MinionRegistry round-robin behavior."""

import pytest
from master.infrastructure.minion_registry import MinionRegistry
from master.infrastructure.circuit_breaker import MiniCircuitBreaker


class TestMinionRegistry:
    """Tests for minion registry functionality."""
    
    def test_registry_creation(self):
        """Test creating a MinionRegistry."""
        urls = ["http://minion1:8000", "http://minion2:8000"]
        registry = MinionRegistry(urls)
        
        # Check that all minions are registered
        all_minions = registry.all_minions()
        assert len(all_minions) == 2
        assert "http://minion1:8000" in all_minions
        assert "http://minion2:8000" in all_minions
        
        # Check that breakers exist for each
        for url in urls:
            breaker = registry.get_breaker(url)
            assert breaker is not None
    
    def test_pick_next_round_robin(self):
        """Test that pick_next uses round-robin scheduling."""
        urls = ["http://minion1:8000", "http://minion2:8000", "http://minion3:8000"]
        registry = MinionRegistry(urls)
        
        # Should cycle through minions
        picks = [registry.pick_next() for _ in range(6)]
        
        # Should cycle: minion1, minion2, minion3, minion1, minion2, minion3
        assert picks[0] == urls[0]
        assert picks[1] == urls[1]
        assert picks[2] == urls[2]
        assert picks[3] == urls[0]
        assert picks[4] == urls[1]
        assert picks[5] == urls[2]
    
    def test_pick_next_skips_unavailable_breakers(self):
        """Test that pick_next skips minions with unavailable circuit breakers."""
        urls = ["http://minion1:8000", "http://minion2:8000", "http://minion3:8000"]
        registry = MinionRegistry(urls)
        
        # Make breaker unavailable for minion1
        breaker1 = registry.get_breaker(urls[0])
        for _ in range(3):  # Make the breaker unavailable
            breaker1.record_failure()
        
        assert breaker1.is_unavailable() is True
        
        # pick_next should skip minion1 and return minion2
        picked = registry.pick_next()
        assert picked == urls[1] or picked == urls[2]
        assert picked != urls[0]
    
    def test_pick_next_returns_none_when_all_unavailable(self):
        """Test that pick_next returns None when all breakers are unavailable."""
        urls = ["http://minion1:8000", "http://minion2:8000"]
        registry = MinionRegistry(urls)
        
        # Make all breakers unavailable
        for url in urls:
            breaker = registry.get_breaker(url)
            for _ in range(3):
                breaker.record_failure()
        
        # All should be unavailable
        assert all(registry.get_breaker(url).is_unavailable() for url in urls)
        
        # pick_next should return None
        assert registry.pick_next() is None
    
    def test_pick_next_returns_available_after_reset(self):
        """Test that pick_next returns minion after breaker resets."""
        urls = ["http://minion1:8000"]
        registry = MinionRegistry(urls)
        
        # Make breaker unavailable
        breaker = registry.get_breaker(urls[0])
        for _ in range(3):
            breaker.record_failure()
        
        assert registry.pick_next() is None
        
        # Reset breaker
        breaker.record_success()
        
        # Should now return the minion
        assert registry.pick_next() == urls[0]
    
    def test_get_breaker_returns_correct_breaker(self):
        """Test that get_breaker returns the correct breaker for a minion."""
        urls = ["http://minion1:8000", "http://minion2:8000"]
        registry = MinionRegistry(urls)
        
        breaker1 = registry.get_breaker(urls[0])
        breaker2 = registry.get_breaker(urls[1])
        
        assert breaker1 is not breaker2
        assert isinstance(breaker1, MiniCircuitBreaker)
        assert isinstance(breaker2, MiniCircuitBreaker)
    
    def test_all_minions_returns_copy(self):
        """Test that all_minions returns a copy of the list."""
        urls = ["http://minion1:8000", "http://minion2:8000"]
        registry = MinionRegistry(urls)
        
        all_urls = registry.all_minions()
        
        # Should return the same URLs
        assert all_urls == urls
        
        # Modifying the copy shouldn't affect registry (if it's a copy)
        original_count = len(all_urls)
        all_urls.append("http://minion3:8000")
        # The registry should still have original count (implementation dependent)
        assert len(registry.all_minions()) == original_count
    
    def test_empty_registry_returns_none(self):
        """Test that empty registry returns None."""
        registry = MinionRegistry([])
        assert registry.pick_next() is None

