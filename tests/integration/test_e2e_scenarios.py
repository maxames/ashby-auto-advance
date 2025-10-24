"""Comprehensive E2E scenarios for advancement workflows."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.advancement import process_advancement_evaluations
from tests.fixtures.factories import (
    create_test_feedback,
    create_test_rule,
    create_test_schedule,
)


class TestPanelInterviewScenarios:
    """Test scenarios with multiple interviewers (panel interviews)."""

    @pytest.mark.asyncio
    async def test_panel_interview_all_pass_advances(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Panel: 3 interviewers all pass (score >= 3) → should advance."""
        # Setup: Create rule requiring score >= 3
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="3",
        )

        # Setup: Create schedule with 3 interviewers
        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        # Create 3 interviewers (need events for each)
        async with clean_db.acquire() as conn:
            event_id = uuid4()
            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

            # Add 3 interviewers to the event
            interviewer_ids = [uuid4() for _ in range(3)]
            for idx, interviewer_id in enumerate(interviewer_ids):
                await conn.execute(
                    """
                    INSERT INTO interview_assignments
                    (event_id, interviewer_id, first_name, last_name, email,
                     global_role, training_role, is_enabled, interviewer_pool_id,
                     interviewer_pool_title, interviewer_pool_is_archived,
                     training_path, interviewer_updated_at)
                    VALUES ($1, $2, $3, $4, $5, 'Interviewer', 'Trained', true,
                            $6, 'Test Pool', false, '{}', NOW())
                    """,
                    event_id,
                    interviewer_id,
                    f"Interviewer_{idx}",
                    f"LastName_{idx}",
                    f"interviewer{idx}@test.com",
                    uuid4(),
                )

                # All 3 submit passing feedback (score = 4)
                await create_test_feedback(
                    clean_db,
                    event_id=str(event_id),
                    application_id=schedule_data["application_id"],
                    interviewer_id=str(interviewer_id),
                    interview_id=sample_interview["interview_id"],
                    submitted_values={"overall_score": 4},
                    submitted_at=datetime.now(UTC) - timedelta(hours=1),
                )

        # Mock advancement API
        mock_advance = AsyncMock(return_value={"id": schedule_data["application_id"]})
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # Execute: Run evaluation
        await process_advancement_evaluations()

        # Verify advancement occurred exactly once
        mock_advance.assert_called_once()

        # Verify audit trail
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                schedule_data["schedule_id"],
            )
            assert execution is not None
            assert execution["execution_status"] == "success"

    @pytest.mark.asyncio
    async def test_panel_interview_one_fails_blocks(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Panel: 2 pass, 1 fails → should send rejection notification."""
        # Setup: Create rule requiring score >= 3
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="3",
        )

        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        # Create event with 3 interviewers
        async with clean_db.acquire() as conn:
            event_id = uuid4()
            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

            interviewer_ids = [uuid4() for _ in range(3)]
            for idx, interviewer_id in enumerate(interviewer_ids):
                await conn.execute(
                    """
                    INSERT INTO interview_assignments
                    (event_id, interviewer_id, first_name, last_name, email,
                     global_role, training_role, is_enabled, interviewer_pool_id,
                     interviewer_pool_title, interviewer_pool_is_archived,
                     training_path, interviewer_updated_at)
                    VALUES ($1, $2, $3, $4, $5, 'Interviewer', 'Trained', true,
                            $6, 'Test Pool', false, '{}', NOW())
                    """,
                    event_id,
                    interviewer_id,
                    f"Interviewer_{idx}",
                    f"LastName_{idx}",
                    f"interviewer{idx}@test.com",
                    uuid4(),
                )

                # 2 pass (score = 4), 1 fails (score = 2)
                score = 2 if idx == 2 else 4
                await create_test_feedback(
                    clean_db,
                    event_id=str(event_id),
                    application_id=schedule_data["application_id"],
                    interviewer_id=str(interviewer_id),
                    interview_id=sample_interview["interview_id"],
                    submitted_values={"overall_score": score},
                    submitted_at=datetime.now(UTC) - timedelta(hours=1),
                )

        # Mock APIs
        mock_advance = AsyncMock()
        mock_slack = AsyncMock()
        mock_fetch_candidate = AsyncMock(
            return_value={"id": "candidate_id", "name": "Test Candidate"}
        )

        from app.clients import ashby, slack
        from app.core.config import settings
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(slack.slack_client, "chat_postMessage", mock_slack)
        monkeypatch.setattr(ashby, "fetch_candidate_info", mock_fetch_candidate)
        monkeypatch.setattr(settings, "admin_slack_channel_id", "C123456")

        # Execute: Run evaluation
        await process_advancement_evaluations()

        # Assert: Should NOT advance (one failed)
        mock_advance.assert_not_called()

        # Verify schedule was evaluated
        async with clean_db.acquire() as conn:
            schedule = await conn.fetchrow(
                """
                SELECT last_evaluated_for_advancement_at
                FROM interview_schedules WHERE schedule_id = $1
                """,
                schedule_data["schedule_id"],
            )
            assert schedule["last_evaluated_for_advancement_at"] is not None


class TestSequentialInterviewScenarios:
    """Test scenarios with sequential interviews (multiple interview types)."""

    @pytest.mark.asyncio
    async def test_sequential_interviews_both_pass(self, clean_db, monkeypatch):
        """Sequential: Tech interview → Culture interview, both pass → advance."""
        # Create two interview definitions
        tech_interview_id = uuid4()
        culture_interview_id = uuid4()

        async with clean_db.acquire() as conn:
            for interview_id, title in [
                (tech_interview_id, "Technical Interview"),
                (culture_interview_id, "Culture Fit Interview"),
            ]:
                await conn.execute(
                    """
                    INSERT INTO interviews
                    (interview_id, title, feedback_form_definition_id, is_archived, updated_at)
                    VALUES ($1, $2, $3, false, NOW())
                    """,
                    interview_id,
                    title,
                    uuid4(),
                )

        # Create ONE rule with TWO requirements (both interviews must pass)
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        target_stage_id = str(uuid4())
        rule_id = uuid4()

        async with clean_db.acquire() as conn:
            # Create rule
            await conn.execute(
                """
                INSERT INTO advancement_rules
                (rule_id, job_id, interview_plan_id, interview_stage_id,
                 target_stage_id, is_active, created_at, updated_at)
                VALUES ($1, NULL, $2, $3, $4, true, NOW(), NOW())
                """,
                rule_id,
                interview_plan_id,
                interview_stage_id,
                target_stage_id,
            )

            # Add requirement 1: Tech interview
            await conn.execute(
                """
                INSERT INTO advancement_rule_requirements
                (requirement_id, rule_id, interview_id, score_field_path,
                 operator, threshold_value, is_required, created_at)
                VALUES ($1, $2, $3, 'overall_score', '>=', '3', true, NOW())
                """,
                uuid4(),
                rule_id,
                tech_interview_id,
            )

            # Add requirement 2: Culture interview
            await conn.execute(
                """
                INSERT INTO advancement_rule_requirements
                (requirement_id, rule_id, interview_id, score_field_path,
                 operator, threshold_value, is_required, created_at)
                VALUES ($1, $2, $3, 'overall_score', '>=', '3', true, NOW())
                """,
                uuid4(),
                rule_id,
                culture_interview_id,
            )

            # Add action
            await conn.execute(
                """
                INSERT INTO advancement_rule_actions
                (action_id, rule_id, action_type, action_config, execution_order, created_at)
                VALUES ($1, $2, 'advance_stage', '{}', 1, NOW())
                """,
                uuid4(),
                rule_id,
            )

        # Create schedule
        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            status="Complete",
        )

        # Create events for both interviews
        async with clean_db.acquire() as conn:
            for interview_id in [tech_interview_id, culture_interview_id]:
                event_id = uuid4()
                interviewer_id = uuid4()

                await conn.execute(
                    """
                    INSERT INTO interview_events
                    (event_id, schedule_id, interview_id, start_time, end_time,
                     feedback_link, location, meeting_link, has_submitted_feedback,
                     created_at, updated_at, extra_data)
                    VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                            'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                            true, NOW(), NOW(), '{}')
                    """,
                    event_id,
                    schedule_data["schedule_id"],
                    interview_id,
                )

                await conn.execute(
                    """
                    INSERT INTO interview_assignments
                    (event_id, interviewer_id, first_name, last_name, email,
                     global_role, training_role, is_enabled, interviewer_pool_id,
                     interviewer_pool_title, interviewer_pool_is_archived,
                     training_path, interviewer_updated_at)
                    VALUES ($1, $2, 'Test', 'Interviewer', 'test@test.com',
                            'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                    """,
                    event_id,
                    interviewer_id,
                    uuid4(),
                )

                # Both pass (score = 4)
                await create_test_feedback(
                    clean_db,
                    event_id=str(event_id),
                    application_id=schedule_data["application_id"],
                    interviewer_id=str(interviewer_id),
                    interview_id=str(interview_id),
                    submitted_values={"overall_score": 4},
                    submitted_at=datetime.now(UTC) - timedelta(hours=1),
                )

        # Mock advancement API
        mock_advance = AsyncMock(return_value={"id": schedule_data["application_id"]})
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # Execute
        await process_advancement_evaluations()

        # Verify advancement occurred exactly once
        mock_advance.assert_called_once()

    @pytest.mark.asyncio
    async def test_sequential_interviews_second_fails(self, clean_db, monkeypatch):
        """Sequential: Tech passes, Culture fails → rejection."""
        # Similar setup to above but culture interview fails
        tech_interview_id = uuid4()
        culture_interview_id = uuid4()

        async with clean_db.acquire() as conn:
            for interview_id, title in [
                (tech_interview_id, "Technical Interview"),
                (culture_interview_id, "Culture Fit Interview"),
            ]:
                await conn.execute(
                    """
                    INSERT INTO interviews
                    (interview_id, title, feedback_form_definition_id, is_archived, updated_at)
                    VALUES ($1, $2, $3, false, NOW())
                    """,
                    interview_id,
                    title,
                    uuid4(),
                )

        # Create ONE rule with TWO requirements (both interviews must pass)
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())
        target_stage_id = str(uuid4())
        rule_id = uuid4()

        async with clean_db.acquire() as conn:
            # Create rule
            await conn.execute(
                """
                INSERT INTO advancement_rules
                (rule_id, job_id, interview_plan_id, interview_stage_id,
                 target_stage_id, is_active, created_at, updated_at)
                VALUES ($1, NULL, $2, $3, $4, true, NOW(), NOW())
                """,
                rule_id,
                interview_plan_id,
                interview_stage_id,
                target_stage_id,
            )

            # Add requirement 1: Tech interview
            await conn.execute(
                """
                INSERT INTO advancement_rule_requirements
                (requirement_id, rule_id, interview_id, score_field_path,
                 operator, threshold_value, is_required, created_at)
                VALUES ($1, $2, $3, 'overall_score', '>=', '3', true, NOW())
                """,
                uuid4(),
                rule_id,
                tech_interview_id,
            )

            # Add requirement 2: Culture interview
            await conn.execute(
                """
                INSERT INTO advancement_rule_requirements
                (requirement_id, rule_id, interview_id, score_field_path,
                 operator, threshold_value, is_required, created_at)
                VALUES ($1, $2, $3, 'overall_score', '>=', '3', true, NOW())
                """,
                uuid4(),
                rule_id,
                culture_interview_id,
            )

            # Add action
            await conn.execute(
                """
                INSERT INTO advancement_rule_actions
                (action_id, rule_id, action_type, action_config, execution_order, created_at)
                VALUES ($1, $2, 'advance_stage', '{}', 1, NOW())
                """,
                uuid4(),
                rule_id,
            )

        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            for interview_id, score in [
                (tech_interview_id, 4),  # Pass
                (culture_interview_id, 2),  # Fail
            ]:
                event_id = uuid4()
                interviewer_id = uuid4()

                await conn.execute(
                    """
                    INSERT INTO interview_events
                    (event_id, schedule_id, interview_id, start_time, end_time,
                     feedback_link, location, meeting_link, has_submitted_feedback,
                     created_at, updated_at, extra_data)
                    VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                            'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                            true, NOW(), NOW(), '{}')
                    """,
                    event_id,
                    schedule_data["schedule_id"],
                    interview_id,
                )

                await conn.execute(
                    """
                    INSERT INTO interview_assignments
                    (event_id, interviewer_id, first_name, last_name, email,
                     global_role, training_role, is_enabled, interviewer_pool_id,
                     interviewer_pool_title, interviewer_pool_is_archived,
                     training_path, interviewer_updated_at)
                    VALUES ($1, $2, 'Test', 'Interviewer', 'test@test.com',
                            'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                    """,
                    event_id,
                    interviewer_id,
                    uuid4(),
                )

                await create_test_feedback(
                    clean_db,
                    event_id=str(event_id),
                    application_id=schedule_data["application_id"],
                    interviewer_id=str(interviewer_id),
                    interview_id=str(interview_id),
                    submitted_values={"overall_score": score},
                    submitted_at=datetime.now(UTC) - timedelta(hours=1),
                )

        # Mock APIs
        mock_advance = AsyncMock()
        from app.clients import ashby, slack
        from app.core.config import settings
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        mock_slack = AsyncMock()
        mock_fetch_candidate = AsyncMock(
            return_value={"id": "candidate_id", "name": "Test Candidate"}
        )
        monkeypatch.setattr(slack.slack_client, "chat_postMessage", mock_slack)
        monkeypatch.setattr(ashby, "fetch_candidate_info", mock_fetch_candidate)
        monkeypatch.setattr(settings, "admin_slack_channel_id", "C123456")

        # Execute
        await process_advancement_evaluations()

        # Assert: Should NOT advance
        mock_advance.assert_not_called()


