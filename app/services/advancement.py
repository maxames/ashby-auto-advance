"""Advancement evaluation and execution service."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from structlog import get_logger

from app.clients.ashby import (
    advance_candidate_stage,
    archive_candidate,
    fetch_candidate_info,
)
from app.clients.slack import slack_client
from app.core.config import settings
from app.core.database import db
from app.core.errors import ConfigurationError, service_boundary
from app.services.rules import (
    evaluate_rule_requirements,
    find_matching_rule,
    get_target_stage_for_rule,
)
from app.types.database import FeedbackSubmissionRecordTD, InterviewScheduleRecordTD

logger = get_logger()


async def get_schedules_ready_for_evaluation() -> list[InterviewScheduleRecordTD]:
    """
    Get schedules that are ready for advancement evaluation.

    Filters:
    - status IN ('WaitingOnFeedback', 'Complete')
    - last_evaluated_at IS NULL OR updated_at > last_evaluated_at
    - created_at within timeout window (not too old)

    Returns:
        List of schedule records with context
    """
    timeout_days = settings.advancement_feedback_timeout_days

    rows = await db.fetch(
        """
        SELECT
            s.schedule_id,
            s.application_id,
            s.interview_stage_id,
            s.interview_plan_id,
            s.job_id,
            s.candidate_id,
            s.status,
            s.updated_at,
            s.last_evaluated_for_advancement_at
        FROM interview_schedules s
        WHERE s.status IN ('WaitingOnFeedback', 'Complete')
          AND (
              s.last_evaluated_for_advancement_at IS NULL
              OR s.updated_at > s.last_evaluated_for_advancement_at
          )
          AND s.updated_at > NOW() - INTERVAL '1 day' * $1
          AND s.interview_plan_id IS NOT NULL
        ORDER BY s.updated_at ASC
    """,
        timeout_days,
    )

    logger.info("schedules_ready_for_evaluation", count=len(rows))

    # Convert asyncpg.Record to dict (TypedDict compatible)
    return [{k: v for k, v in row.items()} for row in rows]  # type: ignore[return-value]


async def evaluate_schedule_for_advancement(schedule_id: str) -> dict[str, Any]:
    """
    Evaluate a single schedule for advancement.

    Checks:
    1. Find matching rule
    2. Get feedback submissions
    3. Verify 30-minute wait period
    4. Evaluate rule requirements

    Returns:
        {
            "ready": bool,
            "blocking_reason": str | None,
            "rule_id": str | None,
            "target_stage_id": str | None,
            "evaluation_results": dict | None
        }
    """
    # Get schedule details
    schedule = await db.fetchrow(
        """
        SELECT
            schedule_id,
            application_id,
            interview_stage_id,
            interview_plan_id,
            job_id,
            candidate_id,
            status
        FROM interview_schedules
        WHERE schedule_id = $1
    """,
        schedule_id,
    )

    if not schedule:
        return {"ready": False, "blocking_reason": "schedule_not_found"}

    job_id = str(schedule["job_id"]) if schedule["job_id"] else None
    interview_plan_id = str(schedule["interview_plan_id"])
    interview_stage_id = str(schedule["interview_stage_id"])
    application_id = str(schedule["application_id"])

    # Find matching rule
    rule = await find_matching_rule(job_id, interview_plan_id, interview_stage_id)

    if not rule:
        return {"ready": False, "blocking_reason": "no_rule"}

    rule_id = rule["rule_id"]

    # Get feedback submissions for this schedule
    feedback_submissions = await db.fetch(
        """
        SELECT
            f.feedback_id,
            f.application_id,
            f.event_id,
            f.interviewer_id,
            f.interview_id,
            f.submitted_at,
            f.submitted_values,
            f.processed_for_advancement_at
        FROM feedback_submissions f
        INNER JOIN interview_events e ON e.event_id = f.event_id
        WHERE e.schedule_id = $1
        ORDER BY f.submitted_at
    """,
        schedule_id,
    )

    feedback_list: list[FeedbackSubmissionRecordTD] = [
        {k: v for k, v in f.items()}
        for f in feedback_submissions  # type: ignore[misc]
    ]

    # Check if any feedback exists
    if not feedback_list:
        return {"ready": False, "blocking_reason": "no_feedback_submitted"}

    # Check 30-minute wait period
    min_wait_minutes = settings.advancement_feedback_min_wait_minutes

    recent_feedback = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM feedback_submissions f
        INNER JOIN interview_events e ON e.event_id = f.event_id
        WHERE e.schedule_id = $1
          AND f.submitted_at > NOW() - INTERVAL '1 minute' * $2
    """,
        schedule_id,
        min_wait_minutes,
    )

    if recent_feedback > 0:
        return {
            "ready": False,
            "blocking_reason": "too_recent",
        }

    # Evaluate rule requirements
    evaluation_results = await evaluate_rule_requirements(rule_id, schedule_id, feedback_list)

    if not evaluation_results["all_passed"]:
        return {
            "ready": False,
            "blocking_reason": "requirements_not_met",
            "rule_id": rule_id,
            "evaluation_results": evaluation_results,
        }

    # Get target stage
    try:
        target_stage_id = await get_target_stage_for_rule(
            rule_id, interview_stage_id, interview_plan_id
        )
    except ValueError as e:
        logger.error(
            "target_stage_error",
            schedule_id=schedule_id,
            rule_id=rule_id,
            error=str(e),
        )
        return {"ready": False, "blocking_reason": f"target_stage_error: {str(e)}"}

    logger.info(
        "schedule_ready_for_advancement",
        schedule_id=schedule_id,
        rule_id=rule_id,
        target_stage_id=target_stage_id,
    )

    return {
        "ready": True,
        "rule_id": rule_id,
        "target_stage_id": target_stage_id,
        "evaluation_results": evaluation_results,
        "application_id": application_id,
    }


