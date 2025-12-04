"""Constants to avoid string typos and magic numbers."""

from enum import Enum
from typing import Literal


class ResultStatus(str, Enum):
    """Result status constants."""
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    INVALID_INPUT = "INVALID_INPUT"


# Type alias for result status literals
ResultStatusLiteral = Literal["FOUND", "NOT_FOUND", "CANCELLED", "ERROR", "INVALID_INPUT"]


class PasswordSchemeName(str, Enum):
    """Password scheme name constants."""
    IL_PHONE_05X_DASH = "il_phone_05x_dash"


class HashAlgorithm:
    """Hash algorithm constants."""
    MD5 = "md5"
    
    # Hash length constants
    MD5_LENGTH = 32  # MD5 hash is 32 hex characters


class HashDisplay:
    """Constants for hash display."""
    PREFIX_LENGTH = 8  # Number of characters to show in logs (e.g., "1d0b28c7...")


class CancelJobFields:
    """Field names for cancel job request."""
    JOB_ID = "job_id"


class CancelJobResponseFields:
    """JSON field names for cancel-job responses."""
    STATUS = "status"
    ERROR = "error"


class CancelJobResponseStatus(str, Enum):
    """Status values for cancel-job responses."""
    OK = "OK"
    ERROR = "ERROR"


class CancelJobResponse:
    """
    Backwards-compatible wrapper for cancel-job response constants (deprecated).
    
    Use CancelJobResponseFields and CancelJobResponseStatus instead.
    """
    STATUS = CancelJobResponseFields.STATUS
    ERROR = CancelJobResponseFields.ERROR
    
    class Status:
        OK = CancelJobResponseStatus.OK
        ERROR = CancelJobResponseStatus.ERROR


class OutputStatus:
    """Output status strings."""
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"

