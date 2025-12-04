"""Configuration loaded from environment variables."""

import os
from typing import List


def _get_env_int(key: str, default: str) -> int:
    """Get integer environment variable with validation."""
    try:
        return int(os.getenv(key, default))
    except ValueError:
        raise ValueError(f"Invalid integer value for {key}")


def _get_env_float(key: str, default: str) -> float:
    """Get float environment variable with validation."""
    try:
        return float(os.getenv(key, default))
    except ValueError:
        raise ValueError(f"Invalid float value for {key}")


class Config:
    """Centralized configuration from environment variables."""
    
    # Chunking
    CHUNK_SIZE: int = _get_env_int("CHUNK_SIZE", "100000")
    CANCELLATION_CHECK_EVERY: int = _get_env_int("CANCELLATION_CHECK_EVERY", "5000")
    
    # Performance: Worker threads per minion (for parallel processing within minion)
    # Balanced default: 2 threads per minion (good balance between performance and CPU usage)
    # With 3 minions (default), this uses ~6 threads total (optimal for 6-8 core systems)
    WORKER_THREADS: int = _get_env_int("WORKER_THREADS", "2")  # 1 = sequential, 2 = balanced, >2 = high performance
    
    # Minion parallel processing: Minimum subrange size per thread
    # When splitting work for parallel processing, each thread gets at least this many indices
    # Larger values = fewer subranges (less overhead, but less parallelism)
    # Smaller values = more subranges (more parallelism, but more overhead)
    MINION_SUBRANGE_MIN_SIZE: int = _get_env_int("MINION_SUBRANGE_MIN_SIZE", "1000")
    
    # Retries
    MAX_ATTEMPTS: int = _get_env_int("MAX_ATTEMPTS", "3")
    
    # Timeouts
    MINION_REQUEST_TIMEOUT: float = _get_env_float("MINION_REQUEST_TIMEOUT", "5.0")
    NO_MINION_WAIT_TIME: float = _get_env_float("NO_MINION_WAIT_TIME", "0.5")
    
    # Output
    OUTPUT_FILE: str = os.getenv("OUTPUT_FILE", "data/output.txt")
    
    # Minion URLs
    _minion_urls_str = os.getenv("MINION_URLS", "http://minion1:8000,http://minion2:8000,http://minion3:8000")
    MINION_URLS: List[str] = [
        url.strip() 
        for url in _minion_urls_str.split(",")
        if url.strip()
    ]
    
    # Circuit Breaker
    MINION_FAILURE_THRESHOLD: int = _get_env_int("MINION_FAILURE_THRESHOLD", "3")
    MINION_BREAKER_OPEN_SECONDS: float = _get_env_float("MINION_BREAKER_OPEN_SECONDS", "10.0")
    
    # Job-level concurrency: Maximum number of hash jobs to process in parallel
    # Default: 3 (or number of minions, whichever is smaller)
    # This controls how many hashes are processed concurrently at the main level
    # Calculate default after MINION_URLS is set
    MAX_CONCURRENT_JOBS: int = _get_env_int(
        "MAX_CONCURRENT_JOBS", 
        str(min(3, len(MINION_URLS) if MINION_URLS else 3))
    )


config = Config()

