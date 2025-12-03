"""Cancellation registry for minion-side job cancellation."""


class CancellationRegistry:
    """Process-wide singleton for tracking cancelled jobs."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs = set()
        return cls._instance
    
    def cancel(self, job_id: str) -> None:
        """Mark a job as cancelled."""
        self._jobs.add(job_id)
    
    def is_cancelled(self, job_id: str) -> bool:
        """Check if a job is cancelled."""
        return job_id in self._jobs

