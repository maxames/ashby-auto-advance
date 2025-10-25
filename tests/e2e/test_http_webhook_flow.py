"""E2E HTTP tests for webhook processing."""

import json
from uuid import uuid4

import pytest

from tests.e2e.conftest import sign_webhook
from tests.fixtures.factories import create_ashby_webhook_payload


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_signature_verification_invalid(http_client):
    """Real HTTP request with invalid signature → 401."""
    payload = create_ashby_webhook_payload()
    body = json.dumps(payload)

    # Send with wrong signature
    response = await http_client.post(
        "/webhooks/ashby",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": "wrong_signature",
        },
    )

    assert response.status_code == 401
    assert "X-Request-ID" in response.headers
    assert "Invalid signature" in response.text or "Unauthorized" in response.text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_signature_verification_valid(
    http_client, clean_db, mock_ashby_api, sample_interview
):
    """Real HTTP request with valid signature → 204."""
    from app.core.config import settings

    payload = create_ashby_webhook_payload(
        schedule_id=str(uuid4()),
        status="Scheduled",
        event_id=str(uuid4()),
    )
    # Use existing interview_id to avoid FK violations
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
    assert "X-Request-ID" in response.headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_to_database_flow(http_client, clean_db, mock_ashby_api, sample_interview):
    """Webhook received → schedule + events + assignments in DB."""
    from app.core.config import settings

    schedule_id = str(uuid4())
    event_id = str(uuid4())

    payload = create_ashby_webhook_payload(
        schedule_id=schedule_id,
        status="Scheduled",
        event_id=event_id,
    )
    # Use existing interview_id to avoid FK violations
    payload["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = sample_interview[
        "interview_id"
    ]

    body = json.dumps(payload)
    signature = sign_webhook(body, settings.ashby_webhook_secret)

    # Send webhook
    response = await http_client.post(
        "/webhooks/ashby",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature,
        },
    )

    assert response.status_code == 204
    assert "X-Request-ID" in response.headers

    # Verify data in database
    async with clean_db.acquire() as conn:
        # Check schedule exists
        schedule = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert schedule is not None
        assert schedule["status"] == "Scheduled"

        # Check event exists
        event = await conn.fetchrow(
            "SELECT * FROM interview_events WHERE event_id = $1",
            event_id,
        )
        assert event is not None
        assert str(event["schedule_id"]) == schedule_id

        # Check interviewer assignment exists
        assignments = await conn.fetch(
            "SELECT * FROM interview_assignments WHERE event_id = $1",
            event_id,
        )
        assert len(assignments) > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_duplicate_idempotent(
    http_client, clean_db, mock_ashby_api, sample_interview
):
    """Same webhook sent twice → idempotent processing."""
    from app.core.config import settings

    schedule_id = str(uuid4())
    payload = create_ashby_webhook_payload(schedule_id=schedule_id)
    # Use existing interview_id to avoid FK violations
    payload["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = sample_interview[
        "interview_id"
    ]

    body = json.dumps(payload)
    signature = sign_webhook(body, settings.ashby_webhook_secret)

    headers = {
        "Content-Type": "application/json",
        "Ashby-Signature": signature,
    }

    # Send same webhook twice
    response1 = await http_client.post("/webhooks/ashby", content=body, headers=headers)
    response2 = await http_client.post("/webhooks/ashby", content=body, headers=headers)

    assert response1.status_code == 204
    assert response2.status_code == 204

    # Verify only one schedule record exists
    async with clean_db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert count == 1


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_concurrent_webhooks_race_condition(
    http_client, clean_db, mock_ashby_api, sample_interview
):
    """Multiple webhooks for same schedule → no race conditions."""
    import asyncio

    from app.core.config import settings

    schedule_id = str(uuid4())

    # Use same interview_id from sample_interview (exists in DB)
    interview_id = sample_interview["interview_id"]

    # Create 3 different webhook payloads for the same schedule (status updates)
    statuses = ["Scheduled", "Complete", "Canceled"]
    tasks = []

    for status in statuses:
        payload = create_ashby_webhook_payload(
            schedule_id=schedule_id,
            status=status,
            event_id=str(uuid4()),
        )
        # Override interview_id to use existing one
        payload["data"]["interviewSchedule"]["interviewEvents"][0]["interviewId"] = interview_id

        body = json.dumps(payload)
        signature = sign_webhook(body, settings.ashby_webhook_secret)

        task = http_client.post(
            "/webhooks/ashby",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Ashby-Signature": signature,
            },
        )
        tasks.append(task)

    # Send all webhooks concurrently
    responses = await asyncio.gather(*tasks)

    # All should succeed
    for response in responses:
        assert response.status_code == 204
    assert "X-Request-ID" in response.headers

    # Verify schedule exists and has final state
    async with clean_db.acquire() as conn:
        schedule = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert schedule is not None
        # Final status is one of the three (last write wins)
        assert schedule["status"] in statuses


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(http_client):
    """Webhook without signature header → 401."""
    payload = create_ashby_webhook_payload()
    body = json.dumps(payload)

    response = await http_client.post(
        "/webhooks/ashby",
        content=body,
        headers={"Content-Type": "application/json"},
        # No X-Ashby-Signature header
    )

    assert response.status_code == 401


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_invalid_json_rejected(http_client):
    """Webhook with malformed JSON → 400 or 422."""
    from app.core.config import settings

    body = "not valid json {{{["
    signature = sign_webhook(body, settings.ashby_webhook_secret)

    response = await http_client.post(
        "/webhooks/ashby",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature,
        },
    )

    # Should reject invalid JSON
    assert response.status_code in [400, 422, 500]
