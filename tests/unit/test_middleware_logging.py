"""Tests for LoggingMiddleware."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.logging import LoggingMiddleware


@pytest.mark.asyncio
async def test_logging_middleware_logs_request_started():
    """Logs request_started event."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    with patch("app.middleware.logging.logger") as mock_logger:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/test")

        # Check info was called with request_started
        assert mock_logger.info.called
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("request_started" in str(call) for call in calls)


@pytest.mark.asyncio
async def test_logging_middleware_logs_request_completed():
    """Logs request_completed with status and timing."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    with patch("app.middleware.logging.logger") as mock_logger:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/test")

        # Check completed log
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("request_completed" in str(call) for call in calls)


@pytest.mark.asyncio
async def test_logging_middleware_logs_errors():
    """Logs request_failed when exception occurs."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route():
        raise ValueError("Test error")

    with patch("app.middleware.logging.logger") as mock_logger:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                await client.get("/test")
            except Exception:
                pass

        # Check error log
        assert mock_logger.error.called


@pytest.mark.asyncio
async def test_logging_middleware_includes_timing():
    """Logs include duration_ms metric."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    with patch("app.middleware.logging.logger") as mock_logger:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/test")

        # Check that duration_ms is in the log call
        # Look at the completed log call
        for call in mock_logger.info.call_args_list:
            if "request_completed" in str(call):
                # Should have duration_ms as keyword arg
                assert "duration_ms" in str(call)
                break
