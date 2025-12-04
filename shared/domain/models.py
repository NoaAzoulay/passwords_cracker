"""Domain models for jobs, chunks, and payloads."""

from dataclasses import dataclass, field
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict
from shared.domain.status import JobStatus, ChunkStatus
from shared.domain.consts import PasswordSchemeName, HashAlgorithm


@dataclass
class WorkChunk:
    """Represents a chunk of work to be processed."""
    id: str
    job_id: str
    start_index: int
    end_index: int  # inclusive
    status: ChunkStatus = ChunkStatus.PENDING
    assigned_minion: Optional[str] = None
    last_index_processed: int = 0
    attempts: int = 0


@dataclass
class HashJob:
    """Represents a hash cracking job."""
    id: str
    hash_value: str  # lowercase
    hash_type: str
    scheme: str
    total_space_start: int
    total_space_end: int
    status: JobStatus = JobStatus.PENDING
    chunks: List[WorkChunk] = field(default_factory=list)
    password_found: Optional[str] = None
    
    def is_complete(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (JobStatus.DONE, JobStatus.CANCELLED, JobStatus.FAILED)


class RangeDict(BaseModel):
    """Range dictionary model."""
    start_index: int = Field(..., description="Start index (inclusive)", ge=0)
    end_index: int = Field(..., description="End index (inclusive)", ge=0)
    
    @model_validator(mode='after')
    def validate_range(self) -> 'RangeDict':
        """Validate that end_index >= start_index."""
        if self.end_index < self.start_index:
            raise ValueError(f"end_index ({self.end_index}) must be >= start_index ({self.start_index})")
        return self


class CrackRangePayload(BaseModel):
    """Payload for crack-range request."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "hash": "1d0b28c7e3ef0ba9d3c04a4183b576ac",
                "hash_type": HashAlgorithm.MD5,
                "password_scheme": PasswordSchemeName.IL_PHONE_05X_DASH,
                "range": {"start_index": 0, "end_index": 99999},
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "request_id": "abc123"
            }
        }
    )
    
    hash: str = Field(..., description="MD5 hash to crack")
    hash_type: str = Field(default=HashAlgorithm.MD5, description="Hash algorithm type")
    password_scheme: str = Field(..., description="Password scheme name")
    range: RangeDict = Field(..., description="Index range to search")
    job_id: str = Field(..., description="Job identifier")
    request_id: str = Field(..., description="Request identifier for tracing")


class CrackResultPayload(BaseModel):
    """Result payload from minion."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "FOUND",
                "found_password": "050-0000000",
                "last_index_processed": 0,
                "error_message": None
            }
        }
    )
    
    status: Literal["FOUND", "NOT_FOUND", "CANCELLED", "ERROR", "INVALID_INPUT"] = Field(
        ..., 
        description="Result status: FOUND, NOT_FOUND, CANCELLED, ERROR, or INVALID_INPUT"
    )
    found_password: Optional[str] = Field(None, description="Password if found")
    last_index_processed: int = Field(0, ge=0, description="Last index processed (must be >= 0)")
    error_message: Optional[str] = Field(None, description="Error message if status is ERROR")

