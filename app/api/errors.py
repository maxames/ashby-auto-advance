"""FastAPI exception handlers for domain errors."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from structlog import get_logger

from app.core.config import settings
from app.core.errors import DomainError

logger = get_logger()

# Map domain error codes to HTTP status codes
ERROR_STATUS_MAP = {
    "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "EXTERNAL_SERVICE_ERROR": status.HTTP_502_BAD_GATEWAY,
    "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "CONFIGURATION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "DOMAIN_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """
    Handle domain-level exceptions and translate to HTTP responses.

    Domain errors are expected/handled errors, so log at WARNING level.
    Includes error context in response if expose_error_details is enabled.

    Args:
        request: FastAPI request
        exc: Domain exception

    Returns:
        JSON error response with appropriate status code
    """
    http_status = ERROR_STATUS_MAP.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Log at WARNING level - these are handled domain errors
    logger.warning(
        "domain_error_handled",
        error_code=exc.code,
        http_status=http_status,
        message=exc.message,
        context=exc.context,
        request_id=getattr(request.state, "request_id", None),
    )

    # Build error response
    content: dict[str, any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }

    # Include details if configured (development/staging mode)
    if settings.expose_error_details and exc.context:
        content["error"]["details"] = exc.context

    return JSONResponse(status_code=http_status, content=content)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException and return standardized error format.

    Error format:
    {
        "error": {
            "code": "HTTP_XXX",
            "message": "Error message",
            "request_id": "uuid"
        }
    }

    Args:
        request: FastAPI request
        exc: HTTP exception

    Returns:
        JSON error response
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": str(exc.detail),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle RequestValidationError and return standardized error format.

    Error format includes validation details from Pydantic.

    Args:
        request: FastAPI request
        exc: Pydantic validation exception

    Returns:
        JSON error response with validation details
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data",
                "details": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions and return standardized error format.

    Logs the full exception with stack trace for debugging.
    These are unexpected errors, so log at ERROR level.

    Args:
        request: FastAPI request
        exc: Unexpected exception

    Returns:
        Generic 500 error response
    """
    # Log at ERROR level with full stack trace - unexpected error
    logger.exception(
        "unhandled_exception",
        error_type=type(exc).__name__,
        request_id=getattr(request.state, "request_id", None),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Configure exception handlers for the application.

    Registers handlers for:
    - DomainError (domain-level exceptions)
    - HTTPException (FastAPI exceptions)
    - RequestValidationError (Pydantic validation)
    - Exception (catch-all for unexpected errors)

    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, general_exception_handler)  # type: ignore[arg-type]
