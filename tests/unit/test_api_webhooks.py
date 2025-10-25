"""Tests for Ashby webhook handler (app/api/webhooks.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.datastructures import Headers

from app.api.webhooks import handle_ashby_webhook, handle_interview_schedule_update


@pytest.mark.asyncio
async def test_ping_webhook_returns_200_ok(clean_db):
    """Verify ping webhook without signature returns 200."""
    # Create mock request with ping payload
    ping_payload = {"action": "ping", "type": "ping"}
    body = json.dumps(ping_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({})

    response = await handle_ashby_webhook(mock_request)

    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_invalid_json_returns_400(clean_db):
    """Malformed JSON payload returns 400."""
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=b"invalid json {")
    mock_request.headers = Headers({})

    with pytest.raises(Exception) as exc_info:
        await handle_ashby_webhook(mock_request)

    assert "400" in str(exc_info.value) or "Invalid JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_webhook_missing_signature_returns_401(clean_db):
    """Non-ping webhook without signature returns 401."""
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {"interviewSchedule": {"id": "test"}},
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({})

    with pytest.raises(Exception) as exc_info:
        await handle_ashby_webhook(mock_request)

    assert "401" in str(exc_info.value) or "Missing Ashby-Signature" in str(exc_info.value)


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(clean_db):
    """Invalid signature fails verification."""
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {"interviewSchedule": {"id": "test"}},
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "invalid_signature"})

    # Mock verify_ashby_signature to return False
    with patch("app.api.webhooks.verify_ashby_signature", return_value=False):
        with pytest.raises(Exception) as exc_info:
            await handle_ashby_webhook(mock_request)

        assert "401" in str(exc_info.value) or "Invalid signature" in str(exc_info.value)


@pytest.mark.asyncio
async def test_webhook_valid_signature_accepted(clean_db):
    """Valid signature passes verification."""
    schedule_id = str(uuid4())
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {"interviewSchedule": {"id": schedule_id}},
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    # Mock signature verification and schedule processing
    with (
        patch("app.api.webhooks.verify_ashby_signature", return_value=True),
        patch(
            "app.api.webhooks.handle_interview_schedule_update", new_callable=AsyncMock
        ) as mock_handler,
    ):
        response = await handle_ashby_webhook(mock_request)

        assert response.status_code == 204
        mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_invalid_payload_structure_returns_400(clean_db):
    """Payload fails Pydantic validation."""
    # Missing required fields for AshbyWebhookPayload
    invalid_payload = {
        "action": "interviewScheduleUpdate"
        # Missing 'data' field
    }
    body = json.dumps(invalid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    with patch("app.api.webhooks.verify_ashby_signature", return_value=True):
        with pytest.raises(Exception) as exc_info:
            await handle_ashby_webhook(mock_request)

        assert "400" in str(exc_info.value) or "Invalid payload" in str(exc_info.value)


@pytest.mark.asyncio
async def test_webhook_logs_to_audit_table(clean_db):
    """Successful webhook stores in ashby_webhook_payloads."""
    schedule_id = str(uuid4())
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {"interviewSchedule": {"id": schedule_id}},
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    with (
        patch("app.api.webhooks.verify_ashby_signature", return_value=True),
        patch("app.api.webhooks.handle_interview_schedule_update", new_callable=AsyncMock),
    ):
        await handle_ashby_webhook(mock_request)

        # Check database for audit entry
        async with clean_db.acquire() as conn:
            audit_entry = await conn.fetchrow(
                "SELECT * FROM ashby_webhook_payloads WHERE schedule_id = $1",
                schedule_id,
            )

            assert audit_entry is not None
            assert audit_entry["action"] == "interviewScheduleUpdate"
            assert str(audit_entry["schedule_id"]) == schedule_id


@pytest.mark.asyncio
async def test_webhook_interview_schedule_update_calls_handler(clean_db):
    """interviewScheduleUpdate triggers processing."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {
            "interviewSchedule": {
                "id": schedule_id,
                "status": "Scheduled",
                "applicationId": app_id,
            }
        },
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    with (
        patch("app.api.webhooks.verify_ashby_signature", return_value=True),
        patch(
            "app.api.webhooks.handle_interview_schedule_update", new_callable=AsyncMock
        ) as mock_handler,
    ):
        response = await handle_ashby_webhook(mock_request)

        assert response.status_code == 204
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0][0]
        assert "interviewSchedule" in call_args


@pytest.mark.asyncio
async def test_webhook_unknown_action_ignored(clean_db):
    """Unknown actions logged and ignored."""
    unknown_payload = {"action": "unknownAction", "data": {"some": "data"}}
    body = json.dumps(unknown_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    with patch("app.api.webhooks.verify_ashby_signature", return_value=True):
        response = await handle_ashby_webhook(mock_request)

        # Should still return 204 but not process anything
        assert response.status_code == 204


@pytest.mark.asyncio
async def test_webhook_returns_204_on_success(clean_db):
    """Successful processing returns 204."""
    schedule_id = str(uuid4())
    valid_payload = {
        "action": "interviewScheduleUpdate",
        "data": {"interviewSchedule": {"id": schedule_id}},
    }
    body = json.dumps(valid_payload).encode()

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = Headers({"Ashby-Signature": "valid_signature"})

    with (
        patch("app.api.webhooks.verify_ashby_signature", return_value=True),
        patch("app.api.webhooks.handle_interview_schedule_update", new_callable=AsyncMock),
    ):
        response = await handle_ashby_webhook(mock_request)

        assert response.status_code == 204


@pytest.mark.asyncio
async def test_handle_interview_schedule_update_missing_data(clean_db):
    """Missing schedule data handled gracefully."""
    # Data without interviewSchedule key
    data_without_schedule = {"someOtherKey": "value"}

    with patch(
        "app.services.interviews.process_schedule_update", new_callable=AsyncMock
    ) as mock_process:
        await handle_interview_schedule_update(data_without_schedule)

        # process_schedule_update should NOT be called
        mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_handle_interview_schedule_update_calls_service_layer(clean_db):
    """Correct data passed to process_schedule_update."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())

    schedule_data = {
        "id": schedule_id,
        "status": "Scheduled",
        "applicationId": app_id,
        "interviewStageId": stage_id,
    }

    data = {"interviewSchedule": schedule_data}

    with patch(
        "app.services.interviews.process_schedule_update", new_callable=AsyncMock
    ) as mock_process:
        await handle_interview_schedule_update(data)

        # Verify process_schedule_update was called with correct data
        mock_process.assert_called_once_with(schedule_data)
