"""Metadata synchronization for UI support data."""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from app.clients.ashby import ashby_client, list_interview_stages_for_plan
from app.core.database import db
from app.utils.time import parse_ashby_timestamp

logger = get_logger()


async def sync_jobs() -> None:
    """
    Sync all jobs from Ashby (open and closed).

    Runs on startup and every 6 hours via scheduler.
    Fetches jobs and their interview plan associations.
    """
    logger.info("sync_jobs_started")

    cursor = None
    jobs_synced = 0

    try:
        while True:
            response = await ashby_client.post(
                "job.list",
                {"status": ["Open", "Closed"], "cursor": cursor, "limit": 100},
            )

            if not response["success"]:
                logger.error("job_sync_failed", error=response.get("error"))
                break

            for job in response["results"]:
                job_dict: dict[str, Any] = job

                # Upsert job
                await db.execute(
                    """
                    INSERT INTO jobs
                    (job_id, title, status, department_id, default_interview_plan_id,
                     location_name, employment_type, created_at, updated_at, synced_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (job_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        status = EXCLUDED.status,
                        department_id = EXCLUDED.department_id,
                        default_interview_plan_id = EXCLUDED.default_interview_plan_id,
                        location_name = EXCLUDED.location_name,
                        employment_type = EXCLUDED.employment_type,
                        updated_at = EXCLUDED.updated_at,
                        synced_at = NOW()
                    """,
                    job_dict["id"],
                    job_dict.get("title"),
                    job_dict.get("status"),
                    job_dict.get("departmentId"),
                    job_dict.get("defaultInterviewPlanId"),
                    (
                        job_dict.get("location", {}).get("name")
                        if job_dict.get("location")
                        else None
                    ),
                    job_dict.get("employmentType"),
                    parse_ashby_timestamp(job_dict.get("createdAt")),
                    parse_ashby_timestamp(job_dict.get("updatedAt")),
                )

                # Sync interview plan associations
                plan_ids = job_dict.get("interviewPlanIds", [])
                default_plan_id = job_dict.get("defaultInterviewPlanId")

                # Delete old mappings for this job
                await db.execute(
                    "DELETE FROM job_interview_plans WHERE job_id = $1", job_dict["id"]
                )

                # Insert new mappings
                for plan_id in plan_ids:
                    # Ensure plan exists (create stub if needed)
                    await db.execute(
                        """
                        INSERT INTO interview_plans (interview_plan_id, title, synced_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (interview_plan_id) DO NOTHING
                        """,
                        plan_id,
                        f"Plan {plan_id[:8]}...",  # Placeholder
                    )

                    # Create mapping
                    await db.execute(
                        """
                        INSERT INTO job_interview_plans (job_id, interview_plan_id, is_default)
                        VALUES ($1, $2, $3)
                        """,
                        job_dict["id"],
                        plan_id,
                        plan_id == default_plan_id,
                    )

                jobs_synced += 1

            if not response.get("moreDataAvailable"):
                break

            cursor = response.get("nextCursor")

        logger.info("sync_jobs_completed", count=jobs_synced)

    except Exception:
        logger.exception("sync_jobs_error")


async def sync_interview_plans() -> None:
    """
    Sync all interview plans from Ashby.

    Runs on startup and every 6 hours via scheduler.
    """
    logger.info("sync_interview_plans_started")

    cursor = None
    plans_synced = 0

    try:
        while True:
            response = await ashby_client.post(
                "interviewPlan.list",
                {"includeArchived": False, "cursor": cursor, "limit": 100},
            )

            if not response["success"]:
                logger.error("interview_plan_sync_failed", error=response.get("error"))
                break

            for plan in response["results"]:
                plan_dict: dict[str, Any] = plan
                await db.execute(
                    """
                    INSERT INTO interview_plans
                    (interview_plan_id, title, is_archived, created_at, updated_at, synced_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT (interview_plan_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        is_archived = EXCLUDED.is_archived,
                        updated_at = EXCLUDED.updated_at,
                        synced_at = NOW()
                    """,
                    plan_dict["id"],
                    plan_dict.get("title"),
                    plan_dict.get("isArchived", False),
                    parse_ashby_timestamp(plan_dict.get("createdAt")),
                    parse_ashby_timestamp(plan_dict.get("updatedAt")),
                )
                plans_synced += 1

            if not response.get("moreDataAvailable"):
                break

            cursor = response.get("nextCursor")

        logger.info("sync_interview_plans_completed", count=plans_synced)

    except Exception:
        logger.exception("sync_interview_plans_error")


async def sync_interview_stages() -> None:
    """
    Sync all interview stages for all active interview plans.

    Runs on startup and every 6 hours via scheduler.
    """
    logger.info("sync_interview_stages_started")

    stages_synced = 0

    try:
        # Get all active interview plans
        plans = await db.fetch(
            "SELECT interview_plan_id FROM interview_plans WHERE NOT is_archived"
        )

        for plan in plans:
            plan_id = str(plan["interview_plan_id"])

            # Fetch stages for this plan using existing client function
            stages = await list_interview_stages_for_plan(plan_id)

            # Delete old stages for this plan
            await db.execute(
                "DELETE FROM interview_stages WHERE interview_plan_id = $1",
                plan["interview_plan_id"],
            )

            # Insert current stages
            for stage in stages:
                await db.execute(
                    """
                    INSERT INTO interview_stages
                    (interview_stage_id, interview_plan_id, title, type,
                     order_in_plan, interview_stage_group_id, synced_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    """,
                    stage["id"],
                    plan_id,
                    stage["title"],
                    stage.get("type"),
                    stage["orderInInterviewPlan"],
                    stage.get("interviewStageGroupId"),
                )
                stages_synced += 1

        logger.info("sync_interview_stages_completed", count=stages_synced)

    except Exception:
        logger.exception("sync_interview_stages_error")
