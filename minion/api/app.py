"""FastAPI application for minion service."""

import logging
import re
from fastapi import FastAPI, HTTPException
from shared.domain.models import CrackRangePayload, CrackResultPayload
from shared.domain.consts import (
    ResultStatus,
    HashAlgorithm,
    HashDisplay,
    CancelJobFields,
    CancelJobResponseFields,
    CancelJobResponseStatus,
)
from minion.services.worker import crack_range
from shared.factories.scheme_factory import create_scheme
from minion.infrastructure.cancellation import CancellationRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pentera Minion Service")


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint for Docker healthchecks.
    
    Returns:
        Dict with status "ok" if service is healthy.
    """
    return {"status": "ok"}


def validate_md5_hash(hash_value: str) -> bool:
    """
    Validate that hash is exactly 32 hex characters.
    
    Returns:
        True if valid MD5 hash format, False otherwise.
    """
    pattern = f"^[0-9a-f]{{{HashAlgorithm.MD5_LENGTH}}}$"
    return bool(re.match(pattern, hash_value.lower()))


@app.post("/crack-range", response_model=CrackResultPayload)
async def crack_range_endpoint(payload: CrackRangePayload) -> CrackResultPayload:
    """
    Crack password in the given range.
    
    Accepts a CrackRangePayload and returns a CrackResultPayload.
    Handles validation, scheme creation, and delegates to the unified worker.
    
    Returns:
        CrackResultPayload with result status and data.
        
    Raises:
        HTTPException: If validation fails (400 status).
    """
    try:
        # Validate hash format
        if not validate_md5_hash(payload.hash):
            return CrackResultPayload(
                status=ResultStatus.INVALID_INPUT,
                found_password=None,
                last_index_processed=payload.range.start_index,
                error_message=f"Invalid MD5 hash: must be {HashAlgorithm.MD5_LENGTH} hex characters."
            )
        
        # Log request
        logger.info(
            "Received crack-range request: job_id=%s, hash_prefix=%s, range=[%d, %d], scheme=%s",
            payload.job_id,
            payload.hash[:HashDisplay.PREFIX_LENGTH],
            payload.range.start_index,
            payload.range.end_index,
            payload.password_scheme,
        )
        
        # Create password scheme
        try:
            scheme = create_scheme(payload.password_scheme)
        except ValueError as e:
            return CrackResultPayload(
                status=ResultStatus.INVALID_INPUT,
                found_password=None,
                last_index_processed=payload.range.start_index,
                error_message=f"Unknown password scheme: {payload.password_scheme}"
            )
        
        # Validate range is within scheme bounds
        min_idx, max_idx = scheme.get_space_bounds()
        if payload.range.start_index < min_idx or payload.range.end_index > max_idx:
            return CrackResultPayload(
                status=ResultStatus.INVALID_INPUT,
                found_password=None,
                last_index_processed=payload.range.start_index,
                error_message=(
                    f"Range [{payload.range.start_index}, {payload.range.end_index}] "
                    f"is outside password scheme bounds [{min_idx}, {max_idx}]."
                ),
            )
        
        # Call unified worker (handles sequential/parallel automatically)
        result = crack_range(
            target_hash=payload.hash,
            scheme=scheme,
            start_index=payload.range.start_index,
            end_index=payload.range.end_index,
            job_id=payload.job_id,
        )
        
        # Return result (FastAPI handles JSON serialization)
        return result
    except Exception as e:
        # Log unexpected errors but return ERROR result instead of 500
        logger.error(
            f"Unexpected error in crack-range endpoint for job {payload.job_id}: {e}",
            exc_info=True,
        )
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=payload.range.start_index if payload else 0,
            error_message=str(e),
        )


@app.post("/cancel-job")
async def cancel_job_endpoint(request: dict) -> dict:
    """
    Cancel a job (best-effort, idempotent).
    
    Accepts a dict with job_id and marks the job as cancelled in the
    CancellationRegistry. This is idempotent: calling multiple times
    with the same job_id has no additional effect.
    
    Returns:
        Dict with status (OK or ERROR) and optional error message.
        
    Raises:
        HTTPException: If job_id is missing (400 status).
    """
    try:
        job_id = request.get(CancelJobFields.JOB_ID)
        if not job_id:
            raise HTTPException(
                status_code=400,
                detail="Missing job_id"
            )
        
        # Mark job as cancelled (idempotent)
        registry = CancellationRegistry()
        registry.cancel(job_id)
        
        logger.info(f"Cancellation requested for job_id={job_id}")
        
        return {
            CancelJobResponseFields.STATUS: CancelJobResponseStatus.OK,
            CancelJobResponseFields.ERROR: None,
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log error but return ERROR response instead of 500
        logger.error(
            f"Error cancelling job {request.get(CancelJobFields.JOB_ID, 'unknown')}: {e}",
            exc_info=True,
        )
        return {
            CancelJobResponseFields.STATUS: CancelJobResponseStatus.ERROR,
            CancelJobResponseFields.ERROR: str(e),
        }
