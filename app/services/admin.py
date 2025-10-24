"""Admin service layer for administrative operations."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from structlog import get_logger

from app.core.database import db

logger = get_logger()


async def create_advancement_rule(
    job_id: str | None,
    interview_plan_id: str,
    interview_stage_id: str,
    target_stage_id: str | None,
    requirements: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Create advancement rule with requirements and actions.

    Args:
        job_id: Optional job UUID (NULL = applies to all jobs)
        interview_plan_id: Interview plan UUID
        interview_stage_id: Interview stage UUID
        target_stage_id: Optional target stage UUID (NULL = next sequential)
        requirements: List of requirement dicts with interview_id, score_field_path, etc.
        actions: List of action dicts with action_type, action_config, etc.

    Returns:
        Complete rule object with generated IDs

    Raises:
        Exception: If database operation fails
    """
    # Insert rule
    rule_id = await db.fetchval(
        """
        INSERT INTO advancement_rules
        (job_id, interview_plan_id, interview_stage_id, target_stage_id, is_active)
        VALUES ($1, $2, $3, $4, true)
        RETURNING rule_id
    """,
        job_id,
        interview_plan_id,
        interview_stage_id,
        target_stage_id,
    )

    # Insert requirements
    requirement_ids = []
    for req in requirements:
        req_id = await db.fetchval(
            """
            INSERT INTO advancement_rule_requirements
            (rule_id, interview_id, score_field_path, operator, threshold_value, is_required)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING requirement_id
        """,
            rule_id,
            req["interview_id"],
            req["score_field_path"],
            req["operator"],
            req["threshold_value"],
            req.get("is_required", True),
        )
        requirement_ids.append(str(req_id))

    # Insert actions
    action_ids = []
    for action in actions:
        action_id = await db.fetchval(
            """
            INSERT INTO advancement_rule_actions
            (rule_id, action_type, action_config, execution_order)
            VALUES ($1, $2, $3, $4)
            RETURNING action_id
        """,
            rule_id,
            action["action_type"],
            (
                json.dumps(action.get("action_config"))
                if action.get("action_config")
                else None
            ),
            action.get("execution_order", 1),
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
        "job_id": job_id,
        "interview_plan_id": interview_plan_id,
        "interview_stage_id": interview_stage_id,
        "target_stage_id": target_stage_id,
        "requirement_ids": requirement_ids,
        "action_ids": action_ids,
    }


