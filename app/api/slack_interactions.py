"""Slack interactions API layer for handling button clicks."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.datastructures import UploadFile
from structlog import get_logger

from app.clients.slack import slack_client
from app.core.config import settings
from app.utils.security import verify_slack_signature

logger = get_logger()
router = APIRouter()


@router.post("/slack/interactions")
async def handle_slack_interactions(request: Request) -> Response:
    """
    Handle interactive component submissions from Slack.

    Simplified for advancement system - only handles rejection button clicks.

    Handles:
    - block_actions: Button clicks (send rejection)
    """
    # Get raw body for signature verification
    body = await request.body()
    body_str = body.decode("utf-8")

    # Extract signature headers
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        logger.warning("slack_request_missing_signature_headers")
        raise HTTPException(status_code=401, detail="Missing Slack signature headers")

    # Verify signature (security critical!)
    if not verify_slack_signature(settings.slack_signing_secret, body_str, timestamp, signature):
        logger.warning("slack_request_signature_verification_failed")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse payload after verification
    form_data = await request.form()
    payload_str = form_data.get("payload")
    if not payload_str or isinstance(payload_str, UploadFile):
        return Response(status_code=400)
    payload = json.loads(payload_str)

    # Handle button clicks
    if payload["type"] == "block_actions":
        action = payload["actions"][0]

        if action["action_id"] == "send_rejection":
            # Run async to avoid blocking Slack's 3-second timeout
            asyncio.create_task(handle_rejection_button(payload, action))

        return Response(status_code=200)

    return Response(status_code=200)


async def handle_rejection_button(payload: dict[str, Any], action: dict[str, Any]) -> None:
    """
    Handle rejection button click - archive candidate and send rejection email.

    Args:
        payload: Slack interaction payload
        action: Button action data
    """
    try:
        # Extract data from button value
        button_data = json.loads(action["value"])
        application_id = button_data["application_id"]

        # Execute rejection
        from app.services.advancement import execute_rejection

        result = await execute_rejection(application_id)

        # Update message to show result
        message_ts = payload["message"]["ts"]
        channel_id = payload["channel"]["id"]

        if result["success"]:
            # Update message with success
            await slack_client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="✅ Rejection sent successfully",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "✅ *Rejection Email Sent*\n\n"
                                "The candidate has been archived and "
                                "a rejection email was sent."
                            ),
                        },
                    }
                ],
            )

            logger.info(
                "rejection_sent_via_slack",
                application_id=application_id,
                user_id=payload["user"]["id"],
            )
        else:
            # Update message with error
            await slack_client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="❌ Failed to send rejection",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"❌ *Failed to Send Rejection*\n\n"
                                f"{result.get('error', 'Unknown error')}"
                            ),
                        },
                    }
                ],
            )

            logger.error(
                "rejection_failed_via_slack",
                application_id=application_id,
                error=result.get("error"),
            )

    except Exception as e:
        logger.exception("failed_to_handle_rejection_button", error=str(e))
