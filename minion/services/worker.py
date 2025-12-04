"""Unified worker logic for cracking passwords (sequential and parallel)."""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple
from shared.domain.models import CrackResultPayload
from shared.config.config import config
from shared.interfaces.password_scheme import PasswordScheme
from shared.domain.consts import ResultStatus, HashDisplay
from minion.infrastructure.cancellation import CancellationRegistry

logger = logging.getLogger(__name__)

# Threshold for switching to parallel mode (default: 10,000 indices)
PARALLEL_THRESHOLD = 10000


def crack_range(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
) -> CrackResultPayload:
    """
    Crack password in the given range (sequential or parallel based on config).
    
    This is the single entry point for password cracking on the minion side.
    Automatically chooses between sequential and parallel processing based on:
    - config.WORKER_THREADS (must be > 1 for parallel)
    - Range size (must be >= PARALLEL_THRESHOLD for parallel)
    
    Error handling:
    - Sequential mode: Any exception during processing returns ERROR status.
    - Parallel mode: Any exception in a subrange causes the entire operation
      to return ERROR status (instead of being silently treated as NOT_FOUND).
    
    Returns:
        CrackResultPayload with status (FOUND/NOT_FOUND/CANCELLED/ERROR) and result.
    """
    target_hash = target_hash.lower()
    
    # Read configuration
    check_interval = config.CANCELLATION_CHECK_EVERY
    num_threads = config.WORKER_THREADS
    range_size = end_index - start_index + 1
    
    # Decide between sequential and parallel modes
    use_parallel = (
        num_threads > 1 and
        range_size >= PARALLEL_THRESHOLD
    )
    
    if use_parallel:
        logger.debug(
            f"Job {job_id}: Using parallel mode "
            f"(threads={num_threads}, range_size={range_size})"
        )
        return _crack_range_parallel(
            target_hash=target_hash,
            scheme=scheme,
            start_index=start_index,
            end_index=end_index,
            job_id=job_id,
            check_interval=check_interval,
            num_threads=num_threads,
            range_size=range_size,
        )
    else:
        logger.debug(
            f"Job {job_id}: Using sequential mode "
            f"(threads={num_threads}, range_size={range_size})"
        )
        return _crack_range_sequential(
            target_hash=target_hash,
            scheme=scheme,
            start_index=start_index,
            end_index=end_index,
            job_id=job_id,
            check_interval=check_interval,
        )


