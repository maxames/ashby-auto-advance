"""Tests for admin API endpoints (app/api/admin.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api import admin as admin_api


@pytest.mark.asyncio
async def test_admin_sync_forms_triggers_sync():
    """/admin/sync-forms calls sync_feedback_forms."""
    with patch(
        "app.api.admin.sync_feedback_forms", new_callable=AsyncMock
    ) as mock_sync:
        response = await admin_api.admin_sync_forms()

        mock_sync.assert_called_once()
        assert response["status"] == "completed"


@pytest.mark.asyncio
async def test_admin_sync_forms_returns_completed_status():
    """Returns {"status": "completed", "message": ...}."""
    with patch("app.api.admin.sync_feedback_forms", new_callable=AsyncMock):
        response = await admin_api.admin_sync_forms()

        assert "status" in response
        assert response["status"] == "completed"
        assert "message" in response


@pytest.mark.asyncio
async def test_admin_sync_slack_users_triggers_sync():
    """/admin/sync-slack-users calls sync_slack_users."""
    with patch("app.api.admin.sync_slack_users", new_callable=AsyncMock) as mock_sync:
        response = await admin_api.admin_sync_slack_users()

        mock_sync.assert_called_once()
        assert response["status"] == "completed"


@pytest.mark.asyncio
async def test_admin_sync_slack_users_returns_completed_status():
    """Returns completed status message."""
    with patch("app.api.admin.sync_slack_users", new_callable=AsyncMock):
        response = await admin_api.admin_sync_slack_users()

        assert response == {"status": "completed", "message": "Slack users synced"}


@pytest.mark.asyncio
async def test_admin_stats_returns_statistics():
    """/admin/stats calls get_advancement_statistics."""
    mock_stats = {
        "active_rules": 5,
        "pending_evaluations": 10,
        "total_executions_30d": 0,
        "success_count": 0,
        "failed_count": 0,
        "dry_run_count": 0,
        "rejected_count": 0,
        "recent_failures": [],
    }

    with patch(
        "app.api.admin.admin_service.get_advancement_statistics", new_callable=AsyncMock
    ) as mock_get_stats:
        mock_get_stats.return_value = mock_stats

        response = await admin_api.admin_stats()

        mock_get_stats.assert_called_once()
        assert response.model_dump() == mock_stats


@pytest.mark.asyncio
async def test_admin_create_rule_valid_input_creates_rule():
    """Valid rule creation returns rule_id."""
    from app.models.advancement import (
        AdvancementRuleActionCreate,
        AdvancementRuleCreate,
        AdvancementRuleRequirementCreate,
    )

    rule_id = str(uuid4())
    plan_id = str(uuid4())
    stage_id = str(uuid4())
    target_stage_id = str(uuid4())

    rule = AdvancementRuleCreate(
        job_id=None,
        interview_plan_id=plan_id,
        interview_stage_id=stage_id,
        target_stage_id=target_stage_id,
        requirements=[
            AdvancementRuleRequirementCreate(
                interview_id=str(uuid4()),
                score_field_path="overall_score",
                operator=">=",
                threshold_value="3",
                is_required=True,
            )
        ],
        actions=[
            AdvancementRuleActionCreate(
                action_type="advance_stage",
                action_config={},
                execution_order=1,
            )
        ],
    )

    mock_result = {
        "rule_id": rule_id,
        "job_id": None,
        "interview_plan_id": plan_id,
        "interview_stage_id": stage_id,
        "target_stage_id": target_stage_id,
        "requirement_ids": [str(uuid4())],
        "action_ids": [str(uuid4())],
    }

    with patch(
        "app.api.admin.admin_service.create_advancement_rule", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_result

        response = await admin_api.create_advancement_rule(rule)

        mock_create.assert_called_once()
        assert response.rule_id == rule_id
        assert response.status == "created"


@pytest.mark.asyncio
async def test_admin_create_rule_converts_pydantic_to_dict():
    """Pydantic models converted for service layer."""
    from app.models.advancement import (
        AdvancementRuleActionCreate,
        AdvancementRuleCreate,
        AdvancementRuleRequirementCreate,
    )

    plan_id = str(uuid4())
    stage_id = str(uuid4())

    rule = AdvancementRuleCreate(
        job_id=None,
        interview_plan_id=plan_id,
        interview_stage_id=stage_id,
        target_stage_id=None,
        requirements=[
            AdvancementRuleRequirementCreate(
                interview_id=str(uuid4()),
                score_field_path="overall_score",
                operator=">=",
                threshold_value="3",
                is_required=True,
            )
        ],
        actions=[
            AdvancementRuleActionCreate(
                action_type="advance_stage",
                action_config={},
                execution_order=1,
            )
        ],
    )

    mock_result = {
        "rule_id": str(uuid4()),
        "job_id": None,
        "interview_plan_id": plan_id,
        "interview_stage_id": stage_id,
        "target_stage_id": None,
        "requirement_ids": [str(uuid4())],
        "action_ids": [str(uuid4())],
    }

    with patch(
        "app.api.admin.admin_service.create_advancement_rule", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_result

        await admin_api.create_advancement_rule(rule)

        # Verify service was called with dicts, not Pydantic models
        call_kwargs = mock_create.call_args[1]
        assert isinstance(call_kwargs["requirements"], list)
        assert isinstance(call_kwargs["actions"], list)
        assert isinstance(call_kwargs["requirements"][0], dict)
        assert isinstance(call_kwargs["actions"][0], dict)


@pytest.mark.asyncio
async def test_admin_trigger_advancement_by_schedule_id():
    """Evaluates specific schedule."""
    schedule_id = str(uuid4())
    mock_evaluation = {"ready": True, "blocking_reason": None}

    with patch(
        "app.services.advancement.evaluate_schedule_for_advancement",
        new_callable=AsyncMock,
    ) as mock_evaluate:
        mock_evaluate.return_value = mock_evaluation

        response = await admin_api.trigger_advancement_evaluation(
            schedule_id=schedule_id
        )

        mock_evaluate.assert_called_once_with(schedule_id)
        assert response["schedule_id"] == schedule_id
        assert response["evaluation"] == mock_evaluation


@pytest.mark.asyncio
async def test_admin_trigger_advancement_by_application_id():
    """Evaluates all schedules for application."""
    app_id = str(uuid4())
    schedule1_id = str(uuid4())
    schedule2_id = str(uuid4())

    mock_schedules = [
        {"schedule_id": schedule1_id},
        {"schedule_id": schedule2_id},
    ]

    mock_evaluation = {"ready": True, "blocking_reason": None}

    with (
        patch(
            "app.api.admin.admin_service.get_schedules_for_application",
            new_callable=AsyncMock,
        ) as mock_get_schedules,
        patch(
            "app.services.advancement.evaluate_schedule_for_advancement",
            new_callable=AsyncMock,
        ) as mock_evaluate,
    ):
        mock_get_schedules.return_value = mock_schedules
        mock_evaluate.return_value = mock_evaluation

        response = await admin_api.trigger_advancement_evaluation(application_id=app_id)

        mock_get_schedules.assert_called_once_with(app_id)
        assert mock_evaluate.call_count == 2
        assert response["application_id"] == app_id
        assert response["schedules_evaluated"] == 2
        assert len(response["results"]) == 2


@pytest.mark.asyncio
async def test_admin_trigger_advancement_missing_params_returns_error():
    """Missing both params returns error."""
    response = await admin_api.trigger_advancement_evaluation()

    assert "error" in response
    assert "Must provide either schedule_id or application_id" in response["error"]


@pytest.mark.asyncio
async def test_list_jobs_endpoint_calls_service():
    """/admin/metadata/jobs calls metadata service."""
    mock_jobs = [
        {
            "id": str(uuid4()),
            "title": "Engineer",
            "status": "Open",
            "department_id": None,
            "location": None,
            "employment_type": None,
        }
    ]

    with patch(
        "app.api.admin.metadata_service.get_jobs", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_jobs

        response = await admin_api.list_jobs(active_only=True)

        mock_get.assert_called_once_with(active_only=True)
        assert len(response.jobs) == 1
        assert response.jobs[0].title == "Engineer"


@pytest.mark.asyncio
async def test_get_job_plans_endpoint_calls_service():
    """/admin/metadata/jobs/{job_id}/plans calls metadata service."""
    job_id = str(uuid4())
    mock_plans = [
        {"id": str(uuid4()), "title": "Engineering Onsite", "is_default": True}
    ]

    with patch(
        "app.api.admin.metadata_service.get_plans_for_job", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_plans

        response = await admin_api.get_job_plans(job_id)

        mock_get.assert_called_once_with(job_id)
        assert len(response.plans) == 1
        assert response.plans[0].title == "Engineering Onsite"


@pytest.mark.asyncio
async def test_get_plan_stages_endpoint_calls_service():
    """/admin/metadata/plans/{plan_id}/stages calls metadata service."""
    plan_id = str(uuid4())
    mock_stages = [
        {"id": str(uuid4()), "title": "Technical Screen", "type": "Active", "order": 1}
    ]

    with patch(
        "app.api.admin.metadata_service.get_stages_for_plan", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_stages

        response = await admin_api.get_plan_stages(plan_id)

        mock_get.assert_called_once_with(plan_id)
        assert len(response.stages) == 1
        assert response.stages[0].title == "Technical Screen"


@pytest.mark.asyncio
async def test_list_interviews_endpoint_calls_service():
    """/admin/metadata/interviews calls metadata service."""
    job_id = str(uuid4())
    mock_interviews = [
        {
            "id": str(uuid4()),
            "title": "Tech Screen",
            "job_id": job_id,
            "feedback_form_id": str(uuid4()),
        }
    ]

    with patch(
        "app.api.admin.metadata_service.get_interviews", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_interviews

        response = await admin_api.list_interviews(job_id=job_id)

        mock_get.assert_called_once_with(job_id=job_id)
        assert len(response.interviews) == 1
        assert response.interviews[0].title == "Tech Screen"
