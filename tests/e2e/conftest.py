"""E2E test fixtures for HTTP testing."""

import hashlib
import hmac
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def http_client(clean_db):
    """HTTP client for testing actual FastAPI app.

    Uses the clean_db fixture to ensure database is clean for each test.
    The app's lifespan context manager is not run - we test the app
    without scheduler and background jobs for faster, more deterministic tests.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def sign_webhook(body: str, secret: str) -> str:
    """Compute Ashby webhook signature.

    Args:
        body: Raw request body as string
        secret: Webhook secret for HMAC

    Returns:
        Ashby signature in format: "sha256=<hex_digest>"
    """
    hex_digest = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"sha256={hex_digest}"


def sign_slack_request(body: str, timestamp: str, secret: str) -> str:
    """Compute Slack request signature.

    Args:
        body: Raw request body as string
        timestamp: Request timestamp
        secret: Slack signing secret

    Returns:
        Slack signature in format 'v0=<hex_signature>'
    """
    sig_basestring = f"v0:{timestamp}:{body}"
    signature = hmac.new(
        secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return f"v0={signature}"


@pytest.fixture
def mock_ashby_api():
    """Mock Ashby API calls for E2E tests."""
    with patch("app.clients.ashby.ashby_client.post") as mock_post:
        # Default responses for common endpoints
        def ashby_response(endpoint, data):
            if endpoint == "interviewStage.info":
                return {
                    "success": True,
                    "results": {
                        "id": data.get("id"),
                        "interviewPlanId": str(uuid4()),
                        "jobId": str(uuid4()),
                    },
                }
            elif endpoint == "interview.info":
                return {
                    "success": True,
                    "results": {
                        "id": data.get("id"),
                        "title": "Test Interview",
                        "feedbackFormDefinitionId": str(uuid4()),
                    },
                }
            # Default success for other endpoints
            return {"success": True, "results": {}}

        mock_post.side_effect = lambda endpoint, data: ashby_response(endpoint, data)
        yield mock_post
