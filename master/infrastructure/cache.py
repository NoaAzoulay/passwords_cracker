"""Cache for cracked passwords."""

from typing import Optional


class CrackedCache:
    """
    Simple in-memory cache mapping hash -> password.
    
    Cache lives for the lifetime of the master process.
    No automatic cleaning or eviction logic.
    """
    
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
    
    def get(self, hash_value: str) -> Optional[str]:
        """Get password for hash if cached."""
        key = hash_value.lower()
        return self._cache.get(key)
    
    def put(self, hash_value: str, password: str) -> None:
        """Store password for hash in cache."""
        key = hash_value.lower()
        self._cache[key] = password
    
    def clear(self) -> None:
        """Remove all cached entries."""
        self._cache.clear()

