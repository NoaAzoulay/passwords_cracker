"""Registry for managing minions with round-robin scheduling."""

import logging
from typing import Optional
from master.infrastructure.circuit_breaker import MiniCircuitBreaker

logger = logging.getLogger(__name__)


class MinionRegistry:
    """
    Round-robin minion registry with circuit breaker support.
    
    Manages a list of minion URLs and their associated circuit breakers.
    Provides methods to pick available minions and query their availability.
    
    Thread-safety: This class is shared across all jobs. Circuit breakers are
    per-minion and use internal state, but operations are async and the registry
    itself is designed for concurrent access. Safe for concurrent use across
    multiple async tasks processing different hashes.
    """
    
    def __init__(self, minion_urls: list[str]) -> None:
        """
        Initialize registry with minion URLs.
        """
        self.minions: list[str] = minion_urls
        self.breakers: dict[str, MiniCircuitBreaker] = {
            url: MiniCircuitBreaker() for url in minion_urls
        }
        self._current_index: int = 0
    
    def pick_next(self) -> Optional[str]:
        """
        Pick next available minion (circuit breaker closed) using round-robin.
        
        Returns:
            Next available minion URL, or None if all minions are unavailable.
        """
        if not self.minions:
            return None
        
        start_index = self._current_index
        attempts = 0
        
        while attempts < len(self.minions):
            minion_url = self.minions[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.minions)
            
            breaker = self.breakers[minion_url]
            if not breaker.is_unavailable():
                logger.debug(f"Picked minion {minion_url} (round-robin)")
                return minion_url
            
            attempts += 1
        
        # All minions are unavailable
        logger.debug("All minions unavailable (circuit breakers open)")
        return None
    
    def get_available_minions(self) -> list[str]:
        """
        Get all minions with closed circuit breakers.
        
        Returns:
            List of available minion URLs (circuit breaker closed).
        """
        available = [
            url for url in self.minions
            if not self.breakers[url].is_unavailable()
        ]
        logger.debug(f"Found {len(available)}/{len(self.minions)} available minions")
        return available
    
    def get_breaker(self, minion_url: str) -> MiniCircuitBreaker:
        """
        Get circuit breaker for a minion.
        
        Returns:
            MiniCircuitBreaker instance for the minion.
        """
        return self.breakers[minion_url]
    
    def all_minions(self) -> list[str]:
        """
        Return all minion URLs (regardless of availability).
        
        Returns:
            Copy of all minion URLs.
        """
        return self.minions.copy()


