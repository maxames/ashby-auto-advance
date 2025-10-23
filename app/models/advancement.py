"""Pydantic models for advancement rule creation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AdvancementRuleRequirementCreate(BaseModel):
    """Model for creating advancement rule requirement."""

    interview_id: str
    score_field_path: str
    operator: str  # ">=", ">", "==", "<=", "<"
    threshold_value: str  # Stored as text, cast during evaluation
    is_required: bool = True


class AdvancementRuleActionCreate(BaseModel):
    """Model for creating advancement rule action."""

    action_type: str  # e.g., "advance_stage", "send_rejection_notification"
    action_config: dict[str, Any] | None = None
    execution_order: int = 1


class AdvancementRuleCreate(BaseModel):
    """Model for creating advancement rule."""

    job_id: str | None = None  # NULL = applies to all jobs
    interview_plan_id: str
    interview_stage_id: str
    target_stage_id: str | None = None  # NULL = next sequential stage
    requirements: list[AdvancementRuleRequirementCreate]
    actions: list[AdvancementRuleActionCreate]
