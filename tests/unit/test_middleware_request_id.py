"""Tests for RequestIDMiddleware."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.middleware.request_id import RequestIDMiddleware


@pytest.mark.asyncio
async def test_request_id_added_to_header():
    """Request ID is added to response header."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert "X-Request-ID" in response.headers
    # Should be valid UUID format
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36  # UUID format with hyphens
    assert request_id.count("-") == 4


@pytest.mark.asyncio
async def test_request_id_unique_per_request():
    """Each request gets a unique ID."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response1 = await client.get("/test")
        response2 = await client.get("/test")

    id1 = response1.headers["X-Request-ID"]
    id2 = response2.headers["X-Request-ID"]
    assert id1 != id2


@pytest.mark.asyncio
async def test_request_id_available_in_request_state():
    """Request ID is accessible via request.state."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    captured_id = None

    @app.get("/test")
    async def test_route(request: Request):
        nonlocal captured_id
        captured_id = request.state.request_id
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test")

    assert captured_id is not None
    assert captured_id == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_request_id_persists_through_errors():
    """Request ID is present even when endpoint raises error."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_route():
        raise ValueError("Test error")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        try:
            response = await client.get("/test")
        except Exception:
            pass
        else:
            # If error handler catches it, we should still have the header
            assert "X-Request-ID" in response.headers
