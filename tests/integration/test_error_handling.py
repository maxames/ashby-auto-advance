"""Integration tests for end-to-end error handling flow.

Verifies that domain exceptions raised by services are properly handled
by the API layer and converted to appropriate HTTP responses with correct
status codes and error formats.

These tests use direct mocking to verify the error handling architecture works.
Note: Some service functions have try/except blocks that currently swallow
exceptions - those should be refactored to allow errors to propagate per the plan.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import ExternalServiceError, NotFoundError
from app.main import app


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401():
    """Webhook authentication failure returns 401 with standardized error format."""
    payload = {"action": "interviewSchedule.updated", "interviewSchedule": {}}
    body = json.dumps(payload).encode()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/ashby",
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-ashby-signature": "sha256=invalid_signature",
            },
        )

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "HTTP_401"
    assert "request_id" in data["error"]


@pytest.mark.asyncio
async def test_service_external_service_error_returns_502():
    """Service raising External ServiceError returns 502 Bad Gateway.

    Tests: API endpoint → Service (raises ExternalServiceError) → Handler → HTTP 502
    """
    # Patch where the function is used (in admin.py), not where it's defined
    with patch(
        "app.api.admin.sync_feedback_forms",
        new=AsyncMock(
            side_effect=ExternalServiceError(
                "Ashby API unavailable",
                service="ashby",
                context={"endpoint": "feedbackFormDefinition.list"},
            )
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/admin/sync-forms")

    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "EXTERNAL_SERVICE_ERROR"
    assert "Ashby API unavailable" in data["error"]["message"]
    assert "request_id" in data["error"]
    # Details included when expose_error_details=True (default in dev)
    if "details" in data["error"]:
        assert data["error"]["details"]["service"] == "ashby"


@pytest.mark.asyncio
async def test_service_not_found_error_returns_404():
    """Service raising NotFoundError returns 404 Not Found.

    Tests: API endpoint → Service (raises NotFoundError) → Handler → HTTP 404
    """
    with patch(
        "app.services.admin.create_advancement_rule",
        new=AsyncMock(
            side_effect=NotFoundError(
                "Interview plan not found", context={"plan_id": "nonexistent-plan"}
            )
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/admin/create-advancement-rule",
                json={
                    "job_id": "job-123",
                    "interview_plan_id": "nonexistent-plan",
                    "interview_stage_id": "stage-123",
                    "target_stage_id": None,
                    "requirements": [],
                    "actions": [],
                },
            )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Interview plan not found" in data["error"]["message"]
    assert "request_id" in data["error"]
