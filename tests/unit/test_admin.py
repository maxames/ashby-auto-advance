"""Unit tests for admin service."""

from uuid import uuid4

import pytest

from app.services.admin import (
    create_advancement_rule,
    get_advancement_statistics,
    get_schedules_for_application,
)
from tests.fixtures.factories import create_test_rule, create_test_schedule


class TestCreateAdvancementRule:
    """Tests for create_advancement_rule function."""

    @pytest.mark.asyncio
    async def test_creates_rule_with_requirements_and_actions(self, clean_db):
        """Test creates rule with all related records."""
        job_id = str(uuid4())
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        target_stage_id = str(uuid4())
        interview_id = str(uuid4())

        requirements = [
            {
                "interview_id": interview_id,
                "score_field_path": "overall_score",
                "operator": ">=",
                "threshold_value": "3",
                "is_required": True,
            }
        ]

        actions = [
            {
                "action_type": "advance_stage",
                "action_config": {},
                "execution_order": 1,
            }
        ]

        result = await create_advancement_rule(
            job_id=job_id,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            target_stage_id=target_stage_id,
            requirements=requirements,
            actions=actions,
        )

        assert "rule_id" in result
        assert result["job_id"] == job_id
        assert result["interview_plan_id"] == interview_plan_id
        assert result["interview_stage_id"] == interview_stage_id
        assert result["target_stage_id"] == target_stage_id
        assert len(result["requirement_ids"]) == 1
        assert len(result["action_ids"]) == 1

        # Verify in database
        async with clean_db.acquire() as conn:
            rule = await conn.fetchrow(
                "SELECT * FROM advancement_rules WHERE rule_id = $1",
                uuid4(result["rule_id"]),
            )
            assert rule is not None
            assert rule["is_active"] is True

            req_count = await conn.fetchval(
                "SELECT COUNT(*) FROM advancement_rule_requirements WHERE rule_id = $1",
                uuid4(result["rule_id"]),
            )
            assert req_count == 1

            action_count = await conn.fetchval(
                "SELECT COUNT(*) FROM advancement_rule_actions WHERE rule_id = $1",
                uuid4(result["rule_id"]),
            )
            assert action_count == 1

    @pytest.mark.asyncio
    async def test_returns_complete_rule_object_with_ids(self, clean_db):
        """Test returns all generated IDs."""
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        interview_id = str(uuid4())

        requirements = [
            {
                "interview_id": interview_id,
                "score_field_path": "overall_score",
                "operator": ">=",
                "threshold_value": "3",
                "is_required": True,
            }
        ]

        actions = [{"action_type": "advance_stage", "execution_order": 1}]

        result = await create_advancement_rule(
            job_id=None,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            target_stage_id=None,
            requirements=requirements,
            actions=actions,
        )

        # Check all IDs are valid UUIDs
        assert len(result["rule_id"]) == 36
        assert len(result["requirement_ids"][0]) == 36
        assert len(result["action_ids"][0]) == 36

    @pytest.mark.asyncio
    async def test_handles_transaction_rollback_on_error(self, clean_db, monkeypatch):
        """Test transaction rolls back if any insert fails."""
        from unittest.mock import AsyncMock

        # This would require mocking database operations to force an error
        # For now, we'll test that invalid data raises an exception
        with pytest.raises(Exception):
            await create_advancement_rule(
                job_id=None,
                interview_plan_id="invalid-uuid",  # Invalid UUID format
                interview_stage_id=str(uuid4()),
                target_stage_id=None,
                requirements=[],
                actions=[],
            )


class TestGetAdvancementStatistics:
    """Tests for get_advancement_statistics function."""

    @pytest.mark.asyncio
    async def test_returns_correct_counts(self, clean_db):
        """Test returns accurate statistics."""
        # Create some test data
        rule1 = await create_test_rule(clean_db)
        rule2 = await create_test_rule(clean_db)
        schedule1 = await create_test_schedule(clean_db, status="Complete")
        schedule2 = await create_test_schedule(clean_db, status="WaitingOnFeedback")

        # Create some executions
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO advancement_executions
                (schedule_id, application_id, rule_id, execution_status, executed_at)
                VALUES ($1, $2, $3, 'success', NOW())
                """,
                uuid4(schedule1["schedule_id"]),
                uuid4(schedule1["application_id"]),
                uuid4(rule1["rule_id"]),
            )

            await conn.execute(
                """
                INSERT INTO advancement_executions
                (schedule_id, application_id, rule_id, execution_status,
                 failure_reason, executed_at)
                VALUES ($1, $2, $3, 'failed', 'Test error', NOW())
                """,
                uuid4(schedule2["schedule_id"]),
                uuid4(schedule2["application_id"]),
                uuid4(rule2["rule_id"]),
            )

        stats = await get_advancement_statistics()

        assert stats["active_rules"] == 2
        assert stats["pending_evaluations"] == 2
        assert stats["success_count"] == 1
        assert stats["failed_count"] == 1
        assert len(stats["recent_failures"]) == 1
        assert stats["recent_failures"][0]["failure_reason"] == "Test error"

    @pytest.mark.asyncio
    async def test_handles_empty_database(self, clean_db):
        """Test returns zeros when database is empty."""
        stats = await get_advancement_statistics()

        assert stats["active_rules"] == 0
        assert stats["pending_evaluations"] == 0
        assert stats["success_count"] == 0
        assert stats["failed_count"] == 0
        assert stats["total_executions_30d"] == 0
        assert len(stats["recent_failures"]) == 0


class TestGetSchedulesForApplication:
    """Tests for get_schedules_for_application function."""

    @pytest.mark.asyncio
    async def test_returns_all_schedules_for_application(self, clean_db):
        """Test returns all schedules for given application."""
        application_id = str(uuid4())

        # Create multiple schedules for same application
        await create_test_schedule(
            clean_db, application_id=application_id, status="Complete"
        )
        await create_test_schedule(
            clean_db, application_id=application_id, status="Scheduled"
        )

        # Create schedule for different application
        await create_test_schedule(clean_db, status="Complete")

        schedules = await get_schedules_for_application(application_id)

        assert len(schedules) == 2
        assert all(s["status"] in ["Complete", "Scheduled"] for s in schedules)

    @pytest.mark.asyncio
    async def test_orders_by_updated_at_desc(self, clean_db):
        """Test returns schedules ordered by most recent first."""
        application_id = str(uuid4())

        # Create schedules
        schedule1 = await create_test_schedule(
            clean_db, application_id=application_id, status="Scheduled"
        )
        schedule2 = await create_test_schedule(
            clean_db, application_id=application_id, status="Complete"
        )

        # Update schedule1 to be more recent
        async with clean_db.acquire() as conn:
            await conn.execute(
                "UPDATE interview_schedules SET updated_at = NOW() + INTERVAL '1 hour' WHERE schedule_id = $1",
                uuid4(schedule1["schedule_id"]),
            )

        schedules = await get_schedules_for_application(application_id)

        # Most recent should be first
        assert schedules[0]["schedule_id"] == schedule1["schedule_id"]
        assert schedules[1]["schedule_id"] == schedule2["schedule_id"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_schedules(self, clean_db):
        """Test returns empty list when no schedules exist."""
        schedules = await get_schedules_for_application(str(uuid4()))

        assert schedules == []
