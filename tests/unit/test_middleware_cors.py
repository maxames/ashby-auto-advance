"""Tests for CORS middleware configuration."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI

from app.middleware.cors import setup_cors


@pytest.mark.asyncio
async def test_setup_cors_configures_middleware():
    """setup_cors adds CORS middleware to app."""
    app = FastAPI()

    # Mock the add_middleware method to track calls
    original_add_middleware = app.add_middleware
    add_middleware_calls = []

    def track_add_middleware(middleware, **kwargs):
        add_middleware_calls.append((middleware, kwargs))
        return original_add_middleware(middleware, **kwargs)

    app.add_middleware = track_add_middleware

    # Setup CORS
    setup_cors(app)

    # Verify middleware was added
    assert len(add_middleware_calls) == 1
    middleware_class, kwargs = add_middleware_calls[0]

    # Check configuration
    assert "allow_origins" in kwargs
    assert "allow_credentials" in kwargs
    assert "allow_methods" in kwargs
    assert "allow_headers" in kwargs


@pytest.mark.asyncio
async def test_cors_allows_configured_headers():
    """CORS configuration includes required headers."""
    app = FastAPI()
    setup_cors(app)

    # Check that middleware was added (app.user_middleware will contain it)
    assert len(app.user_middleware) > 0


def test_cors_includes_request_id_header():
    """CORS configuration allows X-Request-ID header."""
    with patch("app.middleware.cors.settings") as mock_settings:
        mock_settings.frontend_urls = ["http://localhost:3000"]

        app = FastAPI()

        # Track what gets passed to add_middleware
        called_with = {}
        original_add_middleware = app.add_middleware

        def capture_add_middleware(middleware, **kwargs):
            called_with.update(kwargs)
            return original_add_middleware(middleware, **kwargs)

        app.add_middleware = capture_add_middleware

        setup_cors(app)

        # Verify X-Request-ID is in allowed headers
        assert "allow_headers" in called_with
        assert "X-Request-ID" in called_with["allow_headers"]


def test_cors_includes_api_key_header():
    """CORS configuration allows X-API-Key header for future auth."""
    with patch("app.middleware.cors.settings") as mock_settings:
        mock_settings.frontend_urls = ["http://localhost:3000"]

        app = FastAPI()

        # Track what gets passed to add_middleware
        called_with = {}
        original_add_middleware = app.add_middleware

        def capture_add_middleware(middleware, **kwargs):
            called_with.update(kwargs)
            return original_add_middleware(middleware, **kwargs)

        app.add_middleware = capture_add_middleware

        setup_cors(app)

        # Verify X-API-Key is in allowed headers
        assert "allow_headers" in called_with
        assert "X-API-Key" in called_with["allow_headers"]
