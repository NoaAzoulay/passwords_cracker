"""FastAPI application for minion service."""

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from shared.domain.models import CrackRangePayload, CrackResultPayload, RangeDict
from shared.config.config import config
from shared.consts import ResultStatus, CancelJobResponse, HashAlgorithm
from minion.services.worker import crack_range
from shared.factories.scheme_factory import create_scheme
from minion.infrastructure.cancellation import CancellationRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pentera Minion Service")


class CancelJobRequest(BaseModel):
    """Request to cancel a job."""
    job_id: str


@app.post("/crack-range", response_model=CrackResultPayload)
async def crack_range_endpoint(request: CrackRangePayload):
    """Crack password in the given range."""
    try:
        # Validate payload
        if not request.hash or len(request.hash) != HashAlgorithm.MD5_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid hash: must be {HashAlgorithm.MD5_LENGTH} hex characters"
            )
        
        # Range validation is handled by Pydantic's RangeDict model_validator
        # This check is redundant but kept for explicit error message
        
        # Create scheme
        scheme = create_scheme(request.password_scheme)
        
        # Normalize hash to lowercase
        target_hash = request.hash.lower()
        
        logger.info(
            f"Processing request {request.request_id} for job {request.job_id} "
            f"range [{request.range.start_index}, {request.range.end_index}]"
        )
        
        # Execute worker
        result = crack_range(
            target_hash=target_hash,
            scheme=scheme,
            start_index=request.range.start_index,
            end_index=request.range.end_index,
            job_id=request.job_id,
        )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in crack-range endpoint: {e}", exc_info=True)
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=0,
            error_message=str(e),
        )


@app.post("/cancel-job")
async def cancel_job_endpoint(request: CancelJobRequest):
    """Cancel a job (best-effort)."""
    try:
        registry = CancellationRegistry()
        registry.cancel(request.job_id)
        logger.info(f"Job {request.job_id} marked as cancelled")
        return {CancelJobResponse.STATUS: CancelJobResponse.Status.OK}
    except Exception as e:
        logger.error(f"Error cancelling job {request.job_id}: {e}", exc_info=True)
        return {
            CancelJobResponse.STATUS: CancelJobResponse.Status.ERROR,
            CancelJobResponse.ERROR: str(e)
        }