class TestEdgeCaseScenarios:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_thirty_minute_wait_window(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Feedback submitted within 30min wait → should not evaluate yet."""
        rule_data = await create_test_rule(
            clean_db, interview_id=sample_interview["interview_id"]
        )

        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            event_id = uuid4()
            interviewer_id = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Test', 'User', 'test@test.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                event_id,
                interviewer_id,
                uuid4(),
            )

        # Submit feedback just 15 minutes ago (within 30min window)
        await create_test_feedback(
            clean_db,
            event_id=str(event_id),
            application_id=schedule_data["application_id"],
            interviewer_id=str(interviewer_id),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(minutes=15),
        )

        mock_advance = AsyncMock()
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # Execute: Run evaluation
        await process_advancement_evaluations()

        # Assert: Should NOT advance yet (too soon)
        mock_advance.assert_not_called()

        # Now update feedback to be 35 minutes old (direct DB update)
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE feedback_submissions
                SET submitted_at = $1
                WHERE event_id = $2 AND interviewer_id = $3
                """,
                datetime.now(UTC) - timedelta(minutes=35),
                event_id,
                interviewer_id,
            )
            # Also update schedule's updated_at to trigger re-evaluation
            await conn.execute(
                """
                UPDATE interview_schedules
                SET updated_at = NOW()
                WHERE schedule_id = $1
                """,
                schedule_data["schedule_id"],
            )

        # Execute again
        await process_advancement_evaluations()

        # Verify advancement occurred exactly once
        mock_advance.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_interview_plan_id_skipped(self, clean_db):
        """Schedule with NULL interview_plan_id → evaluated but no rule matches."""
        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=None,  # NULL - missing advancement fields
            status="Complete",
        )

        # Execute: Run evaluation
        from app.services.advancement import process_advancement_evaluations

        await process_advancement_evaluations()

        # Assert: Schedule was evaluated but no rule matched
        async with clean_db.acquire() as conn:
            schedule = await conn.fetchrow(
                """
                SELECT last_evaluated_for_advancement_at
                FROM interview_schedules WHERE schedule_id = $1
                """,
                schedule_data["schedule_id"],
            )
            # Schedule was evaluated but no rule matched (expected behavior)
            assert schedule["last_evaluated_for_advancement_at"] is not None

    @pytest.mark.asyncio
    async def test_duplicate_feedback_submission_idempotent(
        self, clean_db, sample_interview
    ):
        """Same feedback submitted twice → processed idempotently."""
        schedule_data = await create_test_schedule(clean_db, status="Complete")

        async with clean_db.acquire() as conn:
            event_id = uuid4()
            interviewer_id = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

        feedback_id = uuid4()

        # Submit same feedback twice with same ID
        for _ in range(2):
            async with clean_db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO feedback_submissions
                    (feedback_id, application_id, event_id, interviewer_id, interview_id,
                     submitted_at, submitted_values, processed_for_advancement_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, NOW())
                    ON CONFLICT (feedback_id) DO NOTHING
                    """,
                    feedback_id,
                    schedule_data["application_id"],
                    event_id,
                    interviewer_id,
                    sample_interview["interview_id"],
                    datetime.now(UTC),
                    '{"overall_score": 4}',
                )

        # Assert: Only one record exists
        async with clean_db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_submissions WHERE feedback_id = $1",
                feedback_id,
            )
            assert count == 1

    @pytest.mark.asyncio
    async def test_advancement_with_custom_threshold(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Rule with threshold = 4.5 → only scores >= 4.5 advance."""
        # Create rule with high threshold
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="4.5",  # High threshold
        )

        # Test scenario 1: Score = 4 (should fail)
        schedule_data_fail = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            event_id = uuid4()
            interviewer_id = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data_fail["schedule_id"],
                sample_interview["interview_id"],
            )

            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Test', 'User', 'test@test.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                event_id,
                interviewer_id,
                uuid4(),
            )

        await create_test_feedback(
            clean_db,
            event_id=str(event_id),
            application_id=schedule_data_fail["application_id"],
            interviewer_id=str(interviewer_id),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},  # Fails threshold
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        mock_advance = AsyncMock()
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        await process_advancement_evaluations()

        # Assert: Should NOT advance (score too low)
        mock_advance.assert_not_called()

        # Test scenario 2: Score = 5 (should pass)
        schedule_data_pass = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            event_id2 = uuid4()
            interviewer_id2 = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id2,
                schedule_data_pass["schedule_id"],
                sample_interview["interview_id"],
            )

            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Test', 'User', 'test@test.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                event_id2,
                interviewer_id2,
                uuid4(),
            )

        await create_test_feedback(
            clean_db,
            event_id=str(event_id2),
            application_id=schedule_data_pass["application_id"],
            interviewer_id=str(interviewer_id2),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 5},  # Passes threshold
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        mock_advance.reset_mock()
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )
        await process_advancement_evaluations()

        # Verify advancement occurred exactly once
        mock_advance.assert_called_once()

    @pytest.mark.asyncio
    async def test_ashby_api_timeout_graceful_handling(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Ashby API times out → logs error but continues processing."""

        rule_data = await create_test_rule(
            clean_db, interview_id=sample_interview["interview_id"]
        )

        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=rule_data["interview_plan_id"],
            interview_stage_id=rule_data["interview_stage_id"],
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            event_id = uuid4()
            interviewer_id = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Test', 'User', 'test@test.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                event_id,
                interviewer_id,
                uuid4(),
            )

        await create_test_feedback(
            clean_db,
            event_id=str(event_id),
            application_id=schedule_data["application_id"],
            interviewer_id=str(interviewer_id),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Mock API to timeout
        async def mock_timeout(*args, **kwargs):
            raise TimeoutError("API request timed out")

        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_timeout)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # Execute: Should not crash
        await process_advancement_evaluations()

        # Assert: Execution record shows failure
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                schedule_data["schedule_id"],
            )
            # Should have attempted and recorded failure
            assert execution is not None
            assert execution["execution_status"] in ["failed", "error"]

    @pytest.mark.asyncio
    async def test_multiple_rules_same_interview_stage(
        self, clean_db, sample_interview, monkeypatch
    ):
        """Multiple rules for same stage → first matching rule applies."""
        interview_plan_id = str(uuid4())
        interview_stage_id = str(uuid4())

        # Create two rules for the same interview stage
        rule1 = await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=sample_interview["interview_id"],
            target_stage_id=str(uuid4()),  # Different target
            operator=">=",
            threshold="3",
        )

        # Second rule (should not be used - first rule matches)
        await create_test_rule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            interview_id=sample_interview["interview_id"],
            target_stage_id=str(uuid4()),  # Different target
            operator=">=",
            threshold="5",
        )

        schedule_data = await create_test_schedule(
            clean_db,
            interview_plan_id=interview_plan_id,
            interview_stage_id=interview_stage_id,
            status="Complete",
        )

        async with clean_db.acquire() as conn:
            event_id = uuid4()
            interviewer_id = uuid4()

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, start_time, end_time,
                 feedback_link, location, meeting_link, has_submitted_feedback,
                 created_at, updated_at, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW() + interval '1 hour',
                        'https://ashby.com/feedback', 'Zoom', 'https://zoom.us/test',
                        true, NOW(), NOW(), '{}')
                """,
                event_id,
                schedule_data["schedule_id"],
                sample_interview["interview_id"],
            )

            await conn.execute(
                """
                INSERT INTO interview_assignments
                (event_id, interviewer_id, first_name, last_name, email,
                 global_role, training_role, is_enabled, interviewer_pool_id,
                 interviewer_pool_title, interviewer_pool_is_archived,
                 training_path, interviewer_updated_at)
                VALUES ($1, $2, 'Test', 'User', 'test@test.com',
                        'Interviewer', 'Trained', true, $3, 'Pool', false, '{}', NOW())
                """,
                event_id,
                interviewer_id,
                uuid4(),
            )

        await create_test_feedback(
            clean_db,
            event_id=str(event_id),
            application_id=schedule_data["application_id"],
            interviewer_id=str(interviewer_id),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},  # Passes rule1, not rule2
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        mock_advance = AsyncMock(return_value={"id": schedule_data["application_id"]})
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        await process_advancement_evaluations()

        # Verify advancement occurred exactly once
        mock_advance.assert_called_once()
        # Verify it advanced to rule1's target stage
        # Function is called as: advance_candidate_stage(application_id, target_stage_id)
        call_args = mock_advance.call_args[0]  # Positional args tuple
        assert call_args[1] == rule1["target_stage_id"]  # Second positional arg
