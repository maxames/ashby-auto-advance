"""Unit tests for advancement service."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.services.advancement import (
    evaluate_schedule_for_advancement,
    execute_advancement,
    get_schedules_ready_for_evaluation,
)
from tests.fixtures.factories import (
    create_test_feedback,
    create_test_rule,
    create_test_schedule,
)


class TestGetSchedulesReadyForEvaluation:
    """Tests for get_schedules_ready_for_evaluation function."""

    @pytest.mark.asyncio
    async def test_filters_by_status(self, clean_db):
        """Test only includes WaitingOnFeedback and Complete statuses."""
        # Create schedules with different statuses
        await create_test_schedule(clean_db, status="Complete")
        await create_test_schedule(clean_db, status="WaitingOnFeedback")
        await create_test_schedule(clean_db, status="Scheduled")
        await create_test_schedule(clean_db, status="Cancelled")

        schedules = await get_schedules_ready_for_evaluation()

        assert len(schedules) == 2
        statuses = {s["status"] for s in schedules}
        assert statuses == {"Complete", "WaitingOnFeedback"}

    @pytest.mark.asyncio
    async def test_respects_last_evaluated_at_timestamp(self, clean_db):
        """Test includes schedules not yet evaluated or updated since last evaluation."""
        plan_id = str(uuid4())
        stage_id = str(uuid4())

        # Schedule 1: Never evaluated
        await create_test_schedule(
            clean_db,
            status="Complete",
            interview_plan_id=plan_id,
            interview_stage_id=stage_id,
        )

        # Schedule 2: Evaluated but updated since then
        schedule2 = await create_test_schedule(
            clean_db,
            status="Complete",
            interview_plan_id=plan_id,
            interview_stage_id=stage_id,
        )

        async with clean_db.acquire() as conn:
            # Set last_evaluated to 1 hour ago, updated to now
            await conn.execute(
                """
                UPDATE interview_schedules
                SET last_evaluated_for_advancement_at = NOW() - INTERVAL '1 hour',
                    updated_at = NOW()
                WHERE schedule_id = $1
                """,
                uuid4(schedule2["schedule_id"]),
            )

        # Schedule 3: Evaluated and NOT updated since
        schedule3 = await create_test_schedule(
            clean_db,
            status="Complete",
            interview_plan_id=plan_id,
            interview_stage_id=stage_id,
        )

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET last_evaluated_for_advancement_at = NOW(),
                    updated_at = NOW() - INTERVAL '1 hour'
                WHERE schedule_id = $1
                """,
                uuid4(schedule3["schedule_id"]),
            )

        schedules = await get_schedules_ready_for_evaluation()

        # Should get schedules 1 and 2, not 3
        assert len(schedules) == 2

    @pytest.mark.asyncio
    async def test_timeout_window_filtering(self, clean_db):
        """Test filters out schedules older than timeout window."""
        from app.core.config import settings

        plan_id = str(uuid4())
        stage_id = str(uuid4())

        # Recent schedule (within timeout)
        await create_test_schedule(
            clean_db,
            status="Complete",
            interview_plan_id=plan_id,
            interview_stage_id=stage_id,
        )

        # Old schedule (beyond timeout)
        old_schedule = await create_test_schedule(
            clean_db,
            status="Complete",
            interview_plan_id=plan_id,
            interview_stage_id=stage_id,
        )

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET updated_at = NOW() - INTERVAL '30 days'
                WHERE schedule_id = $1
                """,
                uuid4(old_schedule["schedule_id"]),
            )

        schedules = await get_schedules_ready_for_evaluation()

        # Should only get recent schedule
        assert len(schedules) == 1


class TestEvaluateScheduleForAdvancement:
    """Tests for evaluate_schedule_for_advancement function."""

    @pytest.mark.asyncio
    async def test_ready_for_advancement_returns_ready_true(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test returns ready=True when all criteria met."""
        # Create rule
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="3",
        )

        # Update schedule with plan and stage
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2, status = 'Complete'
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create passing feedback (submitted > 30 mins ago)
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        result = await evaluate_schedule_for_advancement(schedule_id)

        assert result["ready"] is True
        assert "rule_id" in result
        assert "target_stage_id" in result

    @pytest.mark.asyncio
    async def test_no_matching_rule_returns_blocking_reason(self, clean_db):
        """Test returns blocking_reason when no rule matches."""
        schedule = await create_test_schedule(clean_db, status="Complete")

        result = await evaluate_schedule_for_advancement(schedule["schedule_id"])

        assert result["ready"] is False
        assert result["blocking_reason"] == "no_rule"

    @pytest.mark.asyncio
    async def test_feedback_too_recent_blocks(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test returns too_recent when feedback submitted < 30 mins ago."""
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
        )

        # Update schedule
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2, status = 'Complete'
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create recent feedback (< 30 mins)
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        result = await evaluate_schedule_for_advancement(schedule_id)

        assert result["ready"] is False
        assert result["blocking_reason"] == "too_recent"

    @pytest.mark.asyncio
    async def test_requirements_not_met_blocks(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test returns requirements_not_met when scores don't pass."""
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="4",  # High threshold
        )

        # Update schedule
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2, status = 'Complete'
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create feedback that fails threshold
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 2},  # Below threshold
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        result = await evaluate_schedule_for_advancement(schedule_id)

        assert result["ready"] is False
        assert result["blocking_reason"] == "requirements_not_met"


