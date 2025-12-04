"""HTTP client for communicating with minions."""

import logging
import httpx
import uuid
from shared.config.config import config
from shared.domain.models import CrackRangePayload, CrackResultPayload, WorkChunk, RangeDict
from shared.domain.consts import ResultStatus, CancelJobFields, HashDisplay
from master.infrastructure.minion_registry import MinionRegistry

logger = logging.getLogger(__name__)


class MinionClient:
    """
    HTTP client for minion communication.
    
    Handles all HTTP requests to minions, including crack requests and
    cancellation. Integrates with circuit breakers for failure handling.
    """
    
    def __init__(self, registry: MinionRegistry) -> None:
        """
        Initialize minion client.
        """
        self.registry = registry
        self.client = httpx.AsyncClient(
            timeout=config.MINION_REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
    
    async def send_crack_request(
        self,
        minion_url: str,
        chunk: WorkChunk,
        hash_value: str,
        hash_type: str,
        password_scheme: str,
        job_id: str,
    ) -> CrackResultPayload:
        """
        Send crack request to minion.
        
        Returns:
            CrackResultPayload with result
        """
        breaker = self.registry.get_breaker(minion_url)
        request_id = str(uuid.uuid4())
        
        payload = CrackRangePayload(
            hash=hash_value,
            hash_type=hash_type,
            password_scheme=password_scheme,
            range=RangeDict(
                start_index=chunk.start_index,
                end_index=chunk.end_index,
            ),
            job_id=job_id,
            request_id=request_id,
        )
        
        try:
            logger.debug(
                f"Job {job_id[:8]}...: Sending request {request_id[:8]}... "
                f"to {minion_url} for chunk {chunk.id[:8]}... "
                f"range [{chunk.start_index}, {chunk.end_index}]"
            )
            
            response = await self.client.post(
                f"{minion_url}/crack-range",
                json=payload.model_dump()
            )
            response.raise_for_status()
            
            result = CrackResultPayload.model_validate(response.json())
            
            # Record success (even NOT_FOUND is a logical success)
            breaker.record_success()
            
            logger.debug(
                f"Job {job_id[:8]}...: Request {request_id[:8]}... "
                f"to {minion_url} completed with status {result.status}"
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(
                f"Job {job_id[:8]}...: HTTP error communicating with {minion_url} "
                f"for chunk {chunk.id[:8]}...: {e}"
            )
            breaker.record_failure()
            return CrackResultPayload(
                status=ResultStatus.ERROR,
                found_password=None,
                last_index_processed=chunk.start_index,
                error_message=f"HTTP error: {str(e)}",
            )
        except Exception as e:
            logger.error(
                f"Job {job_id[:8]}...: Unexpected error communicating with {minion_url} "
                f"for chunk {chunk.id[:8]}...: {e}",
                exc_info=True,
            )
            breaker.record_failure()
            return CrackResultPayload(
                status=ResultStatus.ERROR,
                found_password=None,
                last_index_processed=chunk.start_index,
                error_message=f"Unexpected error: {str(e)}",
            )
    
    async def send_cancel_job(self, minion_url: str, job_id: str) -> None:
        """
        Send cancel request to minion (best-effort, non-blocking).
        
        Network errors do not fail the job. This is called asynchronously
        and exceptions are caught and logged.
        """
        try:
            logger.debug(
                f"Job {job_id[:8]}...: Sending cancel request to {minion_url}"
            )
            await self.client.post(
                f"{minion_url}/cancel-job",
                json={CancelJobFields.JOB_ID: job_id},
                timeout=2.0,  # Shorter timeout for cancel
            )
            logger.debug(
                f"Job {job_id[:8]}...: Cancel request sent successfully to {minion_url}"
            )
        except Exception as e:
            # Best-effort: log but don't fail
            logger.debug(
                f"Job {job_id[:8]}...: Failed to send cancel to {minion_url}: {e}"
            )
    
    async def close(self) -> None:
        """
        Close HTTP client and cleanup resources.
        
        Should be called when done with the client to properly close connections.
        """
        await self.client.aclose()

