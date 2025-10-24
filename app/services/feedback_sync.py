"""Feedback synchronization service - polls Ashby API for feedback submissions."""

from __future__ import annotations

import json

from structlog import get_logger

from app.clients.ashby import fetch_application_feedback
from app.core.database import db

logger = get_logger()


async def sync_feedback_for_application(application_id: str) -> int:
    """
    Sync feedback submissions for a single application from Ashby API.

    Idempotent - uses ON CONFLICT DO NOTHING to prevent duplicates.

    Args:
        application_id: Ashby application UUID

    Returns:
        Count of new submissions inserted

    Raises:
        Exception: If API call fails
    """
    try:
        # Fetch all feedback from Ashby API
        submissions = await fetch_application_feedback(application_id)

        new_count = 0

        for submission in submissions:
            # Skip feedback without event_id (can't link it to a schedule)
            event_id = submission.get("interviewEventId")
            if not event_id:
                logger.debug(
                    "feedback_skipped_no_event_id",
                    feedback_id=submission["id"],
                )
                continue

            # Check if event exists in our database (might be from different schedule)
            event_exists = await db.fetchval(
                "SELECT 1 FROM interview_events WHERE event_id = $1",
                event_id,
            )

            if not event_exists:
                logger.debug(
                    "feedback_skipped_event_not_in_db",
                    feedback_id=submission["id"],
                    event_id=event_id,
                )
                continue

            # Extract and validate interviewer_id (required by schema)
            interviewer_id = (
                submission.get("submittedByUser", {}).get("id")
                if submission.get("submittedByUser")
                else None
            )

            if not interviewer_id:
                logger.debug(
                    "feedback_skipped_no_interviewer",
                    feedback_id=submission["id"],
                )
                continue

            # Insert with ON CONFLICT DO NOTHING for idempotency
            result = await db.execute(
                """
                INSERT INTO feedback_submissions
                (
                    feedback_id,
                    application_id,
                    event_id,
                    interviewer_id,
                    interview_id,
                    submitted_at,
                    submitted_values,
                    processed_for_advancement_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::text::timestamptz, $7, NULL)
                ON CONFLICT (feedback_id) DO NOTHING
            """,
                submission["id"],
                submission["applicationId"],
                event_id,
                interviewer_id,
                submission["interviewId"],
                submission["submittedAt"],
                json.dumps(submission["submittedValues"]),
            )

            # Check if row was inserted (result will be "INSERT 0 1" for new row)
            if "INSERT 0 1" in result:
                new_count += 1

        # Update schedule's updated_at to trigger re-evaluation
        if new_count > 0:
            await db.execute(
                """
                UPDATE interview_schedules s
                SET updated_at = NOW()
                WHERE s.application_id = $1
                """,
                application_id,
            )

        logger.info(
            "feedback_synced_for_application",
            application_id=application_id,
            total_submissions=len(submissions),
            new_submissions=new_count,
        )

        return new_count

    except Exception as e:
        logger.error(
            "feedback_sync_failed",
            application_id=application_id,
            error=str(e),
        )
        raise


async def sync_feedback_for_active_schedules() -> None:
    """
    Sync feedback for all active schedules.

    Queries schedules with status IN ('WaitingOnFeedback', 'Complete')
    and syncs feedback for each unique application_id.

    Handles errors gracefully - logs and continues with next application.
    """
    logger.info("feedback_sync_started")

    try:
        # Get distinct application_ids from active schedules
        rows = await db.fetch(
            """
            SELECT DISTINCT application_id
            FROM interview_schedules
            WHERE status IN ('WaitingOnFeedback', 'Complete')
              AND application_id IS NOT NULL
        """
        )

        application_ids = [str(row["application_id"]) for row in rows]

        logger.info(
            "feedback_sync_applications_found",
            count=len(application_ids),
        )

        total_new = 0
        success_count = 0
        error_count = 0

        # Sync each application (with error isolation)
        for application_id in application_ids:
            try:
                new_count = await sync_feedback_for_application(application_id)
                total_new += new_count
                success_count += 1
            except Exception as e:
                logger.error(
                    "feedback_sync_application_error",
                    application_id=application_id,
                    error=str(e),
                )
                error_count += 1
                # Continue with next application

        logger.info(
            "feedback_sync_completed",
            applications_processed=success_count,
            applications_failed=error_count,
            total_new_submissions=total_new,
        )

    except Exception as e:
        logger.error("feedback_sync_error", error=str(e))
        raise
