"""Database record type definitions.

MAINTENANCE NOTE:
This file must be kept in sync with database/schema.sql manually.
Add types incrementally as needed - only create types for records
that are fetched and converted to dicts in the service layer.
Consider automated generation if schema changes become frequent.

NOTE: This file must track database/schema.sql manually.
Use total=False and NotRequired for nullable/optional columns.
Add new types incrementally as needed - don't create unused types.
"""

from datetime import datetime
from typing import Any, NotRequired, TypedDict
from uuid import UUID


class InterviewScheduleRecordTD(TypedDict):
    """Record from interview_schedules table.

    Used in: advancement.py:70, admin.py:213
    """

    schedule_id: UUID
    application_id: UUID
    interview_stage_id: NotRequired[UUID | None]
    status: str
    candidate_id: NotRequired[str | None]
    updated_at: datetime
    job_id: NotRequired[UUID | None]
    interview_plan_id: NotRequired[UUID | None]
    last_evaluated_for_advancement_at: NotRequired[datetime | None]


class AdvancementRuleRecordTD(TypedDict):
    """Record from advancement_rules table.

    Used in: rules.py:118, admin.py:293
    """

    rule_id: UUID
    job_id: NotRequired[UUID | None]
    interview_plan_id: UUID
    interview_stage_id: UUID
    target_stage_id: NotRequired[UUID | None]
    is_active: bool
    created_at: NotRequired[datetime | None]
    updated_at: NotRequired[datetime | None]


class AdvancementRequirementRecordTD(TypedDict):
    """Record from advancement_rule_requirements table.

    Used in: rules.py:118, admin.py:305
    """

    requirement_id: UUID
    rule_id: UUID
    interview_id: UUID
    score_field_path: str
    operator: str
    threshold_value: str
    is_required: bool
    created_at: NotRequired[datetime | None]


class AdvancementActionRecordTD(TypedDict):
    """Record from advancement_rule_actions table.

    Used in: rules.py:119, admin.py:319
    """

    action_id: UUID
    rule_id: UUID
    action_type: str
    action_config: NotRequired[str | None]  # JSONB stored as string
    execution_order: int
    created_at: NotRequired[datetime | None]


class FeedbackSubmissionRecordTD(TypedDict):
    """Record from feedback_submissions table.

    Used in: advancement.py:145, advancement.py:474
    """

    feedback_id: UUID
    application_id: UUID
    event_id: UUID
    interviewer_id: UUID
    interview_id: UUID
    submitted_at: datetime
    submitted_values: str | dict[str, Any]  # JSONB, may be pre-parsed
    processed_for_advancement_at: NotRequired[datetime | None]
    created_at: NotRequired[datetime | None]
