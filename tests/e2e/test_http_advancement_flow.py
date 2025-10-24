"""E2E HTTP tests for advancement flow."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.e2e.conftest import sign_webhook
from tests.fixtures.factories import (
    create_ashby_webhook_payload,
    create_test_feedback,
    create_test_rule,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_http_advancement_flow(
    http_client, clean_db, mock_ashby_api, sample_interview, monkeypatch
):
    """Full flow: webhook → feedback sync → advancement via HTTP."""
    from app.core.config import settings

    # Setup: Create advancement rule
    rule_data = await create_test_rule(
        clean_db,
        interview_id=sample_interview["interview_id"],
        operator=">=",
        threshold="3",
    )

    schedule_id = str(uuid4())
    event_id = str(uuid4())
    application_id = str(uuid4())

    # Step 1: POST webhook (schedule interview)
    payload = create_ashby_webhook_payload(
        schedule_id=schedule_id,
        status="Scheduled",
        event_id=event_id,
    )
    payload["data"]["interviewSchedule"]["applicationId"] = application_id
    payload["data"]["interviewSchedule"]["interviewStageId"] = rule_data["interview_stage_id"]
    payload["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = sample_interview[
        "interview_id"
    ]

    body = json.dumps(payload)
    signature = sign_webhook(body, settings.ashby_webhook_secret)

    response = await http_client.post(
        "/webhooks/ashby",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature,
        },
    )

    assert response.status_code == 204

    # Update schedule to have advancement fields
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            UPDATE interview_schedules
            SET interview_plan_id = $1, status = 'Complete'
            WHERE schedule_id = $2
            """,
            rule_data["interview_plan_id"],
            schedule_id,
        )

    # Step 2: Add passing feedback
    interviewer_id = str(uuid4())
    await create_test_feedback(
        clean_db,
        event_id=event_id,
        application_id=application_id,
        interviewer_id=interviewer_id,
        interview_id=sample_interview["interview_id"],
        submitted_values={"overall_score": 4},
        submitted_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # Step 3: Mock advancement API and run evaluation
    mock_advance = AsyncMock(return_value={"id": application_id})
    from app.services import advancement

    monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)

    # Trigger advancement evaluation
    await advancement.process_advancement_evaluations()

    # Assert: advancement was executed
    assert mock_advance.called

    # Verify audit trail
    async with clean_db.acquire() as conn:
        execution = await conn.fetchrow(
            "SELECT * FROM advancement_executions WHERE schedule_id = $1",
            schedule_id,
        )
        assert execution is not None
        assert execution["execution_status"] == "success"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_health_check_includes_scheduler(http_client):
    """GET /health → includes scheduler status."""
    response = await http_client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Verify health check structure
    assert "status" in data
    assert "database" in data

    # Verify scheduler status is included
    assert "scheduler" in data
    # Note: In E2E tests without full lifespan, scheduler may be "stopped"
    assert data["scheduler"] in ["running", "stopped"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_updates_schedule_status(
    http_client, clean_db, mock_ashby_api, sample_interview
):
    """Webhook with status change → updates schedule in DB."""
    from app.core.config import settings

    schedule_id = str(uuid4())

    # Send initial webhook (Scheduled)
    payload1 = create_ashby_webhook_payload(schedule_id=schedule_id, status="Scheduled")
    # Use existing interview_id to avoid FK violations
    payload1["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = sample_interview[
        "interview_id"
    ]

    body1 = json.dumps(payload1)
    signature1 = sign_webhook(body1, settings.ashby_webhook_secret)

    response1 = await http_client.post(
        "/webhooks/ashby",
        content=body1,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature1,
        },
    )

    assert response1.status_code == 204

    # Verify initial status
    async with clean_db.acquire() as conn:
        schedule = await conn.fetchrow(
            "SELECT status FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert schedule["status"] == "Scheduled"

    # Send status update (Complete)
    payload2 = create_ashby_webhook_payload(schedule_id=schedule_id, status="Complete")
    # Use same interview_id
    payload2["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = sample_interview[
        "interview_id"
    ]

    body2 = json.dumps(payload2)
    signature2 = sign_webhook(body2, settings.ashby_webhook_secret)

    response2 = await http_client.post(
        "/webhooks/ashby",
        content=body2,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature2,
        },
    )

    assert response2.status_code == 204

    # Verify updated status
    async with clean_db.acquire() as conn:
        schedule = await conn.fetchrow(
            "SELECT status FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert schedule["status"] == "Complete"
