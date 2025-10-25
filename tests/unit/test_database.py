"""Tests for database connection pool manager (app/core/database.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.database import Database


@pytest.mark.asyncio
async def test_connect_success():
    """Connection pool created successfully with correct parameters."""
    db = Database()
    mock_pool = MagicMock()

    with patch("app.core.database.asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_pool

        await db.connect()

        # Verify pool created with correct parameters
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["min_size"] == 2
        assert call_kwargs["max_size"] == 10
        assert call_kwargs["command_timeout"] == 60

        # Verify pool was assigned
        assert db.pool == mock_pool


@pytest.mark.asyncio
async def test_connect_retry_on_failure():
    """Retries connection on failure with exponential backoff."""
    db = Database()
    mock_pool = MagicMock()

    with (
        patch("app.core.database.asyncpg.create_pool", new_callable=AsyncMock) as mock_create,
        patch("app.core.database.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        # Fail first attempt, succeed on second
        mock_create.side_effect = [Exception("Connection failed"), mock_pool]

        await db.connect()

        # Verify two attempts made
        assert mock_create.call_count == 2

        # Verify exponential backoff (2^1 = 2 seconds after first failure)
        mock_sleep.assert_called_once_with(2)

        # Verify successful connection
        assert db.pool == mock_pool


@pytest.mark.asyncio
async def test_connect_max_retries_exhausted():
    """Exception raised after max retries exhausted."""
    db = Database()

    with (
        patch("app.core.database.asyncpg.create_pool", new_callable=AsyncMock) as mock_create,
        patch("app.core.database.asyncio.sleep", new_callable=AsyncMock),
    ):
        # Always fail
        mock_create.side_effect = Exception("Connection failed")

        # Should raise exception after 3 attempts
        with pytest.raises(Exception, match="Connection failed"):
            await db.connect()

        # Verify 3 attempts made (max_retries=3)
        assert mock_create.call_count == 3


@pytest.mark.asyncio
async def test_disconnect_closes_pool():
    """Disconnect closes pool gracefully."""
    db = Database()
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()

    db.pool = mock_pool

    await db.disconnect()

    # Verify pool was closed
    mock_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_when_no_pool():
    """Disconnect handles missing pool gracefully."""
    db = Database()
    db.pool = None

    # Should not raise exception
    await db.disconnect()


@pytest.mark.asyncio
async def test_execute_success():
    """Execute runs query successfully."""
    db = Database()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value="UPDATE 1")
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))

    db.pool = mock_pool

    result = await db.execute("UPDATE users SET name = $1", "test")

    assert result == "UPDATE 1"
    mock_conn.execute.assert_called_once_with("UPDATE users SET name = $1", "test")


@pytest.mark.asyncio
async def test_execute_no_pool_raises_error():
    """Execute raises RuntimeError when pool not initialized."""
    db = Database()
    db.pool = None

    with pytest.raises(RuntimeError, match="Database pool not initialized"):
        await db.execute("SELECT 1")


@pytest.mark.asyncio
async def test_fetch_success():
    """Fetch returns multiple rows."""
    db = Database()
    mock_conn = MagicMock()
    mock_rows = [{"id": 1}, {"id": 2}]
    mock_conn.fetch = AsyncMock(return_value=mock_rows)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))

    db.pool = mock_pool

    result = await db.fetch("SELECT * FROM users WHERE age > $1", 18)

    assert result == mock_rows
    mock_conn.fetch.assert_called_once_with("SELECT * FROM users WHERE age > $1", 18)


@pytest.mark.asyncio
async def test_fetchrow_success():
    """Fetchrow returns single row."""
    db = Database()
    mock_conn = MagicMock()
    mock_row = {"id": 1, "name": "test"}
    mock_conn.fetchrow = AsyncMock(return_value=mock_row)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))

    db.pool = mock_pool

    result = await db.fetchrow("SELECT * FROM users WHERE id = $1", 1)

    assert result == mock_row
    mock_conn.fetchrow.assert_called_once_with("SELECT * FROM users WHERE id = $1", 1)


@pytest.mark.asyncio
async def test_fetchval_success():
    """Fetchval returns single value."""
    db = Database()
    mock_conn = MagicMock()
    mock_conn.fetchval = AsyncMock(return_value=42)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))

    db.pool = mock_pool

    result = await db.fetchval("SELECT COUNT(*) FROM users")

    assert result == 42
    mock_conn.fetchval.assert_called_once_with("SELECT COUNT(*) FROM users")


# Helper class for async context manager mocking
class AsyncContextManager:
    """Helper for mocking async context managers."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
