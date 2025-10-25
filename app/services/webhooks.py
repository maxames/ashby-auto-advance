"""Webhook service layer for audit logging."""

from __future__ import annotations

import json
from typing import Any

from structlog import get_logger

from app.core.database import db

logger = get_logger()


async def log_webhook_to_audit(schedule_id: str, action: str, payload: dict[str, Any]) -> None:
    """
    Log webhook event to audit table.

    Records webhook payload in ashby_webhook_payloads table for debugging
    and compliance purposes.

    Args:
        schedule_id: Interview schedule UUID from webhook
        action: Webhook action type (e.g., "interviewScheduleUpdate")
        payload: Complete webhook payload dict
    """
    await db.execute(
        """
        INSERT INTO ashby_webhook_payloads (schedule_id, received_at, action, payload)
        VALUES ($1, NOW(), $2, $3)
        """,
        schedule_id,
        action,
        json.dumps(payload),
    )

    logger.debug(
        "webhook_logged_to_audit",
        schedule_id=schedule_id,
        action=action,
    )
