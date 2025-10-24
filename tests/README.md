# Test Suite Documentation

## Structure

The test suite is organized into four main categories:

- **`tests/unit/`** - Unit tests (13 files, ~100 tests)
  - Test service/client logic with mocked dependencies
  - Fast execution, comprehensive coverage
  - Examples: `test_rules.py`, `test_advancement.py`, `test_security.py`

- **`tests/integration/`** - Integration tests (4 files, ~60 tests)
  - Test service workflows with real database
  - Medium speed, business logic validation
  - Examples: `test_advancement_flow.py`, `test_e2e_scenarios.py`

- **`tests/e2e/`** - End-to-end HTTP tests (3 files, ~10 tests)
  - Test complete HTTP flows through FastAPI
  - Slower execution, critical path validation
  - Examples: `test_http_webhook_flow.py`, `test_http_advancement_flow.py`

- **`tests/contracts/`** - Payload contract tests (2 files, ~20 tests)
  - Validate external API payload structures
  - Fast execution, schema validation
  - Examples: `test_webhook_payloads.py`, `test_slack_payloads.py`

- **`tests/fixtures/`** - Test fixtures and factories
  - Reusable test data generators
  - `factories.py` - Database record creation helpers
  - `sample_payloads.py` - Example API payloads

## Running Tests

### All Tests

```bash
# Run complete test suite
pytest tests/ -v

# With coverage report
pytest --cov=app --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=app --cov-report=html
```

### By Category

```bash
# Fast tests only (unit + contract)
pytest tests/unit tests/contracts -v

# Integration tests (with database)
pytest tests/integration -v

# E2E HTTP tests (slowest)
pytest tests/e2e -v -m e2e
```

### Specific Tests

```bash
# Single test file
pytest tests/integration/test_advancement_flow.py -v

# Single test function
pytest tests/integration/test_e2e_scenarios.py::test_panel_interview_all_pass_advances -v

# Tests matching pattern
pytest tests/ -k "advancement" -v
```

### With Options

```bash
# Stop on first failure
pytest tests/ -x

# Show detailed output
pytest tests/ -vv

# Show print statements
pytest tests/ -s

# Run in parallel (requires pytest-xdist)
pytest tests/ -n auto
```

## Manual Testing

Use the interactive E2E testing script for development and debugging:

### Interactive Menu

```bash
python scripts/manual_e2e.py

# Available scenarios:
#   1. Single interviewer pass
#   2. Panel all pass
#   3. Panel one fails
#   4. Health check only
```

### Specific Scenario

```bash
# Run single interviewer scenario
python scripts/manual_e2e.py --scenario single

# Run panel scenario
python scripts/manual_e2e.py --scenario panel

# Health check only
python scripts/manual_e2e.py --scenario health
```

### Test Against Different Environments

```bash
# Test against local server (default)
python scripts/manual_e2e.py --url http://localhost:8000

# Test against staging
python scripts/manual_e2e.py --url https://staging.onrender.com

# Test against staging using env var
TEST_BASE_URL=https://staging.onrender.com python scripts/manual_e2e.py
```

### Replay Production Webhooks

```bash
# Save webhook payload to file (from production logs)
echo '{"action": "interviewScheduleUpdate", ...}' > webhook_payload.json

# Replay against local environment
python scripts/manual_e2e.py --replay webhook_payload.json

# Replay against staging
python scripts/manual_e2e.py --replay webhook_payload.json --url https://staging.onrender.com
```

## Test Coverage

Current coverage: **72%**

Target coverage by category:
- Unit tests: 80%+ (comprehensive business logic)
- Integration tests: 70%+ (critical workflows)
- E2E tests: N/A (not measured by coverage, validates HTTP layer)

Run coverage report:
```bash
pytest --cov=app --cov-report=term-missing --cov-report=html
open htmlcov/index.html  # View in browser
```

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_my_service.py
import pytest
from unittest.mock import AsyncMock
from app.services.my_service import process_data

@pytest.mark.asyncio
async def test_process_data_success(monkeypatch):
    """Test successful data processing."""
    # Mock external dependencies
    mock_api = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("app.clients.api.call", mock_api)

    # Execute
    result = await process_data("input")

    # Assert
    assert result == "expected"
    mock_api.assert_called_once()
```

### Integration Test Example

```python
# tests/integration/test_my_workflow.py
import pytest
from tests.fixtures.factories import create_test_rule

@pytest.mark.asyncio
async def test_complete_workflow(clean_db):
    """Test complete workflow with real database."""
    # Setup: Create test data
    rule = await create_test_rule(clean_db, threshold="3")

    # Execute: Run business logic
    from app.services.my_service import process_workflow
    result = await process_workflow(rule["rule_id"])

    # Assert: Verify database state
    async with clean_db.acquire() as conn:
        record = await conn.fetchrow("SELECT * FROM results WHERE id = $1", result)
        assert record is not None
```

### E2E HTTP Test Example

```python
# tests/e2e/test_my_endpoint.py
import pytest
from tests.e2e.conftest import sign_webhook

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_endpoint_flow(http_client, clean_db):
    """Test complete HTTP flow."""
    # Send HTTP request
    response = await http_client.post(
        "/my-endpoint",
        json={"key": "value"},
    )

    # Assert response
    assert response.status_code == 200

    # Verify database state
    async with clean_db.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM my_table")
        assert count == 1
```

## Fixtures

Common fixtures available in all tests:

- `clean_db` - Clean database with connection pool
- `sample_interview` - Sample interview definition
- `sample_interview_event` - Sample interview event with schedule
- `sample_slack_user` - Sample Slack user
- `http_client` - HTTP client for E2E tests (from `tests/e2e/conftest.py`)

See `tests/conftest.py` and `tests/e2e/conftest.py` for full fixture list.

## Continuous Integration

Tests run automatically on every commit via GitHub Actions:

1. **Lint** - `ruff check app/`
2. **Format** - `ruff format app/ --check`
3. **Type check** - `pyright app/` (non-blocking)
4. **Unit + Integration tests** - `pytest --cov=app`
5. **E2E tests** - `pytest tests/e2e -v -m e2e`

View CI results: `.github/workflows/ci.yml`

## Troubleshooting

### Database Connection Errors

```bash
# Ensure PostgreSQL is running
psql $DATABASE_URL -c "SELECT 1"

# Reset test database
psql $DATABASE_URL -f database/schema.sql
```

### Import Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Install test dependencies
pip install -r requirements-dev.txt
```

### Slow Tests

```bash
# Run only fast tests
pytest tests/unit tests/contracts -v

# Skip E2E tests
pytest tests/ -v -m "not e2e"
```

### Flaky Tests

```bash
# Run test multiple times
pytest tests/integration/test_my_test.py --count=10

# Run with verbose output
pytest tests/integration/test_my_test.py -vv -s
```

## Best Practices

1. **Use factories** - Use `tests/fixtures/factories.py` for creating test data
2. **Mock external APIs** - Never make real API calls in tests
3. **Clean database** - Always use `clean_db` fixture for isolation
4. **Descriptive names** - Test names should describe what they test
5. **One assertion focus** - Each test should validate one behavior
6. **Avoid test interdependence** - Tests should run in any order
7. **Fast tests** - Keep unit tests under 100ms each

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [httpx testing](https://www.python-httpx.org/async/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)

