"""Tests for CrackedCache functionality."""

import pytest
from master.infrastructure.cache import CrackedCache


class TestCrackedCache:
    """Tests for password cache."""
    
    def test_cache_empty_initially(self):
        """Test that cache starts empty."""
        cache = CrackedCache()
        assert cache.get("a" * 32) is None
    
    def test_cache_put_and_get(self):
        """Test basic cache put and get operations."""
        cache = CrackedCache()
        hash_value = "a" * 32
        password = "050-0000000"
        
        cache.put(hash_value, password)
        assert cache.get(hash_value) == password
    
    def test_cache_case_insensitive_hash(self):
        """Test that cache is case-insensitive for hashes."""
        cache = CrackedCache()
        hash_upper = "A" * 32
        hash_lower = "a" * 32
        password = "050-0000000"
        
        # Put with uppercase
        cache.put(hash_upper, password)
        
        # Get with lowercase should work
        assert cache.get(hash_lower) == password
        
        # Get with uppercase should also work
        assert cache.get(hash_upper) == password
    
    def test_cache_overwrite_existing_entry(self):
        """Test that cache overwrites existing entries."""
        cache = CrackedCache()
        hash_value = "a" * 32
        
        cache.put(hash_value, "050-0000000")
        assert cache.get(hash_value) == "050-0000000"
        
        cache.put(hash_value, "050-0000001")
        assert cache.get(hash_value) == "050-0000001"
    
    def test_cache_multiple_entries(self):
        """Test that cache can store multiple entries independently."""
        cache = CrackedCache()
        
        cache.put("a" * 32, "050-0000000")
        cache.put("b" * 32, "050-0000001")
        cache.put("c" * 32, "050-0000002")
        
        assert cache.get("a" * 32) == "050-0000000"
        assert cache.get("b" * 32) == "050-0000001"
        assert cache.get("c" * 32) == "050-0000002"
    
    def test_cache_get_nonexistent_returns_none(self):
        """Test that getting non-existent hash returns None."""
        cache = CrackedCache()
        cache.put("a" * 32, "050-0000000")
        
        assert cache.get("b" * 32) is None
        assert cache.get("c" * 32) is None
    
    def test_cache_normalizes_to_lowercase(self):
        """Test that cache normalizes all hashes to lowercase."""
        cache = CrackedCache()
        
        # Put with mixed case
        cache.put("AbCdEf" * 5 + "AbCd", "050-0000000")
        
        # Get with different case should work
        assert cache.get("abcdef" * 5 + "abcd") == "050-0000000"
        assert cache.get("ABCDEF" * 5 + "ABCD") == "050-0000000"
        assert cache.get("AbCdEf" * 5 + "AbCd") == "050-0000000"
    
    def test_cache_clear(self):
        """Test that clear() removes all cached entries."""
        cache = CrackedCache()
        
        # Add some entries
        cache.put("a" * 32, "050-0000000")
        cache.put("b" * 32, "050-0000001")
        cache.put("c" * 32, "050-0000002")
        
        # Verify entries exist
        assert cache.get("a" * 32) == "050-0000000"
        assert cache.get("b" * 32) == "050-0000001"
        assert cache.get("c" * 32) == "050-0000002"
        
        # Clear cache
        cache.clear()
        
        # Verify all entries are gone
        assert cache.get("a" * 32) is None
        assert cache.get("b" * 32) is None
        assert cache.get("c" * 32) is None
    
    def test_cache_clear_empty_cache(self):
        """Test that clear() on empty cache does not raise."""
        cache = CrackedCache()
        
        # Should not raise
        cache.clear()
        
        # Cache should still be empty
        assert cache.get("a" * 32) is None
    
    def test_cache_clear_preserves_case_normalization(self):
        """Test that clearing does not break case normalization behavior."""
        cache = CrackedCache()
        
        # Add entry with uppercase
        cache.put("A" * 32, "050-0000000")
        assert cache.get("a" * 32) == "050-0000000"
        
        # Clear cache
        cache.clear()
        
        # Add new entry with lowercase
        cache.put("a" * 32, "050-0000001")
        
        # Should still work with case-insensitive lookup
        assert cache.get("A" * 32) == "050-0000001"
        assert cache.get("a" * 32) == "050-0000001"
    
    def test_cache_clear_allows_reuse(self):
        """Test that cache can be used normally after clearing."""
        cache = CrackedCache()
        
        # Add and clear
        cache.put("a" * 32, "050-0000000")
        cache.clear()
        
        # Should be able to add new entries
        cache.put("b" * 32, "050-0000001")
        assert cache.get("b" * 32) == "050-0000001"
        
        # Old entry should still be gone
        assert cache.get("a" * 32) is None


