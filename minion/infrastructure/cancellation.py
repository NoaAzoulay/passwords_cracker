"""Cancellation registry for minion-side job cancellation."""

import threading
import logging
from typing import Set

logger = logging.getLogger(__name__)


class CancellationRegistry:
    """
    Process-wide singleton for tracking cancelled jobs.
    
    All instances of this class share the same internal state via class-level
    attributes. This ensures that:
    - `cancel(job_id)` called in one place (e.g., `/cancel-job` endpoint)
    - Is immediately visible to `is_cancelled(job_id)` in any other place
      (e.g., worker threads, including parallel subranges)
    
    Thread-safe using a lock for all operations. This is a true singleton:
    every call to `CancellationRegistry()` returns an object that shares
    the same underlying storage.
    
    Example:
        registry1 = CancellationRegistry()
        registry2 = CancellationRegistry()
        registry1.cancel("job-123")
        assert registry2.is_cancelled("job-123")  # True - shared state
    """
    
    # Class-level storage (shared across all instances in the process)
    # This ensures singleton behavior: all instances share the same set
    _cancelled_jobs: Set[str] = set()
    _lock = threading.Lock()
    
    def cancel(self, job_id: str) -> None:
        """
        Mark a job as cancelled.
        
        This is idempotent: calling multiple times with the same job_id
        has no additional effect.
        """
        with self._lock:
            self._cancelled_jobs.add(job_id)
            logger.debug(f"Job {job_id} marked as cancelled")
    
    def is_cancelled(self, job_id: str) -> bool:
        """
        Check if a job is cancelled.
        
        Returns:
            True if job is cancelled, False otherwise.
        """
        with self._lock:
            return job_id in self._cancelled_jobs
