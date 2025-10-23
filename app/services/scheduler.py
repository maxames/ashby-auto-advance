"""Scheduler service for background jobs."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from structlog import get_logger

from app.services.advancement import process_advancement_evaluations
from app.services.feedback_sync import sync_feedback_for_active_schedules
from app.services.interviews import refetch_missing_advancement_fields
from app.services.sync import sync_feedback_forms, sync_interviews, sync_slack_users

logger = get_logger()

# Create scheduler instance
scheduler = AsyncIOScheduler()


def setup_scheduler() -> None:
    """
    Configure scheduler with all background jobs.

    Jobs:
    - sync_feedback_for_active_schedules: Every 30 minutes
    - process_advancement_evaluations: Every 30 minutes
    - refetch_missing_advancement_fields: Every hour
    - sync_feedback_forms: Every 6 hours
    - sync_interviews: Every 12 hours
    - sync_slack_users: Every 12 hours

    All jobs use coalesce=True and max_instances=1 to prevent overlaps.
    """
    # Sync feedback submissions from Ashby API every 30 minutes
    scheduler.add_job(
        sync_feedback_for_active_schedules,
        trigger="interval",
        minutes=30,
        id="sync_feedback",
        replace_existing=True,
        coalesce=True,  # Skip if previous run still executing
        max_instances=1,  # Only one instance at a time
    )

    # Process advancement evaluations every 30 minutes
    scheduler.add_job(
        process_advancement_evaluations,
        trigger="interval",
        minutes=30,
        id="advancement_evaluations",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Refetch missing advancement fields every hour
    scheduler.add_job(
        refetch_missing_advancement_fields,
        trigger="interval",
        hours=1,
        id="refetch_advancement_fields",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Sync feedback form definitions every 6 hours
    scheduler.add_job(
        sync_feedback_forms,
        trigger="interval",
        hours=6,
        id="sync_feedback_forms",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Sync interview definitions every 12 hours
    scheduler.add_job(
        sync_interviews,
        trigger="interval",
        hours=12,
        id="sync_interviews",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Sync Slack users every 12 hours
    scheduler.add_job(
        sync_slack_users,
        trigger="interval",
        hours=12,
        id="sync_slack_users",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    logger.info("scheduler_configured", jobs=6)


def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler.start()
    logger.info("scheduler_started")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    scheduler.shutdown(wait=True)
    logger.info("scheduler_shutdown")
