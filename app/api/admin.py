"""Admin endpoints for operational tasks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from structlog import get_logger

from app.models.advancement import (
    AdvancementRuleCreate,
    AdvancementRuleResponse,
    AdvancementStatsResponse,
    FeedbackFormFieldsResponse,
    InterviewsListResponse,
    JobsListResponse,
    PlansListResponse,
    RuleCreateResponse,
    RuleDeleteResponse,
    RulesListResponse,
    StagesListResponse,
)
from app.services import admin as admin_service
from app.services import metadata as metadata_service
from app.services.sync import sync_feedback_forms, sync_interviews, sync_slack_users

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


@router.post("/sync-interviews")
async def admin_sync_interviews() -> dict[str, str]:
    """
    Manually trigger interview definitions sync from Ashby.

    Useful for immediate refresh after interview changes.
    """
    logger.info("admin_sync_interviews_triggered")
    await sync_interviews()
    return {"status": "completed", "message": "Interviews synced"}


@router.post("/sync-metadata")
async def admin_sync_metadata() -> dict[str, str]:
    """
    Manually trigger metadata sync (jobs, plans, stages).

    Useful for immediate refresh during development.
    """
    from app.services.metadata_sync import (
        sync_interview_plans,
        sync_interview_stages,
        sync_jobs,
    )

    logger.info("admin_sync_metadata_triggered")
    await sync_jobs()
    await sync_interview_plans()
    await sync_interview_stages()
    return {"status": "completed", "message": "Metadata synced (jobs, plans, stages)"}


@router.get("/stats", response_model=AdvancementStatsResponse)
async def admin_stats() -> AdvancementStatsResponse:
    """
    Get advancement system statistics.

    Returns:
        Dict with advancement execution counts, pending evaluations, and recent failures
    """
    stats = await admin_service.get_advancement_statistics()
    return AdvancementStatsResponse(**stats)


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


@router.post("/create-advancement-rule", response_model=RuleCreateResponse)
async def create_advancement_rule(rule: AdvancementRuleCreate) -> RuleCreateResponse:
    """
    Create new advancement rule with requirements and actions.

    Args:
        rule: Rule configuration

    Returns:
        Created rule with IDs
    """
    logger.info("admin_creating_advancement_rule", interview_stage_id=rule.interview_stage_id)

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

    return RuleCreateResponse(**result, status="created")


@router.get("/rules", response_model=RulesListResponse)
async def list_advancement_rules(active_only: bool = True) -> RulesListResponse:
    """
    List all advancement rules with their requirements and actions.

    Args:
        active_only: If True, only return active rules (default: True)

    Returns:
        Dict with count and list of rules
    """
    logger.info("admin_list_advancement_rules_triggered", active_only=active_only)
    rules = await admin_service.get_all_advancement_rules(active_only=active_only)
    return RulesListResponse(count=len(rules), rules=rules)


@router.get("/rules/{rule_id}", response_model=AdvancementRuleResponse)
async def get_advancement_rule(rule_id: str) -> AdvancementRuleResponse:
    """
    Get detailed information about a specific advancement rule.

    Args:
        rule_id: Rule UUID

    Returns:
        Rule details with requirements and actions

    Raises:
        HTTPException: 404 if rule not found
    """
    logger.info("admin_get_advancement_rule_triggered", rule_id=rule_id)
    rule = await admin_service.get_advancement_rule_by_id(rule_id)

    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    return AdvancementRuleResponse(**rule)


@router.delete("/rules/{rule_id}", response_model=RuleDeleteResponse)
async def delete_advancement_rule(rule_id: str) -> RuleDeleteResponse:
    """
    Soft-delete an advancement rule by setting is_active=false.

    Args:
        rule_id: Rule UUID to delete

    Returns:
        Status message

    Raises:
        HTTPException: 404 if rule not found or already deleted
    """
    logger.info("admin_delete_advancement_rule_triggered", rule_id=rule_id)
    success = await admin_service.delete_advancement_rule(rule_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found or already deleted")

    return RuleDeleteResponse(status="deleted", rule_id=rule_id)


# ============================================
# Metadata Endpoints (for UI dropdowns)
# ============================================


@router.get("/metadata/jobs", response_model=JobsListResponse)
async def list_jobs(active_only: bool = True) -> JobsListResponse:
    """
    Get list of jobs for UI dropdowns.

    Args:
        active_only: If True, only return open jobs (default: True)

    Returns:
        List of jobs with id, title, status, etc.
    """
    jobs = await metadata_service.get_jobs(active_only=active_only)
    return JobsListResponse(jobs=jobs)


@router.get("/metadata/jobs/{job_id}/plans", response_model=PlansListResponse)
async def get_job_plans(job_id: str) -> PlansListResponse:
    """
    Get interview plans for a specific job.

    Args:
        job_id: Job UUID

    Returns:
        List of plans with id, title, is_default flag
    """
    plans = await metadata_service.get_plans_for_job(job_id)
    return PlansListResponse(plans=plans)


@router.get("/metadata/plans/{plan_id}/stages", response_model=StagesListResponse)
async def get_plan_stages(plan_id: str) -> StagesListResponse:
    """
    Get stages for an interview plan.

    Args:
        plan_id: Interview plan UUID

    Returns:
        List of stages with id, title, type, order
    """
    stages = await metadata_service.get_stages_for_plan(plan_id)
    return StagesListResponse(stages=stages)


@router.get("/metadata/interviews", response_model=InterviewsListResponse)
async def list_interviews(job_id: str | None = None) -> InterviewsListResponse:
    """
    Get list of interviews, optionally filtered by job.

    Args:
        job_id: Optional job UUID to filter by

    Returns:
        List of interviews with id, title, job_id, feedback_form_id
    """
    interviews = await metadata_service.get_interviews(job_id=job_id)
    return InterviewsListResponse(interviews=interviews)


@router.get(
    "/metadata/feedback-forms/{form_id}/fields",
    response_model=FeedbackFormFieldsResponse,
)
async def get_feedback_form_fields(form_id: str) -> FeedbackFormFieldsResponse:
    """
    Get scoreable fields from a feedback form.

    Returns only field types that can be used in advancement rules
    (Score, ValueSelect, Rating). Excludes RichText and other non-scoreable types.

    Args:
        form_id: Feedback form definition UUID

    Returns:
        List of scoreable fields with paths, labels, types, and options
    """
    fields = await metadata_service.get_feedback_form_fields(form_id)
    return FeedbackFormFieldsResponse(fields=fields)
