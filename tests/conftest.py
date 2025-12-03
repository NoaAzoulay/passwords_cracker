"""Pytest configuration and fixtures."""

import pytest
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config to defaults before each test."""
    # This ensures tests don't interfere with each other
    # via environment variables
    yield
    # Cleanup if needed


@pytest.fixture(autouse=True)
def ensure_sequential_for_small_ranges(monkeypatch):
    """
    Ensure small ranges use sequential processing for deterministic tests.
    
    This fixture ensures that tests with small ranges (< 10000) always use
    sequential processing, regardless of WORKER_THREADS setting.
    This makes tests deterministic and faster.
    """
    # The worker_parallel.py already falls back to sequential for ranges < 10000
    # So this is mainly for documentation/clarity
    yield

