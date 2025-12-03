"""Tests for minion FastAPI endpoints."""

import pytest
import hashlib
from fastapi.testclient import TestClient
from minion.api.app import app
from shared.consts import ResultStatus
from minion.infrastructure.cancellation import CancellationRegistry


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


class TestCrackRangeEndpoint:
    """Tests for /crack-range endpoint."""
    
    def test_crack_range_found(self, client):
        """Test /crack-range with password that exists."""
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        payload = {
            "hash": test_hash,
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 100},
            "job_id": "test-job-1",
            "request_id": "test-request-1"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ResultStatus.FOUND
        assert data["found_password"] == test_password
        assert data["last_index_processed"] <= 100
    
    def test_crack_range_not_found(self, client):
        """Test /crack-range with password that doesn't exist."""
        payload = {
            "hash": "a" * 32,
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 100},
            "job_id": "test-job-2",
            "request_id": "test-request-2"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ResultStatus.NOT_FOUND
        assert data["found_password"] is None
        assert data["last_index_processed"] == 100
    
    def test_crack_range_invalid_hash_too_short(self, client):
        """Test /crack-range with hash that's too short."""
        payload = {
            "hash": "too_short",
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 100},
            "job_id": "test-job-3",
            "request_id": "test-request-3"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 400
        assert "32 hex characters" in response.json()["detail"]
    
    def test_crack_range_invalid_hash_too_long(self, client):
        """Test /crack-range with hash that's too long."""
        payload = {
            "hash": "a" * 33,
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 100},
            "job_id": "test-job-4",
            "request_id": "test-request-4"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 400
    
    def test_crack_range_invalid_range_start_greater_than_end(self, client):
        """Test /crack-range with invalid range (start > end)."""
        payload = {
            "hash": "a" * 32,
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 100, "end_index": 0},  # Invalid
            "job_id": "test-job-5",
            "request_id": "test-request-5"
        }
        
        response = client.post("/crack-range", json=payload)
        
        # Pydantic validation happens first, which returns 422
        # The endpoint also checks, but Pydantic catches it first
        assert response.status_code in (400, 422)
        
        # Check error detail (could be in different format for 422 vs 400)
        error_detail = response.json()
        if "detail" in error_detail:
            detail = error_detail["detail"]
            if isinstance(detail, list):
                # Pydantic validation error format
                detail_str = str(detail)
            else:
                detail_str = str(detail)
        else:
            detail_str = str(error_detail)
        
        # Should mention the range validation error
        assert "end_index" in detail_str or "start_index" in detail_str or "range" in detail_str.lower()
    
    def test_crack_range_valid_range_single_index(self, client):
        """Test /crack-range with valid single-index range."""
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().lower()
        
        payload = {
            "hash": test_hash,
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 0},  # Single index
            "job_id": "test-job-6",
            "request_id": "test-request-6"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ResultStatus.FOUND
        assert data["found_password"] == test_password
    
    def test_crack_range_uppercase_hash_normalized(self, client):
        """Test that uppercase hash is normalized to lowercase."""
        test_password = "050-0000000"
        test_hash = hashlib.md5(test_password.encode()).hexdigest().upper()
        
        payload = {
            "hash": test_hash,  # Uppercase
            "hash_type": "md5",
            "password_scheme": "il_phone_05x_dash",
            "range": {"start_index": 0, "end_index": 10},
            "job_id": "test-job-7",
            "request_id": "test-request-7"
        }
        
        response = client.post("/crack-range", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ResultStatus.FOUND
        assert data["found_password"] == test_password


class TestCancelJobEndpoint:
    """Tests for /cancel-job endpoint."""
    
    def test_cancel_job_success(self, client):
        """Test /cancel-job successfully cancels a job."""
        payload = {"job_id": "test-job-cancel-1"}
        
        response = client.post("/cancel-job", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        
        # Verify job is actually cancelled
        registry = CancellationRegistry()
        assert registry.is_cancelled("test-job-cancel-1") is True
    
    def test_cancel_job_called_twice(self, client):
        """Test that calling /cancel-job twice is still OK."""
        payload = {"job_id": "test-job-cancel-2"}
        
        # First call
        response1 = client.post("/cancel-job", json=payload)
        assert response1.status_code == 200
        
        # Second call
        response2 = client.post("/cancel-job", json=payload)
        assert response2.status_code == 200
        
        # Both should return OK
        assert response1.json()["status"] == "OK"
        assert response2.json()["status"] == "OK"
        
        # Job should still be cancelled
        registry = CancellationRegistry()
        assert registry.is_cancelled("test-job-cancel-2") is True
    
    def test_cancel_job_multiple_jobs(self, client):
        """Test cancelling multiple different jobs."""
        job_ids = ["job-1", "job-2", "job-3"]
        registry = CancellationRegistry()
        
        for job_id in job_ids:
            response = client.post("/cancel-job", json={"job_id": job_id})
            assert response.status_code == 200
            assert registry.is_cancelled(job_id) is True

