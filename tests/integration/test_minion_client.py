"""Tests for MinionClient HTTP communication."""

import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch
from shared.domain.models import CrackResultPayload, WorkChunk, RangeDict
from shared.domain.consts import ResultStatus
from master.infrastructure.minion_client import MinionClient
from master.infrastructure.minion_registry import MinionRegistry


@pytest.fixture
def registry():
    """Create a MinionRegistry for testing."""
    return MinionRegistry(["http://minion1:8000", "http://minion2:8000"])


@pytest.fixture
def client(registry):
    """Create a MinionClient for testing."""
    return MinionClient(registry)


@pytest.fixture
def sample_chunk():
    """Create a sample WorkChunk for testing."""
    return WorkChunk(
        id="test-chunk-1",
        job_id="test-job-1",
        start_index=0,
        end_index=100,
    )


class TestMinionClient:
    """Tests for MinionClient HTTP communication."""
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_success_found(self, client, sample_chunk):
        """Test successful crack request that finds password."""
        # Mock successful response
        respx.post("http://minion1:8000/crack-range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": ResultStatus.FOUND,
                    "found_password": "050-0000000",
                    "last_index_processed": 0,
                    "error_message": None
                }
            )
        )
        
        result = await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-1"
        )
        
        assert result.status == ResultStatus.FOUND
        assert result.found_password == "050-0000000"
        
        # Breaker should record success
        breaker = client.registry.get_breaker("http://minion1:8000")
        assert breaker.failure_count == 0
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_success_not_found(self, client, sample_chunk):
        """Test successful crack request that doesn't find password."""
        respx.post("http://minion1:8000/crack-range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": ResultStatus.NOT_FOUND,
                    "found_password": None,
                    "last_index_processed": 100,
                    "error_message": None
                }
            )
        )
        
        result = await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-2"
        )
        
        assert result.status == ResultStatus.NOT_FOUND
        assert result.found_password is None
        
        # NOT_FOUND should record success (not failure)
        breaker = client.registry.get_breaker("http://minion1:8000")
        assert breaker.failure_count == 0
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_network_timeout(self, client, sample_chunk):
        """Test that network timeout records failure."""
        respx.post("http://minion1:8000/crack-range").mock(
            side_effect=httpx.TimeoutException("Request timeout")
        )
        
        result = await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-3"
        )
        
        assert result.status == ResultStatus.ERROR
        assert "timeout" in result.error_message.lower() or "HTTP error" in result.error_message
        
        # Breaker should record failure
        breaker = client.registry.get_breaker("http://minion1:8000")
        assert breaker.failure_count == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_500_error(self, client, sample_chunk):
        """Test that 500 response is treated as ERROR."""
        respx.post("http://minion1:8000/crack-range").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        
        result = await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-4"
        )
        
        assert result.status == ResultStatus.ERROR
        
        # Breaker should record failure
        breaker = client.registry.get_breaker("http://minion1:8000")
        assert breaker.failure_count == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_connection_error(self, client, sample_chunk):
        """Test that connection error records failure."""
        respx.post("http://minion1:8000/crack-range").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        
        result = await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-5"
        )
        
        assert result.status == ResultStatus.ERROR
        assert "connection" in result.error_message.lower() or "HTTP error" in result.error_message
        
        # Breaker should record failure
        breaker = client.registry.get_breaker("http://minion1:8000")
        assert breaker.failure_count == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_crack_request_uses_pydantic_serialization(self, client, sample_chunk):
        """Test that request uses Pydantic model_dump for serialization."""
        route = respx.post("http://minion1:8000/crack-range").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": ResultStatus.NOT_FOUND,
                    "found_password": None,
                    "last_index_processed": 100,
                    "error_message": None
                }
            )
        )
        
        await client.send_crack_request(
            minion_url="http://minion1:8000",
            chunk=sample_chunk,
            hash_value="a" * 32,
            hash_type="md5",
            password_scheme="il_phone_05x_dash",
            job_id="test-job-6"
        )
        
        # Verify request was made with correct structure
        assert route.calls.call_count == 1
        request = route.calls.last.request
        json_data = request.read()
        import json
        json_data = json.loads(json_data)
        assert "hash" in json_data
        assert "range" in json_data
        assert json_data["range"]["start_index"] == 0
        assert json_data["range"]["end_index"] == 100
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_cancel_job_success(self, client):
        """Test successful cancel job request."""
        respx.post("http://minion1:8000/cancel-job").mock(
            return_value=httpx.Response(200, json={"status": "OK"})
        )
        
        # Should not raise exception
        await client.send_cancel_job("http://minion1:8000", "test-job-cancel")
        
        # Verify request was made
        assert respx.calls.call_count == 1
    
    @pytest.mark.asyncio
    @respx.mock
    async def test_send_cancel_job_network_error_best_effort(self, client):
        """Test that cancel job errors don't fail (best-effort)."""
        respx.post("http://minion1:8000/cancel-job").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        
        # Should not raise exception (best-effort)
        await client.send_cancel_job("http://minion1:8000", "test-job-cancel")
        
        # Should complete without error
    
    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Test that client can be closed."""
        await client.close()
        # Should complete without error

