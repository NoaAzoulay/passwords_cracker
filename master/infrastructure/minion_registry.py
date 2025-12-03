"""Registry for managing minions with round-robin scheduling."""

import logging
from typing import Optional
from master.infrastructure.circuit_breaker import MiniCircuitBreaker

logger = logging.getLogger(__name__)


class MinionRegistry:
    """Round-robin minion registry with circuit breaker support."""
    
    def __init__(self, minion_urls: list[str]):
        self.minions = minion_urls
        self.breakers: dict[str, MiniCircuitBreaker] = {
            url: MiniCircuitBreaker() for url in minion_urls
        }
        self._current_index = 0
    
    def pick_next(self) -> Optional[str]:
        """
        Pick next available minion (circuit breaker closed).
        Returns None if all minions are unavailable.
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
                return minion_url
            
            attempts += 1
        
        # All minions are unavailable
        logger.debug("All minions unavailable (circuit breakers unavailable)")
        return None
    
    def get_breaker(self, minion_url: str) -> MiniCircuitBreaker:
        """Get circuit breaker for a minion."""
        return self.breakers[minion_url]
    
    def all_minions(self) -> list[str]:
        """Return all minion URLs."""
        return self.minions.copy()