async def execute_advancement(
    schedule_id: str,
    application_id: str,
    rule_id: str,
    target_stage_id: str,
    from_stage_id: str,
    evaluation_results: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute advancement with retry logic.

    Args:
        schedule_id: Schedule UUID
        application_id: Application UUID
        rule_id: Rule UUID
        target_stage_id: Target stage UUID
        from_stage_id: Current stage UUID
        evaluation_results: Evaluation results for audit
        dry_run: If True, log only (don't call API)

    Returns:
        {
            "success": bool,
            "execution_id": str,
            "status": str
        }
    """
    if dry_run:
        # Dry-run mode: log and insert audit record
        logger.info(
            "DRY_RUN_would_advance_candidate",
            schedule_id=schedule_id,
            application_id=application_id,
            rule_id=rule_id,
            from_stage_id=from_stage_id,
            target_stage_id=target_stage_id,
        )

        execution_id = await db.fetchval(
            """
            INSERT INTO advancement_executions
            (schedule_id, application_id, rule_id, from_stage_id, to_stage_id,
             execution_status, evaluation_results, executed_by)
            VALUES ($1, $2, $3, $4, $5, 'dry_run', $6, 'system')
            RETURNING execution_id
        """,
            schedule_id,
            application_id,
            rule_id,
            from_stage_id,
            target_stage_id,
            json.dumps(evaluation_results) if evaluation_results else None,
        )

        # Mark as evaluated
        await db.execute(
            """
            UPDATE interview_schedules
            SET last_evaluated_for_advancement_at = NOW()
            WHERE schedule_id = $1
        """,
            schedule_id,
        )

        return {"success": True, "execution_id": str(execution_id), "status": "dry_run"}

    # Real execution with retry logic
    max_attempts = 3
    delays = [2, 4, 8]  # Exponential backoff in seconds

    for attempt in range(max_attempts):
        try:
            # Call Ashby API to advance candidate
            await advance_candidate_stage(application_id, target_stage_id)

            # Success - insert audit record
            execution_id = await db.fetchval(
                """
                INSERT INTO advancement_executions
                (schedule_id, application_id, rule_id, from_stage_id, to_stage_id,
                 execution_status, evaluation_results, executed_by)
                VALUES ($1, $2, $3, $4, $5, 'success', $6, 'system')
                RETURNING execution_id
            """,
                schedule_id,
                application_id,
                rule_id,
                from_stage_id,
                target_stage_id,
                json.dumps(evaluation_results) if evaluation_results else None,
            )

            # Mark feedback as processed
            await db.execute(
                """
                UPDATE feedback_submissions
                SET processed_for_advancement_at = NOW()
                WHERE application_id = $1
                  AND processed_for_advancement_at IS NULL
            """,
                application_id,
            )

            # Mark schedule as evaluated
            await db.execute(
                """
                UPDATE interview_schedules
                SET last_evaluated_for_advancement_at = NOW()
                WHERE schedule_id = $1
            """,
                schedule_id,
            )

            logger.info(
                "candidate_advanced_successfully",
                schedule_id=schedule_id,
                application_id=application_id,
                execution_id=str(execution_id),
                attempt=attempt + 1,
            )

            return {
                "success": True,
                "execution_id": str(execution_id),
                "status": "success",
            }

        except Exception as e:
            logger.warning(
                "advancement_attempt_failed",
                schedule_id=schedule_id,
                application_id=application_id,
                attempt=attempt + 1,
                max_attempts=max_attempts,
                error=str(e),
            )

            # If not last attempt, wait and retry
            if attempt < max_attempts - 1:
                await asyncio.sleep(delays[attempt])
            else:
                # Last attempt failed - insert failure audit record
                failure_reason = str(e)

                execution_id = await db.fetchval(
                    """
                    INSERT INTO advancement_executions
                    (schedule_id, application_id, rule_id, from_stage_id, to_stage_id,
                     execution_status, failure_reason, evaluation_results, executed_by)
                    VALUES ($1, $2, $3, $4, $5, 'failed', $6, $7, 'system')
                    RETURNING execution_id
                """,
                    schedule_id,
                    application_id,
                    rule_id,
                    from_stage_id,
                    target_stage_id,
                    failure_reason,
                    json.dumps(evaluation_results) if evaluation_results else None,
                )

                # Mark schedule as evaluated (prevents retry loop)
                await db.execute(
                    """
                    UPDATE interview_schedules
                    SET last_evaluated_for_advancement_at = NOW()
                    WHERE schedule_id = $1
                """,
                    schedule_id,
                )

                # Send error notification
                await handle_advancement_error(schedule_id, application_id, e)

                return {
                    "success": False,
                    "execution_id": str(execution_id),
                    "status": "failed",
                    "error": failure_reason,
                }

    # Should never reach here
    return {"success": False, "status": "unknown_error"}


@service_boundary
async def process_advancement_evaluations() -> None:
    """
    Main function called by scheduler to process advancement evaluations.

    For each ready schedule:
    - Evaluate for advancement
    - If ready: execute advancement
    - If not ready but requirements failed: send rejection notification (Decision B)
    """
    logger.info("advancement_evaluations_started")

    dry_run = settings.advancement_dry_run_mode

    try:
        schedules = await get_schedules_ready_for_evaluation()

        advanced_count = 0
        rejected_count = 0
        blocked_count = 0
        error_count = 0

        for schedule in schedules:
            schedule_id = str(schedule["schedule_id"])
            application_id = str(schedule["application_id"])

            try:
                # Evaluate schedule
                evaluation = await evaluate_schedule_for_advancement(schedule_id)

                if evaluation["ready"]:
                    # Execute advancement
                    result = await execute_advancement(
                        schedule_id=schedule_id,
                        application_id=application_id,
                        rule_id=evaluation["rule_id"],
                        target_stage_id=evaluation["target_stage_id"],
                        from_stage_id=str(schedule["interview_stage_id"]),
                        evaluation_results=evaluation["evaluation_results"],
                        dry_run=dry_run,
                    )

                    if result["success"]:
                        advanced_count += 1

                elif evaluation.get("blocking_reason") == "requirements_not_met":
                    # Requirements failed - send rejection notification (Decision B)
                    logger.info(
                        "sending_rejection_notification",
                        schedule_id=schedule_id,
                        application_id=application_id,
                    )

                    # Get feedback data
                    feedback_submissions = await db.fetch(
                        """
                        SELECT
                            f.feedback_id,
                            f.interviewer_id,
                            f.interview_id,
                            f.submitted_at,
                            f.submitted_values,
                            i.title as interview_title
                        FROM feedback_submissions f
                        INNER JOIN interview_events e ON e.event_id = f.event_id
                        INNER JOIN interviews i ON i.interview_id = f.interview_id
                        WHERE e.schedule_id = $1
                        ORDER BY f.submitted_at
                    """,
                        schedule_id,
                    )

                    await send_rejection_notification(
                        application_id=application_id,
                        schedule_id=schedule_id,
                        feedback_data=[{k: v for k, v in f.items()} for f in feedback_submissions],
                    )

                    rejected_count += 1

                    # Mark as evaluated to prevent re-notification
                    await db.execute(
                        """
                        UPDATE interview_schedules
                        SET last_evaluated_for_advancement_at = NOW()
                        WHERE schedule_id = $1
                    """,
                        schedule_id,
                    )

                else:
                    # Blocked for other reason (no rule, too recent, etc.)
                    blocked_count += 1

                    # Mark as evaluated
                    await db.execute(
                        """
                        UPDATE interview_schedules
                        SET last_evaluated_for_advancement_at = NOW()
                        WHERE schedule_id = $1
                    """,
                        schedule_id,
                    )

            except Exception as e:
                logger.error(
                    "schedule_evaluation_error",
                    schedule_id=schedule_id,
                    error=str(e),
                )
                error_count += 1
                # Continue with next schedule

        logger.info(
            "advancement_evaluations_completed",
            total_schedules=len(schedules),
            advanced=advanced_count,
            rejected=rejected_count,
            blocked=blocked_count,
            errors=error_count,
            dry_run=dry_run,
        )

    except Exception as e:
        logger.error("advancement_evaluations_error", error=str(e))
        raise


async def send_rejection_notification(
    application_id: str, schedule_id: str, feedback_data: list[dict[str, Any]]
) -> None:
    """
    Send rejection notification to recruiter via Slack.

    Uses candidate info and feedback summary to build message.

    Args:
        application_id: Application UUID
        schedule_id: Schedule UUID
        feedback_data: List of feedback submissions
    """
    try:
        # Get candidate info
        schedule = await db.fetchrow(
            """
            SELECT candidate_id, job_id
            FROM interview_schedules
            WHERE schedule_id = $1
        """,
            schedule_id,
        )

        if not schedule or not schedule["candidate_id"]:
            logger.warning("no_candidate_id_for_rejection", schedule_id=schedule_id)
            return

        candidate_id = str(schedule["candidate_id"])
        candidate = await fetch_candidate_info(candidate_id)

        # Build Ashby profile URL
        ashby_profile_url = (
            f"https://app.ashbyhq.com/candidate-searches/new/right-side/candidates/{candidate_id}"
        )

        # Get job title from Ashby
        job_title = "Position"  # Default fallback
        if schedule["job_id"]:
            try:
                from app.clients.ashby import fetch_job_info

                job_info = await fetch_job_info(str(schedule["job_id"]))
                job_title = job_info["title"]
            except Exception as e:
                logger.warning(
                    "failed_to_fetch_job_title",
                    job_id=schedule["job_id"],
                    error=str(e),
                )
                # Keep default "Position"

        # Build feedback summary
        feedback_summaries = []
        for fb in feedback_data:
            feedback_summaries.append(
                {
                    "interview_title": fb.get("interview_title", "Interview"),
                    "submitted_at": fb["submitted_at"],
                    "scores": fb["submitted_values"],
                }
            )

        # Import here to avoid circular dependency
        from app.clients.slack_views import build_rejection_notification

        blocks = build_rejection_notification(
            candidate_data=candidate,
            feedback_summaries=feedback_summaries,
            application_id=application_id,
            job_title=job_title,
            ashby_profile_url=ashby_profile_url,
        )

        # Find recruiter - TODO: Get from job's hiring team
        # For now, send to admin channel if configured
        if settings.admin_slack_channel_id:
            await slack_client.chat_postMessage(
                channel=settings.admin_slack_channel_id,
                blocks=blocks,
                text=f"Candidate {candidate['name']} did not meet advancement criteria",
            )

            logger.info(
                "rejection_notification_sent",
                application_id=application_id,
                candidate_id=candidate_id,
                channel=settings.admin_slack_channel_id,
            )
        else:
            logger.warning("admin_slack_channel_not_configured")

    except Exception as e:
        logger.error(
            "rejection_notification_error",
            application_id=application_id,
            schedule_id=schedule_id,
            error=str(e),
        )
        # Don't raise - notification failure shouldn't block evaluation


async def handle_advancement_error(schedule_id: str, application_id: str, error: Exception) -> None:
    """
    Handle advancement execution errors.

    Sends Slack alert to admin channel with error details.

    Args:
        schedule_id: Schedule UUID
        application_id: Application UUID
        error: The exception that occurred
    """
    try:
        # Get candidate info for better error message
        schedule = await db.fetchrow(
            """
            SELECT candidate_id
            FROM interview_schedules
            WHERE schedule_id = $1
        """,
            schedule_id,
        )

        candidate_id = str(schedule["candidate_id"]) if schedule else "unknown"
        candidate_name = "Unknown"

        if schedule and schedule["candidate_id"]:
            try:
                candidate = await fetch_candidate_info(str(schedule["candidate_id"]))
                candidate_name = candidate["name"]
            except Exception:
                pass

        # Build error message
        error_message = f"""
❌ *Auto-Advancement Failed*

*Schedule:* `{schedule_id}`
*Application:* `{application_id}`
*Candidate:* {candidate_name}
*Error:* {str(error)}

*Profile:* https://app.ashbyhq.com/candidate-searches/new/right-side/candidates/{candidate_id}
"""

        # Send to admin channel if configured
        if settings.admin_slack_channel_id:
            await slack_client.chat_postMessage(
                channel=settings.admin_slack_channel_id,
                text=error_message,
            )

            logger.info(
                "advancement_error_alert_sent",
                schedule_id=schedule_id,
                application_id=application_id,
            )
        else:
            logger.warning("admin_slack_channel_not_configured_for_errors")

    except Exception as e:
        logger.error(
            "error_notification_failed",
            schedule_id=schedule_id,
            application_id=application_id,
            error=str(e),
        )
        # Don't raise - error notification failure shouldn't cause more issues


@service_boundary
async def execute_rejection(application_id: str) -> dict[str, Any]:
    """
    Execute rejection (archive candidate) via Ashby API.

    Called from Slack interaction when recruiter clicks rejection button.

    Args:
        application_id: Application UUID

    Returns:
        {"success": bool, "error": str | None}
    """
    try:
        # Use archive_reason_id from config (Decision A)
        archive_reason_id = settings.default_archive_reason_id

        if not archive_reason_id:
            raise ConfigurationError(
                "DEFAULT_ARCHIVE_REASON_ID must be configured to execute rejections",
                context={"required_env_var": "DEFAULT_ARCHIVE_REASON_ID"},
            )

        await archive_candidate(
            application_id=application_id,
            archive_reason_id=archive_reason_id,
            communication_template_id=None,  # Optional for MVP
        )

        # Record in audit trail
        await db.execute(
            """
            INSERT INTO advancement_executions
            (schedule_id, application_id, rule_id, execution_status, executed_by)
            SELECT s.schedule_id, $1, NULL, 'rejected', 'recruiter_manual'
            FROM interview_schedules s
            WHERE s.application_id = $1
            LIMIT 1
        """,
            application_id,
        )

        logger.info(
            "candidate_rejected_manually",
            application_id=application_id,
        )

        return {"success": True, "error": None}

    except Exception as e:
        logger.error(
            "rejection_execution_error",
            application_id=application_id,
            error=str(e),
        )
        return {"success": False, "error": str(e)}
