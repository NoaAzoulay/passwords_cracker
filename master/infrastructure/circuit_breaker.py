"""Circuit breaker for minion failure handling."""

import time
import logging
from typing import Optional
from shared.config.config import config

logger = logging.getLogger(__name__)


class MiniCircuitBreaker:
    """Simple circuit breaker per minion."""
    
    def __init__(self):
        self.failure_count = 0
        self.opened_until: Optional[float] = None
    
    def record_success(self) -> None:
        """Record successful request."""
        if self.failure_count > 0:
            logger.info(f"Circuit breaker: resetting failure count (was {self.failure_count})")
        self.failure_count = 0
        self.opened_until = None
    
    def record_failure(self) -> None:
        """Record failed request."""
        self.failure_count += 1
        logger.debug(f"Circuit breaker: failure count = {self.failure_count}")
        
        if self.failure_count >= config.MINION_FAILURE_THRESHOLD:
            self.opened_until = time.time() + config.MINION_BREAKER_OPEN_SECONDS
            logger.warning(
                f"Circuit breaker: OPENED (failures: {self.failure_count}, "
                f"will reset in {config.MINION_BREAKER_OPEN_SECONDS}s)"
            )
    
    def is_unavailable(self) -> bool:
        """Check if circuit breaker is unavailable (open due to failures)."""
        if self.opened_until is None:
            return False
        
        if time.time() >= self.opened_until:
            # Window passed, reset
            logger.info("Circuit breaker: AVAILABLE (window expired)")
            self.failure_count = 0
            self.opened_until = None
            return False
        
        return True
    
    def is_open(self) -> bool:
        """Check if circuit breaker is open (deprecated, use is_unavailable for clarity)."""
        return self.is_unavailable()

