"""Rule evaluation engine for advancement decisions."""

from __future__ import annotations

import json
from typing import Any

from structlog import get_logger

from app.clients.ashby import list_interview_stages_for_plan
from app.core.database import db

logger = get_logger()


async def find_matching_rule(
    job_id: str | None, interview_plan_id: str, interview_stage_id: str
) -> dict[str, Any] | None:
    """
    Find active advancement rule matching the given criteria.

    Matches on interview_plan_id AND interview_stage_id.
    Optionally filters by job_id if rule specifies it.

    Args:
        job_id: Job UUID (nullable)
        interview_plan_id: Interview plan UUID
        interview_stage_id: Interview stage UUID

    Returns:
        Rule data with requirements and actions, or None if no match

    Raises:
        RuntimeError: If database pool not initialized
    """
    query = """
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
        WHERE r.is_active = true
          AND r.interview_plan_id = $1
          AND r.interview_stage_id = $2
          AND (r.job_id IS NULL OR r.job_id = $3)
        ORDER BY r.job_id NULLS LAST  -- Prefer job-specific rules
        LIMIT 1
    """

    row = await db.fetchrow(query, interview_plan_id, interview_stage_id, job_id)

    if not row:
        logger.info(
            "no_matching_rule",
            job_id=job_id,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )
        return None

    rule_id = row["rule_id"]

    # Fetch requirements
    requirements = await db.fetch(
        """
        SELECT
            requirement_id,
            rule_id,
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
        rule_id,
    )

    # Fetch actions
    actions = await db.fetch(
        """
        SELECT
            action_id,
            rule_id,
            action_type,
            action_config,
            execution_order,
            created_at
        FROM advancement_rule_actions
        WHERE rule_id = $1
        ORDER BY execution_order
    """,
        rule_id,
    )

    logger.info(
        "rule_matched",
        rule_id=rule_id,
        requirements_count=len(requirements),
        actions_count=len(actions),
    )

    return {
        "rule_id": str(rule_id),
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "interview_plan_id": str(row["interview_plan_id"]),
        "interview_stage_id": str(row["interview_stage_id"]),
        "target_stage_id": (str(row["target_stage_id"]) if row["target_stage_id"] else None),
        "requirements": [dict(r) for r in requirements],
        "actions": [dict(a) for a in actions],
    }


async def evaluate_rule_requirements(
    rule_id: str, schedule_id: str, feedback_submissions: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Evaluate all requirements for a rule against submitted feedback.

    For each requirement:
    - Check if interview is scheduled
    - If required and not scheduled: BLOCK
    - If scheduled: find matching feedback from ALL assigned interviewers
    - Extract score value from submittedValues
    - Compare against threshold using operator
    - All interviewers must pass for interview to pass

    Note: If an interview is scheduled multiple times (e.g., multiple panel rounds),
    ALL events must have feedback from ALL assigned interviewers before the requirement
    passes. This ensures complete evaluation across all instances of the interview.

    Args:
        rule_id: Rule UUID
        schedule_id: Schedule UUID
        feedback_submissions: List of feedback submissions from database

    Returns:
        {
            "all_passed": bool,
            "results": [
                {
                    "requirement_id": str,
                    "interview_id": str,
                    "passed": bool,
                    "blocking_reason": str | None,
                    "interviewer_results": [...]
                }
            ]
        }
    """
    # Get requirements for this rule
    requirements = await db.fetch(
        """
        SELECT
            requirement_id,
            interview_id,
            score_field_path,
            operator,
            threshold_value,
            is_required
        FROM advancement_rule_requirements
        WHERE rule_id = $1
    """,
        rule_id,
    )

    # Get scheduled events for this schedule
    scheduled_events = await db.fetch(
        """
        SELECT
            e.event_id,
            e.interview_id,
            COUNT(a.interviewer_id) as interviewer_count
        FROM interview_events e
        LEFT JOIN interview_assignments a ON a.event_id = e.event_id
        WHERE e.schedule_id = $1
        GROUP BY e.event_id, e.interview_id
    """,
        schedule_id,
    )

    # Build lookup: interview_id -> list of event_ids
    interview_events: dict[str, list[dict[str, Any]]] = {}
    for event in scheduled_events:
        interview_id = str(event["interview_id"])
        if interview_id not in interview_events:
            interview_events[interview_id] = []
        interview_events[interview_id].append(
            {
                "event_id": str(event["event_id"]),
                "interviewer_count": event["interviewer_count"],
            }
        )

    # Build lookup: event_id -> list of feedback
    feedback_by_event: dict[str, list[dict[str, Any]]] = {}
    for feedback in feedback_submissions:
        event_id = str(feedback["event_id"])
        if event_id not in feedback_by_event:
            feedback_by_event[event_id] = []
        feedback_by_event[event_id].append(feedback)

    results: list[dict[str, Any]] = []
    all_passed = True

    for req in requirements:
        requirement_id = str(req["requirement_id"])
        interview_id = str(req["interview_id"])
        score_field = req["score_field_path"]
        operator = req["operator"]
        threshold = req["threshold_value"]
        is_required = req["is_required"]

        # Check if interview is scheduled
        if interview_id not in interview_events:
            if is_required:
                # Required interview not scheduled: BLOCK
                results.append(
                    {
                        "requirement_id": requirement_id,
                        "interview_id": interview_id,
                        "passed": False,
                        "blocking_reason": "required_interview_not_scheduled",
                    }
                )
                all_passed = False
            else:
                # Optional interview not scheduled: SKIP
                results.append(
                    {
                        "requirement_id": requirement_id,
                        "interview_id": interview_id,
                        "passed": True,
                        "blocking_reason": None,
                        "note": "optional_interview_not_scheduled",
                    }
                )
            continue

        # Interview is scheduled - check all events for this interview
        # Note: If interview is scheduled multiple times, we require feedback
        # from all interviewers across ALL events
        interview_passed = True
        interviewer_results: list[dict[str, Any]] = []

        for event_info in interview_events[interview_id]:
            event_id = event_info["event_id"]
            expected_count = event_info["interviewer_count"]

            # Get feedback for this event
            event_feedback = feedback_by_event.get(event_id, [])
            actual_count = len(event_feedback)

            # All interviewers must submit
            if actual_count < expected_count:
                interviewer_results.append(
                    {
                        "event_id": event_id,
                        "passed": False,
                        "reason": f"missing_feedback_{actual_count}_of_{expected_count}",
                    }
                )
                interview_passed = False
                continue

            # Check each interviewer's score
            for feedback in event_feedback:
                submitted_values = feedback["submitted_values"]
                # Parse JSON if it's a string (from database)
                if isinstance(submitted_values, str):
                    submitted_values = json.loads(submitted_values)
                score_value = submitted_values.get(score_field)

                if score_value is None:
                    interviewer_results.append(
                        {
                            "event_id": event_id,
                            "interviewer_id": str(feedback["interviewer_id"]),
                            "passed": False,
                            "reason": f"score_field_missing_{score_field}",
                        }
                    )
                    interview_passed = False
                    continue

                # Compare against threshold
                passed = _compare_score(score_value, operator, threshold)

                interviewer_results.append(
                    {
                        "event_id": event_id,
                        "interviewer_id": str(feedback["interviewer_id"]),
                        "passed": passed,
                        "score_value": score_value,
                        "operator": operator,
                        "threshold": threshold,
                    }
                )

                if not passed:
                    interview_passed = False

        results.append(
            {
                "requirement_id": requirement_id,
                "interview_id": interview_id,
                "passed": interview_passed,
                "blocking_reason": (None if interview_passed else "score_threshold_not_met"),
                "interviewer_results": interviewer_results,
            }
        )

        if not interview_passed:
            all_passed = False

    logger.info(
        "rule_requirements_evaluated",
        rule_id=rule_id,
        schedule_id=schedule_id,
        all_passed=all_passed,
        total_requirements=len(requirements),
    )

    return {"all_passed": all_passed, "results": results}


def _compare_score(score_value: Any, operator: str, threshold: str) -> bool:
    """
    Compare score value against threshold using operator.

    Args:
        score_value: Actual score from feedback
        operator: Comparison operator (>=, >, ==, <, <=)
        threshold: Threshold value as string

    Returns:
        True if comparison passes
    """
    try:
        # Try to convert both to numbers for numeric comparison
        score_num = float(score_value)
        threshold_num = float(threshold)

        if operator == ">=":
            return score_num >= threshold_num
        elif operator == ">":
            return score_num > threshold_num
        elif operator == "==":
            return score_num == threshold_num
        elif operator == "<=":
            return score_num <= threshold_num
        elif operator == "<":
            return score_num < threshold_num
        else:
            logger.warning("unknown_operator", operator=operator)
            return False

    except (ValueError, TypeError):
        # Fall back to string comparison
        if operator == "==":
            return str(score_value) == threshold
        else:
            logger.warning(
                "non_numeric_comparison",
                score_value=score_value,
                threshold=threshold,
                operator=operator,
            )
            return False


async def get_target_stage_for_rule(
    rule_id: str, current_stage_id: str, interview_plan_id: str
) -> str:
    """
    Get target stage for advancement.

    If rule specifies target_stage_id: return it.
    If NULL: fetch stages for plan, find current stage's order, return stage with order+1.

    Args:
        rule_id: Rule UUID
        current_stage_id: Current interview stage UUID
        interview_plan_id: Interview plan UUID

    Returns:
        Target stage UUID

    Raises:
        ValueError: If next stage doesn't exist
    """
    # Get target_stage_id from rule
    row = await db.fetchrow(
        """
        SELECT target_stage_id
        FROM advancement_rules
        WHERE rule_id = $1
    """,
        rule_id,
    )

    if not row:
        raise ValueError(f"Rule not found: {rule_id}")

    target_stage_id = row["target_stage_id"]

    if target_stage_id:
        logger.info("explicit_target_stage", rule_id=rule_id, target_stage_id=target_stage_id)
        return str(target_stage_id)

    # Fetch all stages for plan
    stages = await list_interview_stages_for_plan(interview_plan_id)

    # Find current stage
    current_stage = None
    for stage in stages:
        if stage["id"] == current_stage_id:
            current_stage = stage
            break

    if not current_stage:
        raise ValueError(f"Current stage not found in plan: {current_stage_id}")

    # Find next stage
    current_order = current_stage["orderInInterviewPlan"]
    next_order = current_order + 1

    next_stage = None
    for stage in stages:
        if stage["orderInInterviewPlan"] == next_order:
            next_stage = stage
            break

    if not next_stage:
        raise ValueError(
            f"No next stage found (current order: {current_order}, plan: {interview_plan_id})"
        )

    logger.info(
        "sequential_target_stage",
        rule_id=rule_id,
        current_order=current_order,
        next_order=next_order,
        target_stage_id=next_stage["id"],
    )

    return next_stage["id"]
