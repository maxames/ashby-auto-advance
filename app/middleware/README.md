# Middleware

HTTP middleware for cross-cutting concerns.

## Order Matters!

Middleware executes in reverse order (bottom to top in the stack), so the order in `main.py` is critical:

1. **RequestIDMiddleware** - Executes FIRST
   - Generates unique request ID
   - Binds to structlog context
   - Adds X-Request-ID header to response

2. **LoggingMiddleware** - Executes SECOND
   - Logs request_started
   - Logs request_completed with timing
   - Automatically includes request_id from context

3. **CORS** - Executes THIRD
   - Handles cross-origin requests
   - Allows configured frontend URLs
   - Includes X-Request-ID in allowed headers

4. **Exception Handlers** - Standardize error responses (now in `app/api/errors.py`)
   - Catches DomainError, HTTPException, RequestValidationError, and general exceptions
   - Returns standardized error format
   - Maps domain exceptions to HTTP status codes
   - Includes request_id in error responses
   - Supports `EXPOSE_ERROR_DETAILS` config flag

5. **Rate Limiting** - Setup function
   - Configures rate limiter
   - Returns limiter for decorator use in routes

## Files

- `request_id.py` - Request tracking and correlation
- `logging.py` - HTTP access logs with timing
- `cors.py` - CORS configuration
- `rate_limit.py` - Rate limiting setup
- ~~`errors.py`~~ **MOVED TO** `app/api/errors.py` - Exception handlers

## Error Handling Architecture

Error handling now follows clean architecture:

- **Domain Exceptions** (`app/core/errors.py`) - Pure Python exceptions with no framework dependencies
  - `DomainError` - Base class
  - `NotFoundError` - Resource not found (404)
  - `ValidationError` - Input validation failed (422)
  - `ExternalServiceError` - Ashby/Slack API failures (502)
  - `DatabaseError` - PostgreSQL failures (500)
  - `ConfigurationError` - Missing/invalid config (500)

- **FastAPI Handlers** (`app/api/errors.py`) - Maps domain exceptions to HTTP responses
  - Translates exception codes to HTTP status codes
  - Includes error context when `EXPOSE_ERROR_DETAILS=true`
  - Logs domain errors at WARNING level, unexpected at ERROR

- **Service Boundaries** (`@service_boundary` decorator) - Converts native exceptions at service entry points
  - Catches `asyncpg.PostgresError` → `DatabaseError`
  - Catches `aiohttp.ClientError` → `ExternalServiceError`
  - Passes through `DomainError` unchanged

## Error Format

All errors return this standardized format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {},
    "request_id": "uuid"
  }
}
```

Error codes:
- `NOT_FOUND` - Resource not found (404)
- `VALIDATION_ERROR` - Input validation failed (422)
- `EXTERNAL_SERVICE_ERROR` - External API failure (502)
- `DATABASE_ERROR` - Database operation failed (500)
- `CONFIGURATION_ERROR` - System misconfigured (500)
- `HTTP_XXX` - HTTP status code errors (400, 401, etc.)
- `INTERNAL_ERROR` - Unexpected server errors (500)

## Request ID

Every request gets a unique UUID that:
- Is returned in `X-Request-ID` response header
- Is included in all log messages (via structlog context)
- Is included in all error responses
- Enables request correlation across logs

## Usage in Routes

Rate limiting can be applied per-route:

```python
from app.middleware.rate_limit import get_limiter

limiter = get_limiter()

@router.post("/endpoint")
@limiter.limit("100/minute")
async def my_endpoint():
    pass
```

## Testing

Middleware tests in `tests/unit/test_middleware_*.py`.
Error handling tests in `tests/unit/test_api_errors.py`.

