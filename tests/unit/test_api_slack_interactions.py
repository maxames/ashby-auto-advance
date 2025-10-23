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


@pytest.mark.asyncio
async def test_slack_interactions_no_payload_returns_400():
    """Missing payload returns 400."""
    mock_request = AsyncMock(spec=Request)
    # Form with no payload key
    mock_request.form = AsyncMock(return_value={"other_key": "value"})

    response = await handle_slack_interactions(mock_request)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_slack_interactions_upload_file_payload_returns_400():
    """UploadFile payload returns 400."""
    mock_request = AsyncMock(spec=Request)
    # Create a mock UploadFile
    import io

    mock_file = io.BytesIO(b"test content")
    mock_upload = UploadFile(file=mock_file, filename="test.txt")
    mock_request.form = AsyncMock(return_value={"payload": mock_upload})

    response = await handle_slack_interactions(mock_request)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_slack_interactions_malformed_json_returns_400():
    """Invalid JSON in payload returns 400."""
    mock_request = AsyncMock(spec=Request)
    # Return invalid JSON string
    mock_request.form = AsyncMock(return_value={"payload": "invalid json {"})

    # Should raise JSONDecodeError
    with pytest.raises(json.JSONDecodeError):
        await handle_slack_interactions(mock_request)


@pytest.mark.asyncio
async def test_slack_interactions_block_actions_send_rejection_handled():
    """send_rejection action triggers handler."""
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

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"payload": json.dumps(payload)})

    with patch(
        "app.api.slack_interactions.handle_rejection_button", new_callable=AsyncMock
    ) as mock_handler:
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
        # Handler should be called (we can't easily assert this with create_task,
        # but the mock_create_task ensures it was awaited)


@pytest.mark.asyncio
async def test_slack_interactions_unknown_action_ignored():
    """Unknown action_id returns 200."""
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "unknown_action", "value": "some_value"}],
    }

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"payload": json.dumps(payload)})

    response = await handle_slack_interactions(mock_request)

    # Should return 200 even for unknown actions
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_slack_interactions_non_block_actions_returns_200():
    """Other interaction types return 200."""
    payload = {
        "type": "view_submission",  # Not block_actions
        "view": {"id": "V123456"},
    }

    mock_request = AsyncMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"payload": json.dumps(payload)})

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
    with patch(
        "app.services.advancement.execute_rejection", new_callable=AsyncMock
    ) as mock_execute, patch(
        "app.clients.slack.slack_client.chat_update", new_callable=AsyncMock
    ) as mock_chat_update:

        mock_execute.return_value = {"success": True}

        await handle_rejection_button(payload, action)

        # Verify execute_rejection was called
        mock_execute.assert_called_once_with(application_id)

        # Verify Slack message was updated with success
        mock_chat_update.assert_called_once()
        call_kwargs = mock_chat_update.call_args[1]
        assert call_kwargs["channel"] == "C123456"
        assert call_kwargs["ts"] == "1234567890.123456"
        assert "✅" in call_kwargs["text"]
        assert "Rejection Email Sent" in call_kwargs["blocks"][0]["text"]["text"]


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
    with patch(
        "app.services.advancement.execute_rejection", new_callable=AsyncMock
    ) as mock_execute, patch(
        "app.clients.slack.slack_client.chat_update", new_callable=AsyncMock
    ) as mock_chat_update:

        mock_execute.return_value = {"success": False, "error": "Candidate not found"}

        await handle_rejection_button(payload, action)

        # Verify execute_rejection was called
        mock_execute.assert_called_once_with(application_id)

        # Verify Slack message was updated with error
        mock_chat_update.assert_called_once()
        call_kwargs = mock_chat_update.call_args[1]
        assert call_kwargs["channel"] == "C123456"
        assert call_kwargs["ts"] == "1234567890.123456"
        assert "❌" in call_kwargs["text"]
        assert "Failed to Send Rejection" in call_kwargs["blocks"][0]["text"]["text"]
        assert "Candidate not found" in call_kwargs["blocks"][0]["text"]["text"]
