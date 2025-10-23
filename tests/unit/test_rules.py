"""Unit tests for rules evaluation engine."""

from uuid import uuid4

import pytest

from app.services.rules import (
    evaluate_rule_requirements,
    find_matching_rule,
    get_target_stage_for_rule,
)
from tests.fixtures.factories import create_test_feedback, create_test_rule


class TestFindMatchingRule:
    """Tests for find_matching_rule function."""

    @pytest.mark.asyncio
    async def test_finds_rule_with_null_job_id(self, clean_db):
        """Test finding rule with job_id NULL (applies to all jobs)."""
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        interview_id = str(uuid4())

        # Create rule with job_id NULL
        rule_data = await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=interview_id,
            job_id=None,
        )

        # Find with any job_id (or None)
        result = await find_matching_rule(
            job_id=str(uuid4()),
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        assert result is not None
        assert result["rule_id"] == rule_data["rule_id"]
        assert result["interview_plan_id"] == interview_plan_id
        assert result["interview_stage_id"] == interview_stage_id

    @pytest.mark.asyncio
    async def test_prefers_job_specific_rule_over_generic(self, clean_db):
        """Test that job-specific rules take precedence over generic rules."""
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        interview_id = str(uuid4())
        job_id = str(uuid4())

        # Create generic rule (job_id NULL)
        await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=interview_id,
            job_id=None,
        )

        # Create job-specific rule
        specific_rule = await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=interview_id,
            job_id=job_id,
        )

        # Find - should return job-specific rule
        result = await find_matching_rule(
            job_id=job_id,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        assert result is not None
        assert result["rule_id"] == specific_rule["rule_id"]
        assert result["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, clean_db):
        """Test returns None when no matching rule exists."""
        result = await find_matching_rule(
            job_id=str(uuid4()),
            interview_plan_id=str(uuid4()),
            interview_stage_id=str(uuid4()),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ignores_inactive_rules(self, clean_db):
        """Test that inactive rules are not returned."""
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        interview_id = str(uuid4())

        # Create rule then deactivate it
        rule_data = await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=interview_id,
        )

        async with clean_db.acquire() as conn:
            await conn.execute(
                "UPDATE advancement_rules SET is_active = false WHERE rule_id = $1",
                uuid4(rule_data["rule_id"]),
            )

        # Should not find the inactive rule
        result = await find_matching_rule(
            job_id=None,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        assert result is None


class TestEvaluateRuleRequirements:
    """Tests for evaluate_rule_requirements function."""

    @pytest.mark.asyncio
    async def test_all_requirements_pass(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test when all requirements are met."""
        # Create rule matching the interview
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            score_field="overall_score",
            operator=">=",
            threshold="3",
        )

        # Create schedule with matching plan/stage
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create feedback that passes threshold
        feedback = await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
        )

        # Evaluate
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule_id,
            feedback_submissions=[
                {
                    **feedback,
                    "event_id": uuid4(feedback["event_id"]),
                    "interview_id": uuid4(feedback["interview_id"]),
                }
            ],
        )

        assert result["all_passed"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["passed"] is True

    @pytest.mark.asyncio
    async def test_required_interview_not_scheduled_blocks(self, clean_db):
        """Test that missing required interview blocks advancement."""
        interview_id = str(uuid4())
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())

        # Create rule requiring an interview
        rule_data = await create_test_rule(
            clean_db,
            interview_id=interview_id,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        # Create schedule with no events
        from tests.fixtures.factories import create_test_schedule

        schedule = await create_test_schedule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        # Evaluate - should block
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule["schedule_id"],
            feedback_submissions=[],
        )

        assert result["all_passed"] is False
        assert len(result["results"]) == 1
        assert result["results"][0]["passed"] is False
        assert (
            result["results"][0]["blocking_reason"]
            == "required_interview_not_scheduled"
        )

    @pytest.mark.asyncio
    async def test_optional_interview_not_scheduled_skips(self, clean_db):
        """Test that optional interview not scheduled doesn't block."""
        interview_id = str(uuid4())
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())

        # Create rule with optional interview
        rule_data = await create_test_rule(
            clean_db,
            interview_id=interview_id,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        # Mark requirement as optional
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE advancement_rule_requirements
                SET is_required = false
                WHERE requirement_id = $1
                """,
                uuid4(rule_data["requirement_id"]),
            )

        # Create schedule with no events
        from tests.fixtures.factories import create_test_schedule

        schedule = await create_test_schedule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
        )

        # Evaluate - should pass (skip optional)
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule["schedule_id"],
            feedback_submissions=[],
        )

        assert result["all_passed"] is True
        assert result["results"][0]["passed"] is True
        assert result["results"][0].get("note") == "optional_interview_not_scheduled"

    @pytest.mark.asyncio
    async def test_multiple_interviewers_all_must_submit(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test that all interviewers must submit feedback."""
        # Create rule
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
                SET interview_plan_id = $1, interview_stage_id = $2
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

            # Add second interviewer to same event
            interviewer2_id = uuid4()
            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Second', 'Interviewer', 'second@example.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                uuid4(sample_interview_event["event_id"]),
                interviewer2_id,
                uuid4(),
            )

        # Only one feedback submitted
        feedback = await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
        )

        # Evaluate - should fail (missing feedback from second interviewer)
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule_id,
            feedback_submissions=[
                {
                    **feedback,
                    "event_id": uuid4(feedback["event_id"]),
                    "interview_id": uuid4(feedback["interview_id"]),
                }
            ],
        )

        assert result["all_passed"] is False

    @pytest.mark.asyncio
    async def test_single_interviewer_fails_threshold_blocks(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test that failing threshold blocks advancement."""
        # Create rule requiring score >= 3
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="3",
        )

        # Update schedule
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create feedback with score below threshold
        feedback = await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 2},  # Below threshold
        )

        # Evaluate
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule_id,
            feedback_submissions=[
                {
                    **feedback,
                    "event_id": uuid4(feedback["event_id"]),
                    "interview_id": uuid4(feedback["interview_id"]),
                }
            ],
        )

        assert result["all_passed"] is False
        assert result["results"][0]["passed"] is False

    @pytest.mark.asyncio
    async def test_missing_score_field_blocks(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test that missing score field blocks advancement."""
        # Create rule
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            score_field="technical_skills",  # Different field
        )

        # Update schedule
        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1, interview_stage_id = $2
                WHERE schedule_id = $3
                """,
                uuid4(rule_data["interview_plan_id"]),
                uuid4(rule_data["interview_stage_id"]),
                uuid4(schedule_id),
            )

        # Create feedback without the required field
        feedback = await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},  # Missing technical_skills
        )

        # Evaluate
        result = await evaluate_rule_requirements(
            rule_id=rule_data["rule_id"],
            schedule_id=schedule_id,
            feedback_submissions=[
                {
                    **feedback,
                    "event_id": uuid4(feedback["event_id"]),
                    "interview_id": uuid4(feedback["interview_id"]),
                }
            ],
        )

        assert result["all_passed"] is False

    @pytest.mark.asyncio
    async def test_different_operators(
        self, clean_db, sample_interview, sample_interview_event
    ):
        """Test different comparison operators work correctly."""
        operators_and_values = [
            (">=", "3", 3, True),  # Equal to threshold
            (">=", "3", 4, True),  # Above threshold
            (">=", "3", 2, False),  # Below threshold
            (">", "3", 4, True),  # Above
            (">", "3", 3, False),  # Equal (fails for >)
            ("==", "3", 3, True),  # Exact match
            ("==", "3", 4, False),  # Not exact
            ("<=", "3", 2, True),  # Below
            ("<", "3", 2, True),  # Strictly below
        ]

        for operator, threshold, score_value, should_pass in operators_and_values:
            # Clean up from previous iteration
            async with clean_db.acquire() as conn:
                await conn.execute("DELETE FROM advancement_rule_requirements")
                await conn.execute("DELETE FROM advancement_rules")
                await conn.execute("DELETE FROM feedback_submissions")

            # Create rule with specific operator
            rule_data = await create_test_rule(
                clean_db,
                interview_id=sample_interview["interview_id"],
                operator=operator,
                threshold=threshold,
            )

            # Update schedule
            schedule_id = sample_interview_event["schedule_id"]
            async with clean_db.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE interview_schedules
                    SET interview_plan_id = $1, interview_stage_id = $2
                    WHERE schedule_id = $3
                    """,
                    uuid4(rule_data["interview_plan_id"]),
                    uuid4(rule_data["interview_stage_id"]),
                    uuid4(schedule_id),
                )

            # Create feedback
            feedback = await create_test_feedback(
                clean_db,
                event_id=sample_interview_event["event_id"],
                application_id=sample_interview_event["application_id"],
                interviewer_id=sample_interview_event["interviewer_id"],
                interview_id=sample_interview["interview_id"],
                submitted_values={"overall_score": score_value},
            )

            # Evaluate
            result = await evaluate_rule_requirements(
                rule_id=rule_data["rule_id"],
                schedule_id=schedule_id,
                feedback_submissions=[
                    {
                        **feedback,
                        "event_id": uuid4(feedback["event_id"]),
                        "interview_id": uuid4(feedback["interview_id"]),
                    }
                ],
            )

            assert (
                result["all_passed"] is should_pass
            ), f"Operator {operator} with threshold {threshold} and value {score_value} should {'pass' if should_pass else 'fail'}"


