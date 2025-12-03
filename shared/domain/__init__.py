"""Domain models and entities."""

from shared.domain.models import HashJob, WorkChunk, CrackRangePayload, CrackResultPayload, RangeDict
from shared.domain.status import JobStatus, ChunkStatus, BaseStatus

__all__ = [
    "HashJob",
    "WorkChunk",
    "CrackRangePayload",
    "CrackResultPayload",
    "RangeDict",
    "JobStatus",
    "ChunkStatus",
    "BaseStatus",
]
