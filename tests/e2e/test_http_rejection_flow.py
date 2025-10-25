"""E2E HTTP tests for rejection flow."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.e2e.conftest import sign_slack_request


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rejection_button_click_http(http_client, clean_db, monkeypatch):
    """POST /slack/interactions with rejection button → archives candidate."""
    import time

    from app.core.config import settings

    application_id = str(uuid4())

    # Create Slack button click payload
    payload = {
        "type": "block_actions",
        "user": {"id": "U123456", "name": "test.user"},
        "trigger_id": f"trigger_{uuid4()}",
        "response_url": "https://hooks.slack.com/test",
        "actions": [
            {
                "action_id": "reject_candidate",
                "block_id": "actions",
                "value": json.dumps({"application_id": application_id}),
                "action_ts": str(int(time.time())),
            }
        ],
        "message": {
            "ts": "1234567890.123456",
            "text": "Test message",
        },
        "channel": {"id": "C123456"},
    }

    payload_str = json.dumps(payload)
    timestamp = str(int(time.time()))

    # Compute Slack signature
    signature = sign_slack_request(
        f"payload={payload_str}", timestamp, settings.slack_signing_secret
    )

    # Mock external API calls
    mock_archive = AsyncMock(return_value={"success": True})
    mock_slack_update = AsyncMock()

    from app.clients import ashby, slack

    monkeypatch.setattr(ashby, "archive_candidate", mock_archive)
    monkeypatch.setattr(slack.slack_client, "chat_update", mock_slack_update)

    # Send request
    response = await http_client.post(
        "/slack/interactions",
        data=f"payload={payload_str}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature,
        },
    )

    # Note: Slack interactions return 200 immediately for async processing
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_slack_signature_verification_invalid(http_client):
    """Slack request with invalid signature → should reject."""
    import time

    # Minimal valid payload with actions array
    payload = {
        "type": "block_actions",
        "user": {"id": "U123456"},
        "actions": [
            {
                "action_id": "some_action",
                "value": "{}",
            }
        ],
    }

    payload_str = json.dumps(payload)
    timestamp = str(int(time.time()))

    response = await http_client.post(
        "/slack/interactions",
        data=f"payload={payload_str}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": "v0=wrong_signature",
        },
    )

    assert response.status_code == 401
    assert "X-Request-ID" in response.headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_slack_old_timestamp_rejected(http_client):
    """Slack request with old timestamp → should reject."""
    import time

    from app.core.config import settings

    # Minimal valid payload with actions array
    payload = {
        "type": "block_actions",
        "user": {"id": "U123456"},
        "actions": [
            {
                "action_id": "some_action",
                "value": "{}",
            }
        ],
    }
    payload_str = json.dumps(payload)

    # Timestamp from 10 minutes ago (should be rejected)
    old_timestamp = str(int(time.time()) - 600)
    signature = sign_slack_request(
        f"payload={payload_str}", old_timestamp, settings.slack_signing_secret
    )

    response = await http_client.post(
        "/slack/interactions",
        data=f"payload={payload_str}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": old_timestamp,
            "X-Slack-Signature": signature,
        },
    )

    # Should reject old timestamps
    assert response.status_code == 401
    assert "X-Request-ID" in response.headers
