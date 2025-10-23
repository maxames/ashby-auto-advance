"""Admin endpoints for operational tasks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from structlog import get_logger

from app.core.database import db
from app.models.advancement import AdvancementRuleCreate
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
async def admin_stats() -> dict[str, int]:
    """
    Get application statistics.

    Returns:
        Dict with counts of reminders, pending feedback, drafts, forms, and users
    """
    stats = {}

    # Count reminders sent
    stats["reminders_sent"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM feedback_reminders_sent
    """
    )

    # Count pending feedback
    stats["pending_feedback"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM feedback_reminders_sent
        WHERE submitted_at IS NULL
    """
    )

    # Count active drafts
    stats["active_drafts"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM feedback_drafts
    """
    )

    # Count feedback forms
    stats["feedback_forms"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM feedback_form_definitions
        WHERE NOT is_archived
    """
    )

    # Count Slack users
    stats["slack_users"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM slack_users
        WHERE NOT deleted
    """
    )

    logger.info("admin_stats_retrieved", **stats)
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
        # Evaluate specific schedule
        result = await evaluate_schedule_for_advancement(schedule_id)
        return {"schedule_id": schedule_id, "evaluation": result}

    elif application_id:
        # Find schedules for application
        schedules = await db.fetch(
            """
            SELECT schedule_id
            FROM interview_schedules
            WHERE application_id = $1
            ORDER BY updated_at DESC
        """,
            application_id,
        )

        results = []
        for schedule in schedules:
            sid = str(schedule["schedule_id"])
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

    # Insert rule
    rule_id = await db.fetchval(
        """
        INSERT INTO advancement_rules
        (job_id, interview_plan_id, interview_stage_id, target_stage_id, is_active)
        VALUES ($1, $2, $3, $4, true)
        RETURNING rule_id
    """,
        rule.job_id,
        rule.interview_plan_id,
        rule.interview_stage_id,
        rule.target_stage_id,
    )

    # Insert requirements
    requirement_ids = []
    for req in rule.requirements:
        req_id = await db.fetchval(
            """
            INSERT INTO advancement_rule_requirements
            (rule_id, interview_id, score_field_path, operator, threshold_value, is_required)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING requirement_id
        """,
            rule_id,
            req.interview_id,
            req.score_field_path,
            req.operator,
            req.threshold_value,
            req.is_required,
        )
        requirement_ids.append(str(req_id))

    # Insert actions
    action_ids = []
    for action in rule.actions:
        action_id = await db.fetchval(
            """
            INSERT INTO advancement_rule_actions
            (rule_id, action_type, action_config, execution_order)
            VALUES ($1, $2, $3, $4)
            RETURNING action_id
        """,
            rule_id,
            action.action_type,
            action.action_config,
            action.execution_order,
        )
        action_ids.append(str(action_id))

    logger.info(
        "advancement_rule_created",
        rule_id=str(rule_id),
        requirements_count=len(requirement_ids),
        actions_count=len(action_ids),
    )

    return {
        "rule_id": str(rule_id),
        "requirement_ids": requirement_ids,
        "action_ids": action_ids,
        "status": "created",
    }


@router.get("/advancement-stats")
async def get_advancement_stats() -> dict[str, Any]:
    """
    Get advancement execution statistics.

    Returns:
        Stats on advancements, failures, pending evaluations
    """
    # Count by execution status
    status_counts = await db.fetch(
        """
        SELECT execution_status, COUNT(*) as count
        FROM advancement_executions
        WHERE executed_at > NOW() - INTERVAL '7 days'
        GROUP BY execution_status
    """
    )

    stats = {
        "last_7_days": {
            str(row["execution_status"]): row["count"] for row in status_counts
        }
    }

    # Count pending evaluations
    stats["pending_evaluations"] = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM interview_schedules
        WHERE status IN ('WaitingOnFeedback', 'Complete')
          AND (last_evaluated_for_advancement_at IS NULL
               OR updated_at > last_evaluated_for_advancement_at)
          AND interview_plan_id IS NOT NULL
    """
    )

    # Count active rules
    stats["active_rules"] = await db.fetchval(
        """
        SELECT COUNT(*) FROM advancement_rules WHERE is_active = true
    """
    )

    # Recent failures
    recent_failures = await db.fetch(
        """
        SELECT execution_id, schedule_id, application_id, failure_reason, executed_at
        FROM advancement_executions
        WHERE execution_status = 'failed'
          AND executed_at > NOW() - INTERVAL '24 hours'
        ORDER BY executed_at DESC
        LIMIT 10
    """
    )

    stats["recent_failures"] = [
        {
            "execution_id": str(f["execution_id"]),
            "schedule_id": str(f["schedule_id"]),
            "application_id": str(f["application_id"]),
            "failure_reason": f["failure_reason"],
            "executed_at": f["executed_at"].isoformat() if f["executed_at"] else None,
        }
        for f in recent_failures
    ]

    logger.info(
        "admin_advancement_stats_retrieved",
        **{k: v for k, v in stats.items() if k != "recent_failures"},
    )
    return stats
