"""Metadata query service for UI dropdown support."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from structlog import get_logger

from app.core.database import db

logger = get_logger()


async def get_jobs(active_only: bool = True) -> list[dict[str, Any]]:
    """
    Get list of jobs for UI dropdowns.

    Args:
        active_only: If True, only return open jobs

    Returns:
        List of job dicts with id, title, status, etc.
    """
    where_clause = "WHERE status = 'Open'" if active_only else ""

    jobs = await db.fetch(
        f"""
        SELECT job_id, title, status, department_id, location_name, employment_type
        FROM jobs
        {where_clause}
        ORDER BY title
        """
    )

    return [
        {
            "id": str(job["job_id"]),
            "title": job["title"],
            "status": job["status"],
            "department_id": (
                str(job["department_id"]) if job["department_id"] else None
            ),
            "location": job["location_name"],
            "employment_type": job["employment_type"],
        }
        for job in jobs
    ]


async def get_plans_for_job(job_id: str) -> list[dict[str, Any]]:
    """
    Get interview plans for a specific job.

    Args:
        job_id: Job UUID

    Returns:
        List of plan dicts with id, title, is_default
    """
    plans = await db.fetch(
        """
        SELECT
            ip.interview_plan_id,
            ip.title,
            jip.is_default
        FROM job_interview_plans jip
        JOIN interview_plans ip ON ip.interview_plan_id = jip.interview_plan_id
        WHERE jip.job_id = $1
        ORDER BY jip.is_default DESC, ip.title
        """,
        UUID(job_id),
    )

    return [
        {
            "id": str(plan["interview_plan_id"]),
            "title": plan["title"],
            "is_default": plan["is_default"],
        }
        for plan in plans
    ]


async def get_stages_for_plan(plan_id: str) -> list[dict[str, Any]]:
    """
    Get stages for an interview plan.

    Args:
        plan_id: Interview plan UUID

    Returns:
        List of stage dicts with id, title, type, order
    """
    stages = await db.fetch(
        """
        SELECT interview_stage_id, title, type, order_in_plan
        FROM interview_stages
        WHERE interview_plan_id = $1
        ORDER BY order_in_plan
        """,
        UUID(plan_id),
    )

    return [
        {
            "id": str(stage["interview_stage_id"]),
            "title": stage["title"],
            "type": stage["type"],
            "order": stage["order_in_plan"],
        }
        for stage in stages
    ]


async def get_interviews(job_id: str | None = None) -> list[dict[str, Any]]:
    """
    Get list of interviews, optionally filtered by job.

    Args:
        job_id: Optional job UUID to filter by

    Returns:
        List of interview dicts with id, title, job_id, feedback_form_id
    """
    if job_id:
        interviews = await db.fetch(
            """
            SELECT interview_id, title, external_title, job_id, feedback_form_definition_id
            FROM interviews
            WHERE job_id = $1 AND is_archived = false
            ORDER BY title
            """,
            UUID(job_id),
        )
    else:
        interviews = await db.fetch(
            """
            SELECT interview_id, title, external_title, job_id, feedback_form_definition_id
            FROM interviews
            WHERE is_archived = false
            ORDER BY title
            """
        )

    return [
        {
            "id": str(interview["interview_id"]),
            "title": interview["title"] or interview["external_title"],
            "job_id": str(interview["job_id"]) if interview.get("job_id") else None,
            "feedback_form_id": (
                str(interview["feedback_form_definition_id"])
                if interview["feedback_form_definition_id"]
                else None
            ),
        }
        for interview in interviews
    ]