class TestGetTargetStageForRule:
    """Tests for get_target_stage_for_rule function."""

    @pytest.mark.asyncio
    async def test_explicit_target_stage_returns_it(self, clean_db):
        """Test that explicit target_stage_id is returned."""
        target_stage_id = str(uuid4())

        rule_data = await create_test_rule(
            clean_db,
            target_stage_id=target_stage_id,
        )

        result = await get_target_stage_for_rule(
            rule_id=rule_data["rule_id"],
            current_stage_id=rule_data["interview_stage_id"],
            interview_plan_id=rule_data["interview_plan_id"],
        )

        assert result == target_stage_id

    @pytest.mark.asyncio
    async def test_null_target_calculates_next_sequential(self, clean_db, monkeypatch):
        """Test that NULL target_stage_id calculates next sequential stage."""
        from unittest.mock import AsyncMock

        # Create rule with NULL target
        rule_data = await create_test_rule(
            clean_db,
            target_stage_id=None,
        )

        # Update rule to have NULL target
        async with clean_db.acquire() as conn:
            await conn.execute(
                "UPDATE advancement_rules SET target_stage_id = NULL WHERE rule_id = $1",
                uuid4(rule_data["rule_id"]),
            )

        # Mock list_interview_stages_for_plan to return sequential stages
        current_stage_id = str(uuid4())
        next_stage_id = str(uuid4())

        mock_stages = [
            {"id": current_stage_id, "orderInInterviewPlan": 1},
            {"id": next_stage_id, "orderInInterviewPlan": 2},
        ]

        from app.clients import ashby

        monkeypatch.setattr(
            ashby,
            "list_interview_stages_for_plan",
            AsyncMock(return_value=mock_stages),
        )

        result = await get_target_stage_for_rule(
            rule_id=rule_data["rule_id"],
            current_stage_id=current_stage_id,
            interview_plan_id=rule_data["interview_plan_id"],
        )

        assert result == next_stage_id

    @pytest.mark.asyncio
    async def test_error_when_next_stage_doesnt_exist(self, clean_db, monkeypatch):
        """Test raises error when next stage doesn't exist."""
        from unittest.mock import AsyncMock

        rule_data = await create_test_rule(
            clean_db,
            target_stage_id=None,
        )

        # Update to NULL target
        async with clean_db.acquire() as conn:
            await conn.execute(
                "UPDATE advancement_rules SET target_stage_id = NULL WHERE rule_id = $1",
                uuid4(rule_data["rule_id"]),
            )

        # Mock - current stage is last (no next stage)
        current_stage_id = str(uuid4())
        mock_stages = [
            {"id": current_stage_id, "orderInInterviewPlan": 3},
        ]

        from app.clients import ashby

        monkeypatch.setattr(
            ashby,
            "list_interview_stages_for_plan",
            AsyncMock(return_value=mock_stages),
        )

        with pytest.raises(ValueError, match="No next stage found"):
            await get_target_stage_for_rule(
                rule_id=rule_data["rule_id"],
                current_stage_id=current_stage_id,
                interview_plan_id=rule_data["interview_plan_id"],
            )
