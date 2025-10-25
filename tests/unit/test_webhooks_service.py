"""Tests for webhook service (app/services/webhooks.py)."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.services.webhooks import log_webhook_to_audit


@pytest.mark.asyncio
async def test_log_webhook_to_audit_stores_in_database(clean_db):
    """Verify webhook is logged to audit table."""
    schedule_id = str(uuid4())
    action = "interviewScheduleUpdate"
    payload = {
        "action": action,
        "data": {"interviewSchedule": {"id": schedule_id, "status": "Scheduled"}},
    }

    await log_webhook_to_audit(schedule_id, action, payload)

    # Verify entry was created
    async with clean_db.acquire() as conn:
        audit_entry = await conn.fetchrow(
            "SELECT * FROM ashby_webhook_payloads WHERE schedule_id = $1",
            schedule_id,
        )

        assert audit_entry is not None
        assert audit_entry["action"] == action
        assert str(audit_entry["schedule_id"]) == schedule_id

        # Verify payload was stored as JSON
        stored_payload = json.loads(audit_entry["payload"])
        assert stored_payload == payload


@pytest.mark.asyncio
async def test_log_webhook_to_audit_handles_complex_payload(clean_db):
    """Verify complex nested payloads are stored correctly."""
    schedule_id = str(uuid4())
    action = "interviewScheduleUpdate"

    # Complex payload with nested structures
    payload = {
        "action": action,
        "data": {
            "interviewSchedule": {
                "id": schedule_id,
                "status": "Complete",
                "interviewEvents": [
                    {
                        "id": str(uuid4()),
                        "title": "Technical Screen",
                        "interviewer": {
                            "name": "Jane Doe",
                            "email": "jane@example.com",
                        },
                    }
                ],
                "metadata": {"key1": "value1", "nested": {"key2": "value2"}},
            }
        },
    }

    await log_webhook_to_audit(schedule_id, action, payload)

    # Verify complex payload was stored correctly
    async with clean_db.acquire() as conn:
        audit_entry = await conn.fetchrow(
            "SELECT * FROM ashby_webhook_payloads WHERE schedule_id = $1",
            schedule_id,
        )

        assert audit_entry is not None
        stored_payload = json.loads(audit_entry["payload"])
        assert stored_payload == payload
        assert stored_payload["data"]["interviewSchedule"]["metadata"]["nested"]["key2"] == "value2"


@pytest.mark.asyncio
async def test_log_webhook_to_audit_multiple_entries(clean_db):
    """Verify multiple webhook logs can be stored."""
    schedule_id_1 = str(uuid4())
    schedule_id_2 = str(uuid4())
    action = "interviewScheduleUpdate"

    payload_1 = {"action": action, "data": {"interviewSchedule": {"id": schedule_id_1}}}
    payload_2 = {"action": action, "data": {"interviewSchedule": {"id": schedule_id_2}}}

    await log_webhook_to_audit(schedule_id_1, action, payload_1)
    await log_webhook_to_audit(schedule_id_2, action, payload_2)

    # Verify both entries exist
    async with clean_db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM ashby_webhook_payloads WHERE schedule_id IN ($1, $2)",
            schedule_id_1,
            schedule_id_2,
        )

        assert count == 2


@pytest.mark.asyncio
async def test_log_webhook_to_audit_sets_timestamp(clean_db):
    """Verify received_at timestamp is set automatically."""
    schedule_id = str(uuid4())
    action = "interviewScheduleUpdate"
    payload = {"action": action, "data": {"interviewSchedule": {"id": schedule_id}}}

    await log_webhook_to_audit(schedule_id, action, payload)

    # Verify timestamp was set
    async with clean_db.acquire() as conn:
        audit_entry = await conn.fetchrow(
            "SELECT * FROM ashby_webhook_payloads WHERE schedule_id = $1",
            schedule_id,
        )

        assert audit_entry is not None
        assert audit_entry["received_at"] is not None
        # Timestamp should be recent (timezone-aware)
        assert audit_entry["received_at"].tzinfo is not None
