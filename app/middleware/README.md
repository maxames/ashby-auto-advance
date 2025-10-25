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

4. **Exception Handlers** - Standardize error responses
   - Catches HTTPException, RequestValidationError, and general exceptions
   - Returns standardized error format
   - Includes request_id in error responses

5. **Rate Limiting** - Setup function
   - Configures rate limiter
   - Returns limiter for decorator use in routes

## Files

- `request_id.py` - Request tracking and correlation
- `logging.py` - HTTP access logs with timing
- `errors.py` - Standardized error responses
- `cors.py` - CORS configuration
- `rate_limit.py` - Rate limiting setup

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
- `HTTP_XXX` - HTTP status code errors (400, 401, 404, etc.)
- `VALIDATION_ERROR` - Pydantic validation failures (includes details)
- `INTERNAL_ERROR` - Unexpected server errors

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

Each middleware has comprehensive unit tests in `tests/unit/test_middleware_*.py`.

