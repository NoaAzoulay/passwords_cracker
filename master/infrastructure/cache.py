"""Cache for cracked passwords."""

import logging
from typing import Optional
from shared.consts import HashDisplay

logger = logging.getLogger(__name__)


class CrackedCache:
    """In-memory cache for cracked passwords."""
    
    def __init__(self):
        self._cache: dict[str, str] = {}
    
    def get(self, hash_value: str) -> Optional[str]:
        """Get password for hash if cached."""
        # Normalize to lowercase
        key = hash_value.lower()
        return self._cache.get(key)
    
    def put(self, hash_value: str, password: str) -> None:
        """Store password for hash."""
        # Normalize to lowercase
        key = hash_value.lower()
        self._cache[key] = password
        logger.debug(f"Cached password for hash {key[:HashDisplay.PREFIX_LENGTH]}...")