def _crack_range_sequential(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
    check_interval: int,
) -> CrackResultPayload:
    """
    Sequential password cracking implementation.
    
    Processes indices one by one, checking for cancellation periodically.
    
    Returns:
        CrackResultPayload with result (FOUND/NOT_FOUND/CANCELLED/ERROR).
    """
    cancellation_registry = CancellationRegistry()
    
    logger.debug(
        f"Job {job_id}: Starting sequential cracking for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
        f"range [{start_index}, {end_index}]"
    )
    
    try:
        for i in range(start_index, end_index + 1):
            # Check cancellation every check_interval iterations
            if i % check_interval == 0:
                if cancellation_registry.is_cancelled(job_id):
                    logger.info(
                        f"Job {job_id}: Cancelled at index {i} "
                        f"(range [{start_index}, {end_index}], "
                        f"hash {target_hash[:HashDisplay.PREFIX_LENGTH]}...)"
                    )
                    return CrackResultPayload(
                        status=ResultStatus.CANCELLED,
                        found_password=None,
                        last_index_processed=i,
                        error_message=None,
                    )
            
            # Generate password and compute hash
            password = scheme.index_to_password(i)
            computed_hash = hashlib.md5(password.encode()).hexdigest().lower()
            
            # Compare with target hash (both already lowercase)
            if computed_hash == target_hash:
                logger.info(
                    f"Job {job_id}: Password found for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
                    f"at index {i} in range [{start_index}, {end_index}]: {password}"
                )
                return CrackResultPayload(
                    status=ResultStatus.FOUND,
                    found_password=password,
                    last_index_processed=i,
                    error_message=None,
                )
        
        # Not found in range
        logger.debug(
            f"Job {job_id}: Password not found in range [{start_index}, {end_index}] "
            f"for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}..."
        )
        return CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=end_index,
            error_message=None,
        )
    
    except Exception as e:
        logger.error(
            f"Job {job_id}: Error in sequential crack_range "
            f"for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
            f"range [{start_index}, {end_index}]: {e}",
            exc_info=True,
        )
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=start_index,
            error_message=str(e),
        )


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
    
    This function runs in a separate thread and processes a portion of the
    total range. It checks for cancellation periodically and returns early
    if the job is cancelled.
    
    Any internal exception will propagate to the caller, which should treat
    it as an ERROR condition for the entire parallel operation.
    
    Returns:
        Tuple of (index, password) if found, None if the subrange completed
        cleanly with no match (or if cancelled).
        
    Raises:
        Exception: Any unexpected error during processing will be raised
        to the caller, which should return ResultStatus.ERROR.
    """
    cancellation_registry = CancellationRegistry()
    
    for i in range(start_index, end_index + 1):
        # Check cancellation every check_interval iterations
        if i % check_interval == 0:
            if cancellation_registry.is_cancelled(job_id):
                logger.debug(
                    f"Job {job_id}: Subrange [{start_index}, {end_index}] "
                    f"cancelled at index {i}"
                )
                return None  # Sub-range stops due to cancellation
        
        # Generate password and compute hash
        password = scheme.index_to_password(i)
        computed_hash = hashlib.md5(password.encode()).hexdigest().lower()
        
        # Compare with target hash (both already lowercase)
        if computed_hash == target_hash:
            logger.debug(
                f"Job {job_id}: Password found in subrange [{start_index}, {end_index}] "
                f"at index {i} for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}..."
            )
            return (i, password)
    
    # Not found in this sub-range (normal completion)
    return None


def _submit_subranges(
    executor: ThreadPoolExecutor,
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
    check_interval: int,
    subrange_size: int,
) -> list[tuple]:
    """
    Submit all subranges to the thread pool executor.
    
    Returns:
        List of tuples: (future, subrange_start, subrange_end)
    """
    futures = []
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
    
    logger.debug(
        f"Job {job_id}: Submitted {len(futures)} sub-ranges "
        f"for parallel processing (range [{start_index}, {end_index}])"
    )
    
    return futures


def _cancel_all_futures(futures: list[tuple]) -> None:
    """Cancel all futures in the list."""
    for f, _, _ in futures:
        f.cancel()


def _handle_cancellation(
    job_id: str,
    start_index: int,
    end_index: int,
    futures: list[tuple],
) -> CrackResultPayload:
    """Handle cancellation during parallel processing."""
    logger.info(
        f"Job {job_id}: Cancelled during parallel processing "
        f"(range [{start_index}, {end_index}])"
    )
    _cancel_all_futures(futures)
    return CrackResultPayload(
        status=ResultStatus.CANCELLED,
        found_password=None,
        last_index_processed=start_index,
        error_message=None,
    )


def _handle_subrange_error(
    job_id: str,
    target_hash: str,
    start_index: int,
    end_index: int,
    error: Exception,
    futures: list[tuple],
) -> CrackResultPayload:
    """Handle exception from a subrange."""
    logger.error(
        f"Job {job_id}: Subrange error in parallel cracking "
        f"for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
        f"range [{start_index}, {end_index}]: {error}",
        exc_info=True,
    )
    _cancel_all_futures(futures)
    return CrackResultPayload(
        status=ResultStatus.ERROR,
        found_password=None,
        last_index_processed=start_index,
        error_message=f"Subrange error: {str(error)}",
    )


def _handle_password_found(
    job_id: str,
    target_hash: str,
    start_index: int,
    end_index: int,
    found_index: int,
    found_password: str,
    futures: list[tuple],
) -> CrackResultPayload:
    """Handle password found case."""
    logger.info(
        f"Job {job_id}: Password found for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
        f"at index {found_index} in range [{start_index}, {end_index}]: {found_password}"
    )
    _cancel_all_futures(futures)
    return CrackResultPayload(
        status=ResultStatus.FOUND,
        found_password=found_password,
        last_index_processed=found_index,
        error_message=None,
    )


def _process_parallel_results(
    futures: list[tuple],
    target_hash: str,
    start_index: int,
    end_index: int,
    job_id: str,
    cancellation_registry: CancellationRegistry,
) -> Optional[CrackResultPayload]:
    """
    Process results from parallel subranges as they complete.
    
    Returns:
        CrackResultPayload if early termination (FOUND/CANCELLED/ERROR), None if all completed.
    """
    for future in as_completed([f[0] for f in futures]):
        # Check cancellation before processing result
        if cancellation_registry.is_cancelled(job_id):
            return _handle_cancellation(job_id, start_index, end_index, futures)
        
        # Get result from future - catch any exceptions from subranges
        try:
            result = future.result()
        except Exception as e:
            return _handle_subrange_error(
                job_id, target_hash, start_index, end_index, e, futures
            )
        
        if result is not None:
            found_index, found_password = result
            return _handle_password_found(
                job_id, target_hash, start_index, end_index,
                found_index, found_password, futures
            )
    
    # All subranges completed without finding password or errors
    return None


def _crack_range_parallel(
    target_hash: str,
    scheme: PasswordScheme,
    start_index: int,
    end_index: int,
    job_id: str,
    check_interval: int,
    num_threads: int,
    range_size: int,
) -> CrackResultPayload:
    """
    Parallel password cracking implementation using ThreadPoolExecutor.
    
    Splits the range into sub-ranges and processes them concurrently.
    Checks for cancellation between sub-range completions.
    
    If any subrange raises an exception, the entire operation is treated
    as an ERROR and all remaining futures are cancelled.
    
    Returns:
        CrackResultPayload with result (FOUND/NOT_FOUND/CANCELLED/ERROR).
    """
    cancellation_registry = CancellationRegistry()
    
    # Calculate sub-range size (at least MINION_SUBRANGE_MIN_SIZE indices per thread)
    subrange_size = max(config.MINION_SUBRANGE_MIN_SIZE, range_size // num_threads)
    
    logger.debug(
        f"Job {job_id}: Starting parallel cracking for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
        f"range [{start_index}, {end_index}], {num_threads} threads, "
        f"subrange_size={subrange_size}"
    )
    
    try:
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            # Submit all subranges
            futures = _submit_subranges(
                executor, target_hash, scheme, start_index, end_index,
                job_id, check_interval, subrange_size
            )
            
            # Process results as they complete
            early_result = _process_parallel_results(
                futures, target_hash, start_index, end_index,
                job_id, cancellation_registry
            )
            
            if early_result is not None:
                return early_result
        
        # Not found in range (all subranges completed cleanly)
        logger.debug(
            f"Job {job_id}: Password not found in range [{start_index}, {end_index}] "
            f"for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}..."
        )
        return CrackResultPayload(
            status=ResultStatus.NOT_FOUND,
            found_password=None,
            last_index_processed=end_index,
            error_message=None,
        )
    
    except Exception as e:
        # Top-level exception (shouldn't normally happen, but catch for safety)
        logger.error(
            f"Job {job_id}: Unexpected error in parallel crack_range "
            f"for hash {target_hash[:HashDisplay.PREFIX_LENGTH]}... "
            f"range [{start_index}, {end_index}]: {e}",
            exc_info=True,
        )
        return CrackResultPayload(
            status=ResultStatus.ERROR,
            found_password=None,
            last_index_processed=start_index,
            error_message=str(e),
        )
