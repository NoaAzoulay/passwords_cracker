"""Worker logic for cracking passwords."""

import hashlib
import logging
from shared.domain.models import CrackResultPayload
from shared.config.config import config
from shared.interfaces.password_scheme import PasswordScheme
from shared.consts import ResultStatus, HashDisplay
from minion.infrastructure.cancellation import CancellationRegistry

logger = logging.getLogger(__name__)


def crack_range(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
) -> CrackResultPayload:
    """
    Crack password in the given range.
    
    Performance optimizations:
    - Pre-compute cancellation check interval
    - Normalize target hash once
    - Direct MD5 computation without intermediate variables
    - Automatic parallel processing if WORKER_THREADS > 1
    
    Args:
        target_hash: MD5 hash to find (will be normalized to lowercase)
        scheme: Password scheme
        start_index: Start index (inclusive)
        end_index: End index (inclusive)
        job_id: Job ID for cancellation checks
    
    Returns:
        CrackResultPayload with status and result
    """
    # Use parallel processing if enabled
    if config.WORKER_THREADS > 1:
        try:
            from minion.services.worker_parallel import crack_range as parallel_crack_range
            return parallel_crack_range(target_hash, scheme, start_index, end_index, job_id)
        except ImportError:
            logger.debug("Parallel worker not available, using sequential mode")
        except Exception as e:
            logger.warning(f"Parallel processing failed, falling back to sequential: {e}")
    
    # Sequential processing (optimized)
    cancellation_registry = CancellationRegistry()
    
    # Normalize hash to lowercase once (not in loop)
    target_hash = target_hash.lower()
    
    # Pre-compute cancellation check interval (avoid repeated config access)
    check_interval = config.CANCELLATION_CHECK_EVERY
    
    try:
        for i in range(start_index, end_index + 1):
            # Check cancellation every N iterations (optimized: check interval once)
            if i % check_interval == 0:
                if cancellation_registry.is_cancelled(job_id):
                    logger.info(f"Job {job_id} cancelled at index {i}")
                    return CrackResultPayload(
                        status=ResultStatus.CANCELLED,
                        found_password=None,
                        last_index_processed=i,
                        error_message=None,
                    )
            
            # Generate password and compute hash
            password = scheme.index_to_password(i)
            # Compute hash and compare (both already lowercase)
            if hashlib.md5(password.encode()).hexdigest().lower() == target_hash:
                logger.info(
                    f"Password found for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
                    f"at index {i}: {password}"
                )
                return CrackResultPayload(
                    status=ResultStatus.FOUND,
                    found_password=password,
                    last_index_processed=i,
                    error_message=None,
                )
        
        # Not found in range
        return CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=end_index,
            error_message=None,
        )
    
    except Exception as e:
        logger.error(f"Error in crack_range for job {job_id}: {e}", exc_info=True)
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=start_index,
            error_message=str(e),
        )