class TestExecuteAdvancement:
    """Tests for execute_advancement function."""

    @pytest.mark.asyncio
    async def test_dry_run_mode_doesnt_call_api(self, clean_db, monkeypatch):
        """Test dry_run mode logs but doesn't call Ashby API."""
        from unittest.mock import AsyncMock

        schedule = await create_test_schedule(clean_db)
        rule = await create_test_rule(clean_db)

        # Mock advance_candidate_stage
        mock_advance = AsyncMock()
        from app.clients import ashby

        monkeypatch.setattr(ashby, "advance_candidate_stage", mock_advance)

        # Execute in dry-run mode
        result = await execute_advancement(
            schedule_id=schedule["schedule_id"],
            application_id=schedule["application_id"],
            rule_id=rule["rule_id"],
            target_stage_id=rule["target_stage_id"],
            from_stage_id=schedule["interview_stage_id"],
            evaluation_results={},
            dry_run=True,
        )

        assert result["success"] is True
        # API should NOT have been called
        mock_advance.assert_not_called()

        # Check audit record
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                uuid4(schedule["schedule_id"]),
            )
            assert execution is not None
            assert execution["execution_status"] == "dry_run"

    @pytest.mark.asyncio
    async def test_successful_advancement_updates_database(self, clean_db, monkeypatch):
        """Test successful advancement updates all necessary records."""
        from unittest.mock import AsyncMock

        schedule = await create_test_schedule(clean_db)
        rule = await create_test_rule(clean_db)

        # Mock API call
        mock_advance = AsyncMock(return_value={"id": schedule["application_id"]})
        from app.clients import ashby

        monkeypatch.setattr(ashby, "advance_candidate_stage", mock_advance)

        # Execute
        result = await execute_advancement(
            schedule_id=schedule["schedule_id"],
            application_id=schedule["application_id"],
            rule_id=rule["rule_id"],
            target_stage_id=rule["target_stage_id"],
            from_stage_id=schedule["interview_stage_id"],
            evaluation_results={},
            dry_run=False,
        )

        assert result["success"] is True

        # Check audit record
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                uuid4(schedule["schedule_id"]),
            )
            assert execution is not None
            assert execution["execution_status"] == "success"
            assert str(execution["to_stage_id"]) == rule["target_stage_id"]

    @pytest.mark.asyncio
    async def test_failure_records_error_in_audit_table(self, clean_db, monkeypatch):
        """Test API failure is recorded in audit table."""
        from unittest.mock import AsyncMock

        schedule = await create_test_schedule(clean_db)
        rule = await create_test_rule(clean_db)

        # Mock API to raise exception
        mock_advance = AsyncMock(side_effect=Exception("API Error"))
        from app.clients import ashby

        monkeypatch.setattr(ashby, "advance_candidate_stage", mock_advance)

        # Execute - should handle error gracefully
        result = await execute_advancement(
            schedule_id=schedule["schedule_id"],
            application_id=schedule["application_id"],
            rule_id=rule["rule_id"],
            target_stage_id=rule["target_stage_id"],
            from_stage_id=schedule["interview_stage_id"],
            evaluation_results={},
            dry_run=False,
        )

        assert result["success"] is False

        # Check error recorded
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                uuid4(schedule["schedule_id"]),
            )
            assert execution is not None
            assert execution["execution_status"] == "failed"
            assert "API Error" in execution["failure_reason"]

    @pytest.mark.asyncio
    async def test_marks_feedback_as_processed(
        self, clean_db, sample_interview_event, monkeypatch
    ):
        """Test marks feedback as processed after advancement."""
        from unittest.mock import AsyncMock

        schedule = await create_test_schedule(clean_db)
        rule = await create_test_rule(clean_db)

        # Create feedback
        feedback = await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=rule["interview_id"],
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Mock API
        mock_advance = AsyncMock(return_value={"id": schedule["application_id"]})
        from app.clients import ashby

        monkeypatch.setattr(ashby, "advance_candidate_stage", mock_advance)

        # Link event to schedule
        async with clean_db.acquire() as conn:
            await conn.execute(
                "UPDATE interview_events SET schedule_id = $1 WHERE event_id = $2",
                uuid4(schedule["schedule_id"]),
                uuid4(sample_interview_event["event_id"]),
            )

        # Execute
        await execute_advancement(
            schedule_id=schedule["schedule_id"],
            application_id=schedule["application_id"],
            rule_id=rule["rule_id"],
            target_stage_id=rule["target_stage_id"],
            from_stage_id=schedule["interview_stage_id"],
            evaluation_results={},
            dry_run=False,
        )

        # Check feedback marked as processed
        async with clean_db.acquire() as conn:
            feedback_record = await conn.fetchrow(
                "SELECT * FROM feedback_submissions WHERE feedback_id = $1",
                uuid4(feedback["feedback_id"]),
            )
            assert feedback_record is not None
            assert feedback_record["processed_for_advancement_at"] is not None
