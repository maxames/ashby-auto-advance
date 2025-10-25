"""Interview schedule processing business logic."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from structlog import get_logger

from app.core.database import db
from app.core.errors import service_boundary
from app.services.sync import _upsert_interview

logger = get_logger()


@service_boundary
async def process_schedule_update(schedule: dict[str, Any]) -> None:
    """
    Process interview schedule update from webhook.

    Implements business rules and full-replace strategy for idempotency:
    - Validates schedule status
    - Handles cancellations (delete)
    - Handles Scheduled/Complete (upsert with full replace)

    Args:
        schedule: Interview schedule data from Ashby webhook

    Raises:
        RuntimeError: If database pool not initialized
    """
    schedule_id: str = schedule["id"]
    status: str = schedule["status"]

    logger.info("processing_schedule_update", schedule_id=schedule_id, status=status)

    # Business rule: Status validation
    if status not in ("Scheduled", "Complete", "Cancelled"):
        logger.info("schedule_status_ignored", status=status)
        return

    # Business rule: Cancellation handling
    if status == "Cancelled":
        await delete_schedule(schedule_id)
        return

    # Business rule: Full replace for Scheduled/Complete
    await upsert_schedule_with_events(schedule, schedule_id, status)


async def delete_schedule(schedule_id: str) -> None:
    """
    Delete schedule and cascading related records.

    Args:
        schedule_id: Schedule UUID
    """
    await db.execute(
        """
        DELETE FROM interview_schedules WHERE schedule_id = $1
    """,
        schedule_id,
    )
    logger.info("schedule_deleted", schedule_id=schedule_id)


async def upsert_schedule_with_events(
    schedule: dict[str, Any], schedule_id: str, status: str
) -> None:
    """
    Upsert schedule with full-replace strategy for events and assignments.

    Args:
        schedule: Schedule data from webhook
        schedule_id: Schedule UUID
        status: Schedule status

    Raises:
        RuntimeError: If database pool not initialized
    """
    if not db.pool:
        raise RuntimeError("Database pool not initialized")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Upsert schedule
            await conn.execute(
                """
                INSERT INTO interview_schedules
                (schedule_id, application_id, interview_stage_id, status, candidate_id, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (schedule_id) DO UPDATE SET
                    application_id = EXCLUDED.application_id,
                    interview_stage_id = EXCLUDED.interview_stage_id,
                    status = EXCLUDED.status,
                    candidate_id = EXCLUDED.candidate_id,
                    updated_at = NOW()
            """,
                schedule_id,
                schedule.get("applicationId"),
                schedule.get("interviewStageId"),
                status,
                schedule.get("candidateId"),
            )

            # Fetch interview_plan_id and job_id with retry
            interview_plan_id = None
            job_id = None
            stage_id = schedule.get("interviewStageId")

            if stage_id:
                for attempt in range(1, 4):  # 3 attempts
                    try:
                        from app.clients.ashby import fetch_interview_stage_info

                        stage_info = await fetch_interview_stage_info(stage_id)
                        interview_plan_id = stage_info.get("interviewPlanId")

                        # Fetch job_id from application API (webhook never includes it)
                        if schedule.get("applicationId"):
                            try:
                                from app.clients.ashby import ashby_client

                                app_response = await ashby_client.post(
                                    "application.info",
                                    {"applicationId": schedule["applicationId"]},
                                )

                                if app_response["success"] and app_response.get("results"):
                                    job_id = app_response["results"].get("job", {}).get("id")

                                    logger.info(
                                        "job_id_fetched_from_application",
                                        schedule_id=schedule_id,
                                        application_id=schedule["applicationId"],
                                        job_id=job_id,
                                    )
                            except Exception as e:
                                logger.warning(
                                    "job_id_fetch_failed",
                                    schedule_id=schedule_id,
                                    error=str(e),
                                )
                                # job_id remains None - will work for global rules

                        # Success - update schedule
                        await conn.execute(
                            """
                            UPDATE interview_schedules
                            SET interview_plan_id = $1, job_id = $2
                            WHERE schedule_id = $3
                        """,
                            interview_plan_id,
                            job_id,
                            schedule_id,
                        )

                        logger.info(
                            "advancement_fields_updated",
                            schedule_id=schedule_id,
                            interview_plan_id=interview_plan_id,
                            job_id=job_id,
                        )
                        break  # Success, exit retry loop

                    except Exception as e:
                        if attempt < 3:
                            logger.warning(
                                "advancement_fields_fetch_retry",
                                schedule_id=schedule_id,
                                attempt=attempt,
                                error=str(e),
                            )
                            await asyncio.sleep(0.5 * attempt)  # 0.5s, 1s delays
                        else:
                            logger.error(
                                "advancement_fields_fetch_failed_all_retries",
                                schedule_id=schedule_id,
                                error=str(e),
                            )
                            # Continue - schedule exists but interview_plan_id remains NULL

            # Delete existing events (full replace strategy)
            await conn.execute(
                """
                DELETE FROM interview_events WHERE schedule_id = $1
            """,
                schedule_id,
            )

            # Insert events and assignments
            for event in schedule.get("interviewEvents", []):
                await insert_event_with_assignments(conn, event, schedule_id)

    logger.info("schedule_updated", schedule_id=schedule_id, status=status)


async def insert_event_with_assignments(conn: Any, event: dict[str, Any], schedule_id: str) -> None:
    """
    Insert interview event and associated interviewer assignments.

    Args:
        conn: Database connection from transaction
        event: Event data from webhook
        schedule_id: Schedule UUID
    """
    event_id: str = event["id"]

    # Get interview_id (either from nested interview object or direct reference)
    interview_id = event.get("interviewId")
    if not interview_id and event.get("interview"):
        interview_id = event["interview"]["id"]

    if not interview_id:
        logger.warning("event_missing_interview_id", event_id=event_id)
        return

    # Fetch/update interview definition via API (ensures fresh data)
    # Import here to avoid circular dependency
    from app.clients.ashby import ashby_client

    try:
        response = await ashby_client.post("interview.info", {"id": interview_id})

        if response["success"]:
            await _upsert_interview(response["results"], conn=conn)
            logger.info("interview_fetched_and_updated", interview_id=interview_id)
        else:
            logger.warning(
                "interview_fetch_failed",
                interview_id=interview_id,
                error=response.get("error"),
            )
            # Continue processing - interview might already exist in DB

    except Exception:
        logger.exception("interview_fetch_error", interview_id=interview_id)
        # Continue processing - interview might already exist in DB
        # Only critical: schedule/event insertion failures will cause rollback

    # Insert event
    await conn.execute(
        """
        INSERT INTO interview_events
        (event_id, schedule_id, interview_id, created_at, updated_at,
         start_time, end_time, feedback_link, location, meeting_link,
         has_submitted_feedback, extra_data)
        VALUES (
            $1, $2, $3,
            $4::text::timestamptz,
            $5::text::timestamptz,
            $6::text::timestamptz,
            $7::text::timestamptz,
            $8, $9, $10, $11, $12
        )
    """,
        event_id,
        schedule_id,
        interview_id,
        event.get("createdAt"),
        event.get("updatedAt"),
        event.get("startTime"),
        event.get("endTime"),
        event.get("feedbackLink"),
        event.get("location"),
        event.get("meetingLink"),
        event.get("hasSubmittedFeedback", False),
        json.dumps(event.get("extraData", {})),
    )

    # Insert interviewer assignments
    for interviewer in event.get("interviewers", []):
        # Extract nested interviewer pool data
        interviewer_pool = interviewer.get("interviewerPool", {})

        await conn.execute(
            """
            INSERT INTO interview_assignments
            (event_id, interviewer_id, first_name, last_name, email,
             global_role, training_role, is_enabled, manager_id,
             interviewer_pool_id, interviewer_pool_title,
             interviewer_pool_is_archived, training_path, interviewer_updated_at)
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14::text::timestamptz
            )
        """,
            event_id,
            interviewer["id"],
            interviewer.get("firstName"),
            interviewer.get("lastName"),
            interviewer.get("email"),
            interviewer.get("globalRole"),
            interviewer.get("trainingRole"),
            interviewer.get("isEnabled", True),
            interviewer.get("managerId"),
            interviewer_pool.get("id"),
            interviewer_pool.get("title"),
            interviewer_pool.get("isArchived", False),
            json.dumps(interviewer_pool.get("trainingPath", {})),
            interviewer.get("updatedAt"),
        )


@service_boundary
async def refetch_missing_advancement_fields() -> None:
    """
    Background job to refetch interview_plan_id for schedules missing it.

    Runs every hour to fix schedules where webhook-time fetch failed.
    """
    logger.info("refetch_advancement_fields_started")

    try:
        schedules = await db.fetch(
            """
            SELECT schedule_id, interview_stage_id
            FROM interview_schedules
            WHERE interview_plan_id IS NULL
              AND interview_stage_id IS NOT NULL
              AND status IN ('Scheduled', 'WaitingOnFeedback', 'Complete')
              AND updated_at > NOW() - INTERVAL '7 days'
            LIMIT 50
        """
        )

        refetched = 0
        for schedule in schedules:
            schedule_id = str(schedule["schedule_id"])
            stage_id = str(schedule["interview_stage_id"])

            try:
                from app.clients.ashby import fetch_interview_stage_info

                stage_info = await fetch_interview_stage_info(stage_id)
                interview_plan_id = stage_info.get("interviewPlanId")

                await db.execute(
                    """
                    UPDATE interview_schedules
                    SET interview_plan_id = $1
                    WHERE schedule_id = $2
                """,
                    interview_plan_id,
                    schedule_id,
                )

                refetched += 1
                logger.info(
                    "advancement_fields_refetched",
                    schedule_id=schedule_id,
                    interview_plan_id=interview_plan_id,
                )

            except Exception as e:
                logger.error(
                    "refetch_failed",
                    schedule_id=schedule_id,
                    error=str(e),
                )

        logger.info("refetch_advancement_fields_completed", refetched=refetched)

    except Exception as e:
        logger.error("refetch_advancement_fields_error", error=str(e))
