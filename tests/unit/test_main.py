"""Tests for FastAPI application (app/main.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def http_client(clean_db):
    """HTTP client for unit testing FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_health_check_success(http_client, clean_db):
    """Health check returns 200 with database and scheduler info."""
    response = await http_client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "scheduler" in data
    assert "pool" in data

    # Verify pool stats
    assert "size" in data["pool"]
    assert "free" in data["pool"]
    assert "in_use" in data["pool"]
    assert isinstance(data["pool"]["size"], int)
    assert isinstance(data["pool"]["free"], int)
    assert isinstance(data["pool"]["in_use"], int)


@pytest.mark.asyncio
async def test_health_check_database_unavailable(http_client):
    """Health check returns 503 when database is unavailable."""
    with patch("app.main.db.fetchval", new_callable=AsyncMock) as mock_fetchval:
        mock_fetchval.side_effect = Exception("Connection failed")

        response = await http_client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert "Database unavailable" in data["detail"]


@pytest.mark.asyncio
async def test_health_check_pool_not_initialized(http_client):
    """Health check returns 503 when pool is not initialized."""
    with patch("app.main.db.pool", None):
        response = await http_client.get("/health")

        assert response.status_code == 503


@pytest.mark.asyncio
async def test_root_endpoint(http_client):
    """Root endpoint returns welcome message."""
    response = await http_client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Ashby Auto-Advancement" in data["message"]


@pytest.mark.asyncio
async def test_lifespan_startup_sequence():
    """Lifespan startup executes in correct order."""
    from contextlib import asynccontextmanager

    from app.main import lifespan

    mock_app = MagicMock()
    call_order = []

    async def track_connect(*args, **kwargs):
        call_order.append("connect")

    async def track_sync_forms(*args, **kwargs):
        call_order.append("sync_forms")

    async def track_sync_interviews(*args, **kwargs):
        call_order.append("sync_interviews")

    async def track_sync_users(*args, **kwargs):
        call_order.append("sync_users")

    def track_setup(*args, **kwargs):
        call_order.append("setup_scheduler")

    def track_start(*args, **kwargs):
        call_order.append("start_scheduler")

    async def track_disconnect(*args, **kwargs):
        call_order.append("disconnect")

    def track_shutdown(*args, **kwargs):
        call_order.append("shutdown_scheduler")

    with (
        patch("app.main.db.connect", new_callable=AsyncMock, side_effect=track_connect),
        patch(
            "app.main.sync_feedback_forms",
            new_callable=AsyncMock,
            side_effect=track_sync_forms,
        ),
        patch(
            "app.main.sync_interviews",
            new_callable=AsyncMock,
            side_effect=track_sync_interviews,
        ),
        patch(
            "app.main.sync_slack_users",
            new_callable=AsyncMock,
            side_effect=track_sync_users,
        ),
        patch("app.main.setup_scheduler", side_effect=track_setup),
        patch("app.main.start_scheduler", side_effect=track_start),
        patch(
            "app.main.db.disconnect",
            new_callable=AsyncMock,
            side_effect=track_disconnect,
        ),
        patch("app.main.shutdown_scheduler", side_effect=track_shutdown),
    ):
        # Execute lifespan
        async with lifespan(mock_app):
            pass

        # Verify correct order
        assert call_order == [
            "connect",
            "sync_forms",
            "sync_interviews",
            "sync_users",
            "setup_scheduler",
            "start_scheduler",
            "shutdown_scheduler",
            "disconnect",
        ]


@pytest.mark.asyncio
async def test_lifespan_startup_sync_failure_continues():
    """Lifespan continues even if initial sync fails."""
    from app.main import lifespan

    mock_app = MagicMock()
    scheduler_started = False

    def track_start(*args, **kwargs):
        nonlocal scheduler_started
        scheduler_started = True

    with (
        patch("app.main.db.connect", new_callable=AsyncMock),
        patch(
            "app.main.sync_feedback_forms",
            new_callable=AsyncMock,
            side_effect=Exception("Sync failed"),
        ),
        patch("app.main.sync_interviews", new_callable=AsyncMock),
        patch("app.main.sync_slack_users", new_callable=AsyncMock),
        patch("app.main.setup_scheduler"),
        patch("app.main.start_scheduler", side_effect=track_start),
        patch("app.main.db.disconnect", new_callable=AsyncMock),
        patch("app.main.shutdown_scheduler"),
    ):
        # Execute lifespan - should not raise exception
        async with lifespan(mock_app):
            pass

        # Verify scheduler was still started despite sync failure
        assert scheduler_started


@pytest.mark.asyncio
async def test_lifespan_shutdown_sequence():
    """Lifespan shutdown executes in correct order."""
    from app.main import lifespan

    mock_app = MagicMock()
    shutdown_order = []

    def track_shutdown(*args, **kwargs):
        shutdown_order.append("shutdown_scheduler")

    async def track_disconnect(*args, **kwargs):
        shutdown_order.append("disconnect")

    with (
        patch("app.main.db.connect", new_callable=AsyncMock),
        patch("app.main.sync_feedback_forms", new_callable=AsyncMock),
        patch("app.main.sync_interviews", new_callable=AsyncMock),
        patch("app.main.sync_slack_users", new_callable=AsyncMock),
        patch("app.main.setup_scheduler"),
        patch("app.main.start_scheduler"),
        patch("app.main.shutdown_scheduler", side_effect=track_shutdown),
        patch(
            "app.main.db.disconnect",
            new_callable=AsyncMock,
            side_effect=track_disconnect,
        ),
    ):
        # Execute lifespan
        async with lifespan(mock_app):
            pass

        # Verify shutdown happens before disconnect
        assert shutdown_order == ["shutdown_scheduler", "disconnect"]
