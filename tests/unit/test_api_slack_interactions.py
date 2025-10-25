"""Tests for Slack interactions handler (app/api/slack_interactions.py)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.datastructures import UploadFile

from app.api.slack_interactions import (
    handle_rejection_button,
    handle_slack_interactions,
)


def create_mock_slack_request(payload: dict | str | None = None, is_upload=False):
    """Create mock Slack request with signature verification bypassed.

    Args:
        payload: Payload dict/string or None
        is_upload: Whether payload is an UploadFile

    Returns:
        Mock request with body, headers, and form data
    """
    import io
    import time

    from starlette.datastructures import Headers

    mock_request = AsyncMock(spec=Request)

    # Mock body for signature verification
    if payload is None:
        body_str = ""
    elif isinstance(payload, dict):
        body_str = f"payload={json.dumps(payload)}"
    else:
        body_str = f"payload={payload}"

    mock_request.body = AsyncMock(return_value=body_str.encode())

    # Mock headers with valid signature data
    timestamp = str(int(time.time()))
    mock_request.headers = Headers(
        {
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": "v0=valid_signature_for_testing",
        }
    )

    # Mock form data
    if is_upload:
        mock_file = io.BytesIO(b"test content")
        mock_upload = UploadFile(file=mock_file, filename="test.txt")
        form_data = {"payload": mock_upload}
    elif payload is None:
        form_data = {"other_key": "value"}  # No payload key
    elif isinstance(payload, dict):
        form_data = {"payload": json.dumps(payload)}
    else:
        form_data = {"payload": payload}

    mock_request.form = AsyncMock(return_value=form_data)

    return mock_request


@pytest.mark.asyncio
async def test_slack_interactions_no_payload_returns_400(monkeypatch):
    """Missing payload returns 400."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    mock_request = create_mock_slack_request(payload=None)

    response = await handle_slack_interactions(mock_request)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_slack_interactions_upload_file_payload_returns_400(monkeypatch):
    """UploadFile payload returns 400."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    mock_request = create_mock_slack_request(payload={}, is_upload=True)

    response = await handle_slack_interactions(mock_request)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_slack_interactions_malformed_json_returns_400(monkeypatch):
    """Invalid JSON in payload returns 400."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    mock_request = create_mock_slack_request(payload="invalid json {")

    # Should raise JSONDecodeError
    with pytest.raises(json.JSONDecodeError):
        await handle_slack_interactions(mock_request)


@pytest.mark.asyncio
async def test_slack_interactions_block_actions_send_rejection_handled(monkeypatch):
    """send_rejection action triggers handler."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    application_id = str(uuid4())
    payload = {
        "type": "block_actions",
        "actions": [
            {
                "action_id": "send_rejection",
                "value": json.dumps({"application_id": application_id}),
            }
        ],
        "message": {"ts": "1234567890.123456"},
        "channel": {"id": "C123456"},
        "user": {"id": "U123456"},
    }

    mock_request = create_mock_slack_request(payload)

    # Mock asyncio.create_task to actually await the coroutine for testing
    original_create_task = asyncio.create_task

    async def mock_create_task(coro):
        # Execute the coroutine immediately for testing
        if asyncio.iscoroutine(coro):
            await coro
        return original_create_task(asyncio.sleep(0))  # Return a dummy task

    with patch("asyncio.create_task", side_effect=mock_create_task):
        response = await handle_slack_interactions(mock_request)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_slack_interactions_unknown_action_ignored(monkeypatch):
    """Unknown action_id returns 200."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "unknown_action", "value": "some_value"}],
    }

    mock_request = create_mock_slack_request(payload)

    response = await handle_slack_interactions(mock_request)

    # Should return 200 even for unknown actions
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_slack_interactions_non_block_actions_returns_200(monkeypatch):
    """Other interaction types return 200."""
    # Mock signature verification to pass
    monkeypatch.setattr("app.api.slack_interactions.verify_slack_signature", lambda *args: True)

    payload = {
        "type": "view_submission",  # Not block_actions
        "view": {"id": "V123456"},
    }

    mock_request = create_mock_slack_request(payload)

    response = await handle_slack_interactions(mock_request)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_handle_rejection_button_success_updates_message():
    """Successful rejection updates Slack message."""
    application_id = str(uuid4())

    payload = {
        "message": {"ts": "1234567890.123456"},
        "channel": {"id": "C123456"},
        "user": {"id": "U123456"},
    }

    action = {"value": json.dumps({"application_id": application_id})}

    # Mock execute_rejection to return success
    mock_success_blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Success"}}]

    with (
        patch("app.services.advancement.execute_rejection", new_callable=AsyncMock) as mock_execute,
        patch(
            "app.clients.slack.slack_client.chat_update", new_callable=AsyncMock
        ) as mock_chat_update,
        patch(
            "app.api.slack_interactions.build_rejection_success_message",
            return_value=mock_success_blocks,
        ) as mock_success_view,
    ):
        mock_execute.return_value = {"success": True}

        await handle_rejection_button(payload, action)

        # Verify execute_rejection was called
        mock_execute.assert_called_once_with(application_id)

        # Verify view builder was called
        mock_success_view.assert_called_once()

        # Verify Slack message was updated with success
        mock_chat_update.assert_called_once()
        call_kwargs = mock_chat_update.call_args[1]
        assert call_kwargs["channel"] == "C123456"
        assert call_kwargs["ts"] == "1234567890.123456"
        assert "✅" in call_kwargs["text"]
        assert call_kwargs["blocks"] == mock_success_blocks


@pytest.mark.asyncio
async def test_handle_rejection_button_failure_updates_message_with_error():
    """Failed rejection shows error message."""
    application_id = str(uuid4())

    payload = {
        "message": {"ts": "1234567890.123456"},
        "channel": {"id": "C123456"},
        "user": {"id": "U123456"},
    }

    action = {"value": json.dumps({"application_id": application_id})}

    # Mock execute_rejection to return failure
    mock_error_blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Error"}}]

    with (
        patch("app.services.advancement.execute_rejection", new_callable=AsyncMock) as mock_execute,
        patch(
            "app.clients.slack.slack_client.chat_update", new_callable=AsyncMock
        ) as mock_chat_update,
        patch(
            "app.api.slack_interactions.build_rejection_error_message",
            return_value=mock_error_blocks,
        ) as mock_error_view,
    ):
        mock_execute.return_value = {"success": False, "error": "Candidate not found"}

        await handle_rejection_button(payload, action)

        # Verify execute_rejection was called
        mock_execute.assert_called_once_with(application_id)

        # Verify view builder was called with error message
        mock_error_view.assert_called_once_with("Candidate not found")

        # Verify Slack message was updated with error
        mock_chat_update.assert_called_once()
        call_kwargs = mock_chat_update.call_args[1]
        assert call_kwargs["channel"] == "C123456"
        assert call_kwargs["ts"] == "1234567890.123456"
        assert "❌" in call_kwargs["text"]
        assert call_kwargs["blocks"] == mock_error_blocks
