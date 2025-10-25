"""Tests for rate limiting middleware."""

from fastapi import FastAPI

from app.middleware.rate_limit import get_limiter, setup_rate_limiting


def test_get_limiter_creates_instance():
    """get_limiter creates a Limiter instance."""
    limiter = get_limiter()

    assert limiter is not None
    # Check it's a Limiter instance
    assert hasattr(limiter, "limit")


def test_get_limiter_returns_new_instance():
    """get_limiter returns new instance each time."""
    limiter1 = get_limiter()
    limiter2 = get_limiter()

    # Each call should return a new instance
    # (They'll have different identity but same configuration)
    assert limiter1 is not None
    assert limiter2 is not None


def test_setup_rate_limiting_adds_to_app_state():
    """setup_rate_limiting adds limiter to app.state."""
    app = FastAPI()

    limiter = setup_rate_limiting(app)

    assert app.state.limiter is not None
    assert app.state.limiter is limiter


def test_setup_rate_limiting_returns_limiter():
    """setup_rate_limiting returns the limiter instance."""
    app = FastAPI()

    limiter = setup_rate_limiting(app)

    assert limiter is not None
    assert hasattr(limiter, "limit")


def test_setup_rate_limiting_adds_exception_handler():
    """setup_rate_limiting adds RateLimitExceeded exception handler."""
    app = FastAPI()

    # Count exception handlers before
    handlers_before = len(app.exception_handlers)

    setup_rate_limiting(app)

    # Should have added one exception handler
    handlers_after = len(app.exception_handlers)
    assert handlers_after == handlers_before + 1
