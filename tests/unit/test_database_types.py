"""Verify database record TypedDicts match schema.sql."""

from datetime import datetime
from uuid import uuid4

from app.types.database import (
    AdvancementActionRecordTD,
    AdvancementRequirementRecordTD,
    AdvancementRuleRecordTD,
    FeedbackSubmissionRecordTD,
    InterviewScheduleRecordTD,
)


def test_interview_schedule_record_has_required_fields():
    """Verify InterviewScheduleRecordTD has expected structure."""
    # This is a compile-time check - if it type-checks, it's correct
    schedule: InterviewScheduleRecordTD = {
        "schedule_id": uuid4(),
        "application_id": uuid4(),
        "status": "Scheduled",
        "updated_at": datetime.now(),
    }
    assert "schedule_id" in schedule
    assert "application_id" in schedule
    assert "status" in schedule
    assert "updated_at" in schedule


def test_advancement_rule_record_has_required_fields():
    """Verify AdvancementRuleRecordTD has expected structure."""
    rule: AdvancementRuleRecordTD = {
        "rule_id": uuid4(),
        "interview_plan_id": uuid4(),
        "interview_stage_id": uuid4(),
        "is_active": True,
    }
    assert "rule_id" in rule
    assert "interview_plan_id" in rule
    assert "interview_stage_id" in rule
    assert "is_active" in rule


def test_advancement_requirement_record_has_required_fields():
    """Verify AdvancementRequirementRecordTD has expected structure."""
    requirement: AdvancementRequirementRecordTD = {
        "requirement_id": uuid4(),
        "rule_id": uuid4(),
        "interview_id": uuid4(),
        "score_field_path": "overall_score",
        "operator": ">=",
        "threshold_value": "3",
        "is_required": True,
    }
    assert "requirement_id" in requirement
    assert "rule_id" in requirement
    assert "interview_id" in requirement
    assert "score_field_path" in requirement
    assert "operator" in requirement
    assert "threshold_value" in requirement
    assert "is_required" in requirement


def test_advancement_action_record_has_required_fields():
    """Verify AdvancementActionRecordTD has expected structure."""
    action: AdvancementActionRecordTD = {
        "action_id": uuid4(),
        "rule_id": uuid4(),
        "action_type": "advance_stage",
        "execution_order": 1,
    }
    assert "action_id" in action
    assert "rule_id" in action
    assert "action_type" in action
    assert "execution_order" in action


def test_feedback_submission_record_has_required_fields():
    """Verify FeedbackSubmissionRecordTD has expected structure."""
    submission: FeedbackSubmissionRecordTD = {
        "feedback_id": uuid4(),
        "application_id": uuid4(),
        "event_id": uuid4(),
        "interviewer_id": uuid4(),
        "interview_id": uuid4(),
        "submitted_at": datetime.now(),
        "submitted_values": {"overall_score": "3"},
    }
    assert "feedback_id" in submission
    assert "application_id" in submission
    assert "event_id" in submission
    assert "interviewer_id" in submission
    assert "interview_id" in submission
    assert "submitted_at" in submission
    assert "submitted_values" in submission


def test_interview_schedule_record_accepts_optional_fields():
    """Verify InterviewScheduleRecordTD accepts NotRequired fields."""
    schedule: InterviewScheduleRecordTD = {
        "schedule_id": uuid4(),
        "application_id": uuid4(),
        "status": "Scheduled",
        "updated_at": datetime.now(),
        "interview_stage_id": uuid4(),
        "candidate_id": "candidate_123",
        "job_id": uuid4(),
        "interview_plan_id": uuid4(),
        "last_evaluated_for_advancement_at": datetime.now(),
    }
    assert "interview_stage_id" in schedule
    assert "candidate_id" in schedule
    assert "job_id" in schedule
    assert "interview_plan_id" in schedule
    assert "last_evaluated_for_advancement_at" in schedule


def test_feedback_submission_record_accepts_string_or_dict_values():
    """Verify FeedbackSubmissionRecordTD accepts both string and dict for submitted_values."""
    # Test with dict
    submission_dict: FeedbackSubmissionRecordTD = {
        "feedback_id": uuid4(),
        "application_id": uuid4(),
        "event_id": uuid4(),
        "interviewer_id": uuid4(),
        "interview_id": uuid4(),
        "submitted_at": datetime.now(),
        "submitted_values": {"overall_score": "3"},
    }
    assert isinstance(submission_dict["submitted_values"], dict)

    # Test with string (JSONB as string)
    submission_str: FeedbackSubmissionRecordTD = {
        "feedback_id": uuid4(),
        "application_id": uuid4(),
        "event_id": uuid4(),
        "interviewer_id": uuid4(),
        "interview_id": uuid4(),
        "submitted_at": datetime.now(),
        "submitted_values": '{"overall_score": "3"}',
    }
    assert isinstance(submission_str["submitted_values"], str)
