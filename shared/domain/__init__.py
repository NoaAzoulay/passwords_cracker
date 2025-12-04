"""Domain models and entities."""

from shared.domain.models import HashJob, WorkChunk, CrackRangePayload, CrackResultPayload, RangeDict
from shared.domain.status import JobStatus, ChunkStatus, BaseStatus
from shared.domain.consts import (
    ResultStatus,
    ResultStatusLiteral,
    PasswordSchemeName,
    HashAlgorithm,
    HashDisplay,
    CancelJobFields,
    CancelJobResponseFields,
    CancelJobResponseStatus,
    CancelJobResponse,
    OutputStatus,
)

__all__ = [
    "HashJob",
    "WorkChunk",
    "CrackRangePayload",
    "CrackResultPayload",
    "RangeDict",
    "JobStatus",
    "ChunkStatus",
    "BaseStatus",
    "ResultStatus",
    "ResultStatusLiteral",
    "PasswordSchemeName",
    "HashAlgorithm",
    "HashDisplay",
    "CancelJobFields",
    "CancelJobResponseFields",
    "CancelJobResponseStatus",
    "CancelJobResponse",
    "OutputStatus",
]