async def get_advancement_statistics() -> dict[str, Any]:
    """
    Get advancement system statistics.

    Returns:
        Dict with active_rules, execution counts by status, pending evaluations,
        and recent failures
    """
    # Count by execution status
    status_counts_rows = await db.fetch(
        """
        SELECT execution_status, COUNT(*) as count
        FROM advancement_executions
        WHERE executed_at > NOW() - INTERVAL '30 days'
        GROUP BY execution_status
    """
    )

    status_counts = {
        row["execution_status"]: row["count"] for row in status_counts_rows
    }

    # Count pending evaluations
    pending_evaluations = await db.fetchval(
        """
        SELECT COUNT(*)
        FROM interview_schedules
        WHERE status IN ('WaitingOnFeedback', 'Complete')
          AND (last_evaluated_for_advancement_at IS NULL
               OR updated_at > last_evaluated_for_advancement_at)
    """
    )

    # Count active rules
    active_rules = await db.fetchval(
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
          AND executed_at > NOW() - INTERVAL '7 days'
        ORDER BY executed_at DESC
        LIMIT 10
    """
    )

    logger.info(
        "advancement_statistics_retrieved",
        active_rules=active_rules,
        pending_evaluations=pending_evaluations,
    )

    return {
        "active_rules": active_rules,
        "pending_evaluations": pending_evaluations,
        "total_executions_30d": sum(status_counts.values()),
        "success_count": status_counts.get("success", 0),
        "failed_count": status_counts.get("failed", 0),
        "dry_run_count": status_counts.get("dry_run", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "recent_failures": [
            {
                "execution_id": str(f["execution_id"]),
                "schedule_id": str(f["schedule_id"]),
                "application_id": str(f["application_id"]),
                "failure_reason": f["failure_reason"],
                "executed_at": f["executed_at"].isoformat(),
            }
            for f in recent_failures
        ],
    }


async def get_schedules_for_application(application_id: str) -> list[dict[str, Any]]:
    """
    Get all schedules for an application.

    Args:
        application_id: Application UUID

    Returns:
        List of schedule records with full details
    """
    schedules = await db.fetch(
        """
        SELECT schedule_id, application_id, status, interview_stage_id, updated_at
        FROM interview_schedules
        WHERE application_id = $1
        ORDER BY updated_at DESC
    """,
        UUID(application_id),
    )

    logger.info(
        "schedules_retrieved_for_application",
        application_id=application_id,
        count=len(schedules),
    )

    return [
        {
            "schedule_id": str(s["schedule_id"]),
            "application_id": str(s["application_id"]),
            "status": s["status"],
            "interview_stage_id": (
                str(s["interview_stage_id"]) if s["interview_stage_id"] else None
            ),
            "updated_at": s["updated_at"].isoformat() if s["updated_at"] else None,
        }
        for s in schedules
    ]


async def get_all_advancement_rules(active_only: bool = True) -> list[dict[str, Any]]:
    """
    Get all advancement rules with their requirements and actions.

    Args:
        active_only: If True, only return active rules

    Returns:
        List of rule dicts with nested requirements and actions
    """
    # Get all rules
    where_clause = "WHERE r.is_active = true" if active_only else ""
    rules = await db.fetch(
        f"""
        SELECT
            r.rule_id,
            r.job_id,
            r.interview_plan_id,
            r.interview_stage_id,
            r.target_stage_id,
            r.is_active,
            r.created_at,
            r.updated_at
        FROM advancement_rules r
        {where_clause}
        ORDER BY r.created_at DESC
    """
    )

    result = []
    for rule in rules:
        rule_id = str(rule["rule_id"])

        # Get requirements for this rule
        requirements = await db.fetch(
            """
            SELECT
                requirement_id,
                interview_id,
                score_field_path,
                operator,
                threshold_value,
                is_required,
                created_at
            FROM advancement_rule_requirements
            WHERE rule_id = $1
            ORDER BY created_at
        """,
            rule["rule_id"],
        )

        # Get actions for this rule
        actions = await db.fetch(
            """
            SELECT
                action_id,
                action_type,
                action_config,
                execution_order,
                created_at
            FROM advancement_rule_actions
            WHERE rule_id = $1
            ORDER BY execution_order
        """,
            rule["rule_id"],
        )

        result.append(
            {
                "rule_id": rule_id,
                "job_id": str(rule["job_id"]) if rule["job_id"] else None,
                "interview_plan_id": str(rule["interview_plan_id"]),
                "interview_stage_id": str(rule["interview_stage_id"]),
                "target_stage_id": (
                    str(rule["target_stage_id"]) if rule["target_stage_id"] else None
                ),
                "is_active": rule["is_active"],
                "created_at": (
                    rule["created_at"].isoformat() if rule["created_at"] else None
                ),
                "updated_at": (
                    rule["updated_at"].isoformat() if rule["updated_at"] else None
                ),
                "requirements": [
                    {
                        "requirement_id": str(req["requirement_id"]),
                        "interview_id": str(req["interview_id"]),
                        "score_field_path": req["score_field_path"],
                        "operator": req["operator"],
                        "threshold_value": req["threshold_value"],
                        "is_required": req["is_required"],
                        "created_at": (
                            req["created_at"].isoformat() if req["created_at"] else None
                        ),
                    }
                    for req in requirements
                ],
                "actions": [
                    {
                        "action_id": str(act["action_id"]),
                        "action_type": act["action_type"],
                        "action_config": (
                            json.loads(act["action_config"])
                            if act["action_config"]
                            else None
                        ),
                        "execution_order": act["execution_order"],
                        "created_at": (
                            act["created_at"].isoformat() if act["created_at"] else None
                        ),
                    }
                    for act in actions
                ],
            }
        )

    logger.info(
        "advancement_rules_retrieved", count=len(result), active_only=active_only
    )
    return result


async def get_advancement_rule_by_id(rule_id: str) -> dict[str, Any] | None:
    """
    Get a specific advancement rule by ID with all requirements and actions.

    Args:
        rule_id: Rule UUID

    Returns:
        Rule dict with nested requirements and actions, or None if not found
    """
    rule = await db.fetchrow(
        """
        SELECT
            rule_id,
            job_id,
            interview_plan_id,
            interview_stage_id,
            target_stage_id,
            is_active,
            created_at,
            updated_at
        FROM advancement_rules
        WHERE rule_id = $1
    """,
        UUID(rule_id),
    )

    if not rule:
        logger.warning("rule_not_found", rule_id=rule_id)
        return None

    # Get requirements
    requirements = await db.fetch(
        """
        SELECT
            requirement_id,
            interview_id,
            score_field_path,
            operator,
            threshold_value,
            is_required,
            created_at
        FROM advancement_rule_requirements
        WHERE rule_id = $1
        ORDER BY created_at
    """,
        rule["rule_id"],
    )

    # Get actions
    actions = await db.fetch(
        """
        SELECT
            action_id,
            action_type,
            action_config,
            execution_order,
            created_at
        FROM advancement_rule_actions
        WHERE rule_id = $1
        ORDER BY execution_order
    """,
        rule["rule_id"],
    )

    logger.info("advancement_rule_retrieved", rule_id=rule_id)

    return {
        "rule_id": str(rule["rule_id"]),
        "job_id": str(rule["job_id"]) if rule["job_id"] else None,
        "interview_plan_id": str(rule["interview_plan_id"]),
        "interview_stage_id": str(rule["interview_stage_id"]),
        "target_stage_id": (
            str(rule["target_stage_id"]) if rule["target_stage_id"] else None
        ),
        "is_active": rule["is_active"],
        "created_at": rule["created_at"].isoformat() if rule["created_at"] else None,
        "updated_at": rule["updated_at"].isoformat() if rule["updated_at"] else None,
        "requirements": [
            {
                "requirement_id": str(req["requirement_id"]),
                "interview_id": str(req["interview_id"]),
                "score_field_path": req["score_field_path"],
                "operator": req["operator"],
                "threshold_value": req["threshold_value"],
                "is_required": req["is_required"],
                "created_at": (
                    req["created_at"].isoformat() if req["created_at"] else None
                ),
            }
            for req in requirements
        ],
        "actions": [
            {
                "action_id": str(act["action_id"]),
                "action_type": act["action_type"],
                "action_config": (
                    json.loads(act["action_config"]) if act["action_config"] else None
                ),
                "execution_order": act["execution_order"],
                "created_at": (
                    act["created_at"].isoformat() if act["created_at"] else None
                ),
            }
            for act in actions
        ],
    }


async def delete_advancement_rule(rule_id: str) -> bool:
    """
    Soft-delete an advancement rule by setting is_active=false.

    Args:
        rule_id: Rule UUID to delete

    Returns:
        True if deleted, False if not found

    Note:
        This is a soft delete for audit trail purposes.
        Requirements and actions are left intact.
    """
    result = await db.execute(
        """
        UPDATE advancement_rules
        SET is_active = false, updated_at = NOW()
        WHERE rule_id = $1 AND is_active = true
    """,
        UUID(rule_id),
    )

    # Check if row was updated (result will be like "UPDATE 1" or "UPDATE 0")
    rows_affected = int(result.split()[-1]) if result else 0

    if rows_affected > 0:
        logger.info("advancement_rule_deleted", rule_id=rule_id)
        return True
    else:
        logger.warning("advancement_rule_not_found_or_already_deleted", rule_id=rule_id)
        return False
