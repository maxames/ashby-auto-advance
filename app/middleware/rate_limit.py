"""Rate limiting middleware."""

from fastapi import FastAPI
from slowapi import (
    Limiter,
    _rate_limit_exceeded_handler,  # type: ignore[reportPrivateUsage]
)
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def get_limiter() -> Limiter:
    """
    Create rate limiter instance.

    Uses client IP address for rate limiting.
    """
    return Limiter(key_func=get_remote_address)


def setup_rate_limiting(app: FastAPI) -> Limiter:
    """
    Configure rate limiting for the application.

    Returns:
        Limiter instance for use in route decorators
    """
    limiter = get_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[reportUnknownMemberType]  # FastAPI handler
    return limiter
