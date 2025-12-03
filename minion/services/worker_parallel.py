"""Parallel worker logic for cracking passwords using multi-threading."""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple
from shared.domain.models import CrackResultPayload
from shared.config.config import config
from shared.interfaces.password_scheme import PasswordScheme
from shared.consts import ResultStatus, HashDisplay
from minion.infrastructure.cancellation import CancellationRegistry

logger = logging.getLogger(__name__)


def _crack_subrange(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
    check_interval: int,
) -> Optional[Tuple[int, str]]:
    """
    Crack password in a sub-range (used by parallel workers).
    
    Returns:
        (index, password) if found, None otherwise
    """
    cancellation_registry = CancellationRegistry()
    
    try:
        for i in range(start_index, end_index + 1):
            # Check cancellation (optimized: only check at intervals)
            if i % check_interval == 0:
                if cancellation_registry.is_cancelled(job_id):
                    return None  # Cancelled
            
            # Generate password and compute hash
            password = scheme.index_to_password(i)
            if hashlib.md5(password.encode()).hexdigest().lower() == target_hash:
                return (i, password)
        
        return None  # Not found
    except Exception:
        return None


def crack_range(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
) -> CrackResultPayload:
    """
    Crack password in the given range using parallel processing.
    
    Performance optimizations:
    - Multi-threaded processing within minion (configurable via WORKER_THREADS)
    - Pre-compute cancellation check interval
    - Normalize target hash once
    - Parallel sub-range processing
    
    Args:
        target_hash: MD5 hash to find (will be normalized to lowercase)
        scheme: Password scheme
        start_index: Start index (inclusive)
        end_index: End index (inclusive)
        job_id: Job ID for cancellation checks
    
    Returns:
        CrackResultPayload with status and result
    """
    # Normalize hash to lowercase once
    target_hash = target_hash.lower()
    
    # Pre-compute cancellation check interval
    check_interval = config.CANCELLATION_CHECK_EVERY
    
    # Get number of worker threads
    num_threads = max(1, config.WORKER_THREADS)
    range_size = end_index - start_index + 1
    
    # If range is small or single-threaded, use sequential processing
    if num_threads == 1 or range_size < 10000:
        return _crack_range_sequential(target_hash, scheme, start_index, end_index, job_id, check_interval)
    
    # Parallel processing: split range into sub-ranges
    subrange_size = max(1000, range_size // num_threads)  # At least 1000 indices per thread
    
    try:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            
            # Submit sub-ranges to thread pool
            current_start = start_index
            while current_start <= end_index:
                current_end = min(current_start + subrange_size - 1, end_index)
                
                future = executor.submit(
                    _crack_subrange,
                    target_hash,
                    scheme,
                    current_start,
                    current_end,
                    job_id,
                    check_interval,
                )
                futures.append((future, current_start, current_end))
                current_start = current_end + 1
            
            # Check results as they complete (use as_completed for faster response)
            cancellation_registry = CancellationRegistry()
            for future in as_completed([f[0] for f in futures]):
                # Check cancellation before processing result
                if cancellation_registry.is_cancelled(job_id):
                    logger.info(f"Job {job_id} cancelled during parallel processing")
                    # Cancel remaining futures
                    for f, _, _ in futures:
                        f.cancel()
                    return CrackResultPayload(
                        status=ResultStatus.CANCELLED,
                        found_password=None,
                        last_index_processed=start_index,
                        error_message=None,
                    )
                
                result = future.result()
                if result is not None:
                    # Password found! Cancel remaining futures
                    for f, _, _ in futures:
                        f.cancel()
                    found_index, found_password = result
                    logger.info(
                        f"Password found for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
                        f"at index {found_index}: {found_password}"
                    )
                    return CrackResultPayload(
                        status=ResultStatus.FOUND,
                        found_password=found_password,
                        last_index_processed=found_index,
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
        logger.error(f"Error in parallel crack_range for job {job_id}: {e}", exc_info=True)
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=start_index,
            error_message=str(e),
        )


def _crack_range_sequential(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
    check_interval: int,
) -> CrackResultPayload:
    """Sequential password cracking (fallback or single-threaded mode)."""
    cancellation_registry = CancellationRegistry()
    
    try:
        for i in range(start_index, end_index + 1):
            # Check cancellation every N iterations
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
        logger.error(f"Error in sequential crack_range for job {job_id}: {e}", exc_info=True)
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=start_index,
            error_message=str(e),
        )

