"""Tests for error handling middleware."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.middleware.errors import setup_exception_handlers
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
