"""Admin endpoints for operational tasks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from structlog import get_logger

from app.models.advancement import AdvancementRuleCreate
from app.services import admin as admin_service
from app.services.sync import sync_feedback_forms, sync_slack_users

logger = get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sync-forms")
async def admin_sync_forms() -> dict[str, str]:
    """
    Manually trigger feedback form sync from Ashby.

    Useful for immediate refresh after form changes.
    """
    logger.info("admin_sync_forms_triggered")
    await sync_feedback_forms()
    return {"status": "completed", "message": "Feedback forms synced"}


@router.post("/sync-slack-users")
async def admin_sync_slack_users() -> dict[str, str]:
    """
    Manually trigger Slack user sync.

    Useful after new employees join or email changes.
    """
    logger.info("admin_sync_slack_users_triggered")
    await sync_slack_users()
    return {"status": "completed", "message": "Slack users synced"}


@router.get("/stats")
async def admin_stats() -> dict[str, Any]:
    """
    Get advancement system statistics.

    Returns:
        Dict with advancement execution counts, pending evaluations, and recent failures
    """
    stats = await admin_service.get_advancement_statistics()
    return stats


@router.post("/trigger-advancement-evaluation")
async def trigger_advancement_evaluation(
    schedule_id: str | None = None, application_id: str | None = None
) -> dict[str, Any]:
    """
    Manually trigger advancement evaluation for testing.

    Args:
        schedule_id: Specific schedule to evaluate (optional)
        application_id: Find schedules for this application (optional)

    Returns:
        Evaluation results
    """
    from app.services.advancement import evaluate_schedule_for_advancement

    logger.info(
        "admin_advancement_evaluation_triggered",
        schedule_id=schedule_id,
        application_id=application_id,
    )

    if schedule_id:
        result = await evaluate_schedule_for_advancement(schedule_id)
        return {"schedule_id": schedule_id, "evaluation": result}

    elif application_id:
        schedules = await admin_service.get_schedules_for_application(application_id)

        results = []
        for schedule in schedules:
            sid = schedule["schedule_id"]
            evaluation = await evaluate_schedule_for_advancement(sid)
            results.append({"schedule_id": sid, "evaluation": evaluation})

        return {
            "application_id": application_id,
            "schedules_evaluated": len(results),
            "results": results,
        }

    else:
        return {"error": "Must provide either schedule_id or application_id"}


@router.post("/create-advancement-rule")
async def create_advancement_rule(rule: AdvancementRuleCreate) -> dict[str, Any]:
    """
    Create new advancement rule with requirements and actions.

    Args:
        rule: Rule configuration

    Returns:
        Created rule with IDs
    """
    logger.info(
        "admin_creating_advancement_rule", interview_stage_id=rule.interview_stage_id
    )

    # Convert Pydantic models to dicts for service layer
    requirements = [req.model_dump() for req in rule.requirements]
    actions = [action.model_dump() for action in rule.actions]

    result = await admin_service.create_advancement_rule(
        job_id=rule.job_id,
        interview_plan_id=rule.interview_plan_id,
        interview_stage_id=rule.interview_stage_id,
        target_stage_id=rule.target_stage_id,
        requirements=requirements,
        actions=actions,
    )

    return {**result, "status": "created"}
