"""Domain exceptions and service boundary decorator."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import aiohttp
import asyncpg
from structlog import get_logger

logger = get_logger()

# Type variables for decorator
P = ParamSpec("P")
T = TypeVar("T")


class DomainError(Exception):
    """Base exception for all domain errors."""

    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        return self.message


class NotFoundError(DomainError):
    """Resource not found."""

    code = "NOT_FOUND"


class ValidationError(DomainError):
    """Input validation failed."""

    code = "VALIDATION_ERROR"


class ExternalServiceError(DomainError):
    """External service (Ashby, Slack) failed."""

    code = "EXTERNAL_SERVICE_ERROR"

    def __init__(
        self,
        message: str,
        service: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        ctx = context or {}
        if service:
            ctx["service"] = service
        super().__init__(message, ctx)


class DatabaseError(DomainError):
    """Database operation failed."""

    code = "DATABASE_ERROR"


class ConfigurationError(DomainError):
    """System misconfigured."""

    code = "CONFIGURATION_ERROR"


def service_boundary[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """
    Convert native exceptions to domain exceptions at service entry points.

    This decorator wraps service functions to automatically translate low-level
    exceptions (database, HTTP client, etc.) into domain-level exceptions that
    can be properly handled by the API layer.

    Usage:
        @service_boundary
        async def process_data():
            await db.execute(...)  # PostgresError -> DatabaseError
            await client.get(...)  # ClientError -> ExternalServiceError

    Args:
        func: Async service function to wrap

    Returns:
        Wrapped function that converts exceptions
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except DomainError:
            # Already a domain error, pass through
            raise
        except asyncpg.PostgresError as e:
            logger.error("database_error", function=func.__name__, error=str(e))
            raise DatabaseError(str(e), context={"function": func.__name__}) from e
        except (aiohttp.ClientError, aiohttp.ClientResponseError) as e:
            logger.error("external_api_error", function=func.__name__, error=str(e))
            raise ExternalServiceError(str(e), context={"function": func.__name__}) from e
        except Exception as e:
            logger.exception("unexpected_error", function=func.__name__)
            raise DomainError(
                str(e), context={"function": func.__name__, "type": type(e).__name__}
            ) from e

    return wrapper  # type: ignore[return-value]
