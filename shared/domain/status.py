"""Status enums for jobs and chunks."""

from enum import Enum


class BaseStatus(str, Enum):
    """Base status enum."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


# For Python 3.13 compatibility, use type aliases instead of inheritance
JobStatus = BaseStatus
ChunkStatus = BaseStatus


