"""Tests for API error handling."""

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.api.errors import setup_exception_handlers
from app.core.errors import (
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    service_boundary,
)
from app.middleware.request_id import RequestIDMiddleware


class SampleInput(BaseModel):
    """Sample input model for validation."""

    name: str
    age: int


@pytest.mark.asyncio
async def test_http_exception_standardized():
    """HTTPException returns standardized error format."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test")
    async def test_route():
        raise HTTPException(status_code=404, detail="Not found")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
    assert data["error"]["message"] == "Not found"
    assert "request_id" in data["error"]


@pytest.mark.asyncio
async def test_validation_error_standardized():
    """Pydantic validation errors return standardized format."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.post("/test")
    async def test_route(data: SampleInput):
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/test", json={"name": "test"})  # Missing age

    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]
    assert "request_id" in data["error"]


@pytest.mark.asyncio
async def test_error_includes_request_id():
    """All errors include request_id from RequestIDMiddleware."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test")
    async def test_route():
        raise HTTPException(status_code=400, detail="Bad request")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    data = response.json()
    request_id_header = response.headers.get("X-Request-ID")
    request_id_body = data["error"]["request_id"]

    assert request_id_header is not None
    assert request_id_body is not None
    assert request_id_header == request_id_body


@pytest.mark.asyncio
async def test_error_various_status_codes():
    """Different HTTP status codes are handled correctly."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test400")
    async def test_400():
        raise HTTPException(status_code=400, detail="Bad request")

    @app.get("/test401")
    async def test_401():
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/test403")
    async def test_403():
        raise HTTPException(status_code=403, detail="Forbidden")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response_400 = await client.get("/test400")
        response_401 = await client.get("/test401")
        response_403 = await client.get("/test403")

    assert response_400.json()["error"]["code"] == "HTTP_400"
    assert response_401.json()["error"]["code"] == "HTTP_401"
    assert response_403.json()["error"]["code"] == "HTTP_403"


# New tests for domain error handling


@pytest.mark.asyncio
async def test_domain_error_maps_to_404():
    """NotFoundError maps to HTTP 404."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test")
    async def test_route():
        raise NotFoundError("Resource not found", context={"resource_id": "123"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Resource not found"


@pytest.mark.asyncio
async def test_external_service_error_maps_to_502():
    """ExternalServiceError maps to HTTP 502."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test")
    async def test_route():
        raise ExternalServiceError(
            "API call failed", service="ashby", context={"endpoint": "candidate.info"}
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "EXTERNAL_SERVICE_ERROR"
    assert data["error"]["message"] == "API call failed"


@pytest.mark.asyncio
async def test_database_error_maps_to_500():
    """DatabaseError maps to HTTP 500."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    setup_exception_handlers(app)

    @app.get("/test")
    async def test_route():
        raise DatabaseError("Connection failed", context={"function": "test"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "DATABASE_ERROR"
    assert data["error"]["message"] == "Connection failed"


@pytest.mark.asyncio
async def test_decorator_converts_asyncpg_to_database_error():
    """@service_boundary converts asyncpg errors to DatabaseError."""

    @service_boundary
    async def failing_db_operation():
        # Create a mock asyncpg error
        raise asyncpg.PostgresError("Connection timeout")  # type: ignore[attr-defined]

    with pytest.raises(DatabaseError) as exc_info:
        await failing_db_operation()

    assert "Connection timeout" in str(exc_info.value)
    assert exc_info.value.context["function"] == "failing_db_operation"


@pytest.mark.asyncio
async def test_decorator_passes_through_domain_errors():
    """@service_boundary doesn't wrap existing domain errors."""

    @service_boundary
    async def already_domain_error():
        raise NotFoundError("Already a domain error")

    with pytest.raises(NotFoundError) as exc_info:
        await already_domain_error()

    assert "Already a domain error" in str(exc_info.value)
