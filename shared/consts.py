"""Constants to avoid string typos and magic numbers."""

from enum import Enum


class ResultStatus(str, Enum):
    """Result status constants."""
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class PasswordSchemeName:
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


class CancelJobResponse:
    """Response fields for cancel job."""
    STATUS = "status"
    ERROR = "error"
    
    class Status:
        OK = "OK"
        ERROR = "ERROR"


class OutputStatus:
    """Output status strings."""
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"

