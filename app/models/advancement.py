"""Pydantic models for advancement rules and metadata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ============================================
# Input Models (Rule Creation)
# ============================================


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


# ============================================
# Response Models (Metadata)
# ============================================


class JobMetadata(BaseModel):
    """Metadata about a job."""

    id: str
    title: str
    status: str | None
    department_id: str | None
    location: str | None
    employment_type: str | None


class JobsListResponse(BaseModel):
    """Response for jobs list."""

    jobs: list[JobMetadata]


class InterviewPlanMetadata(BaseModel):
    """Metadata about an interview plan."""

    id: str
    title: str
    is_default: bool


class PlansListResponse(BaseModel):
    """Response for plans list."""

    plans: list[InterviewPlanMetadata]


class InterviewStageMetadata(BaseModel):
    """Metadata about an interview stage."""

    id: str
    title: str
    type: str | None
    order: int


class StagesListResponse(BaseModel):
    """Response for stages list."""

    stages: list[InterviewStageMetadata]


class InterviewMetadata(BaseModel):
    """Metadata about an interview."""

    id: str
    title: str
    job_id: str | None
    feedback_form_id: str | None


class InterviewsListResponse(BaseModel):
    """Response for interviews list."""

    interviews: list[InterviewMetadata]


# ============================================
# Response Models (Advancement Rules)
# ============================================


class AdvancementRuleRequirementResponse(BaseModel):
    """Response model for advancement rule requirement."""

    requirement_id: str
    interview_id: str
    score_field_path: str
    operator: str
    threshold_value: str
    is_required: bool
    created_at: str | None


class AdvancementRuleActionResponse(BaseModel):
    """Response model for advancement rule action."""

    action_id: str
    action_type: str
    action_config: dict[str, Any] | None
    execution_order: int
    created_at: str | None


class AdvancementRuleResponse(BaseModel):
    """Response model for advancement rule."""

    rule_id: str
    job_id: str | None
    interview_plan_id: str
    interview_stage_id: str
    target_stage_id: str | None
    is_active: bool
    created_at: str | None
    updated_at: str | None
    requirements: list[AdvancementRuleRequirementResponse]
    actions: list[AdvancementRuleActionResponse]


class RulesListResponse(BaseModel):
    """Response for rules list."""

    count: int
    rules: list[AdvancementRuleResponse]


class RuleCreateResponse(BaseModel):
    """Response after creating a rule."""

    rule_id: str
    job_id: str | None
    interview_plan_id: str
    interview_stage_id: str
    target_stage_id: str | None
    requirement_ids: list[str]
    action_ids: list[str]
    status: str


class RuleDeleteResponse(BaseModel):
    """Response after deleting a rule."""

    status: str
    rule_id: str


class RecentFailure(BaseModel):
    """Model for recent failure in stats."""

    execution_id: str
    schedule_id: str
    application_id: str
    failure_reason: str | None
    executed_at: str


class AdvancementStatsResponse(BaseModel):
    """Response for advancement statistics."""

    active_rules: int
    pending_evaluations: int
    total_executions_30d: int
    success_count: int
    failed_count: int
    dry_run_count: int
    rejected_count: int
    recent_failures: list[RecentFailure]
