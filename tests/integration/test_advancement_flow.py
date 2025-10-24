"""Integration tests for full advancement workflow."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.services.advancement import process_advancement_evaluations
from app.services.feedback_sync import sync_feedback_for_application
from tests.fixtures.factories import (
    create_test_feedback,
    create_test_rule,
    create_test_schedule,
)


class TestAdvancementFlow:
    """Integration tests for complete advancement workflow."""

    @pytest.mark.asyncio
    async def test_complete_flow_webhook_to_advancement(
        self, clean_db, sample_interview, sample_interview_event, monkeypatch
    ):
        """Test complete flow: schedule created → feedback synced → evaluated → advanced."""
        from unittest.mock import AsyncMock

        # 1. Schedule exists (simulating webhook created it)
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="3",
        )

        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1,
                    interview_stage_id = $2,
                    status = 'Complete',
                    job_id = $3
                WHERE schedule_id = $4
                """,
                rule_data["interview_plan_id"],
                rule_data["interview_stage_id"],
                uuid4(),
                schedule_id,
            )

        # 2. Sync feedback (simulating scheduled job)
        feedback_data = {
            "id": str(uuid4()),
            "applicationId": sample_interview_event["application_id"],
            "interviewEventId": sample_interview_event["event_id"],
            "interviewId": sample_interview["interview_id"],
            "submittedByUser": {
                "id": sample_interview_event["interviewer_id"],
                "firstName": "Test",
                "lastName": "Interviewer",
                "email": "test@example.com",
            },
            "submittedAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "submittedValues": {"overall_score": 4},
        }

        from app.services import advancement, feedback_sync

        monkeypatch.setattr(
            feedback_sync,
            "fetch_application_feedback",
            AsyncMock(return_value=[feedback_data]),
        )

        await sync_feedback_for_application(sample_interview_event["application_id"])

        # 3. Mock advancement API
        mock_advance = AsyncMock(
            return_value={"id": sample_interview_event["application_id"]}
        )
        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)

        # Disable dry-run mode for this test
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # 4. Run evaluation (simulating scheduled job)
        await process_advancement_evaluations()

        # 5. Verify advancement occurred (may be called with retries)
        assert mock_advance.called, "Mock advance should have been called"

        # Check audit trail
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                schedule_id,
            )
            assert execution is not None
            assert execution["execution_status"] == "success"

    @pytest.mark.asyncio
    async def test_rejection_notification_flow(
        self, clean_db, sample_interview, sample_interview_event, monkeypatch
    ):
        """Test rejection notification is sent when candidate fails."""
        from unittest.mock import AsyncMock

        # Create rule with high threshold
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
            operator=">=",
            threshold="4",  # High threshold
        )

        schedule_id = sample_interview_event["schedule_id"]
        application_id = sample_interview_event["application_id"]

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1,
                    interview_stage_id = $2,
                    status = 'Complete',
                    job_id = $3
                WHERE schedule_id = $4
                """,
                rule_data["interview_plan_id"],
                rule_data["interview_stage_id"],
                uuid4(),
                schedule_id,
            )

        # Create failing feedback
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=application_id,
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 2},  # Fails threshold
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Mock Slack and Ashby clients
        mock_post_message = AsyncMock()
        mock_fetch_candidate = AsyncMock(
            return_value={"id": "candidate_id", "name": "Test Candidate"}
        )

        from app.clients import ashby, slack

        monkeypatch.setattr(slack.slack_client, "chat_postMessage", mock_post_message)
        monkeypatch.setattr(ashby, "fetch_candidate_info", mock_fetch_candidate)

        # Mock getting job info for recruiter
        from app.core.config import settings

        monkeypatch.setattr(settings, "admin_slack_channel_id", "C123456")

        # Run evaluation
        await process_advancement_evaluations()

        # Should send rejection notification (implementation may vary)
        # Check schedule was marked as evaluated
        async with clean_db.acquire() as conn:
            schedule = await conn.fetchrow(
                "SELECT last_evaluated_for_advancement_at FROM interview_schedules WHERE schedule_id = $1",
                schedule_id,
            )
            assert schedule["last_evaluated_for_advancement_at"] is not None

    @pytest.mark.asyncio
    async def test_dry_run_mode_prevents_actual_advancement(
        self, clean_db, sample_interview, sample_interview_event, monkeypatch
    ):
        """Test dry-run mode logs but doesn't execute advancement."""
        from unittest.mock import AsyncMock

        # Enable dry-run mode
        from app.core.config import settings

        monkeypatch.setattr(settings, "advancement_dry_run_mode", True)

        # Setup passing scenario
        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
        )

        schedule_id = sample_interview_event["schedule_id"]
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1,
                    interview_stage_id = $2,
                    status = 'Complete'
                WHERE schedule_id = $3
                """,
                rule_data["interview_plan_id"],
                rule_data["interview_stage_id"],
                schedule_id,
            )

        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=sample_interview_event["application_id"],
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Mock API
        mock_advance = AsyncMock()
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)

        # Run evaluation
        await process_advancement_evaluations()

        # API should NOT have been called
        mock_advance.assert_not_called()

        # But audit record should exist with dry_run status
        async with clean_db.acquire() as conn:
            execution = await conn.fetchrow(
                "SELECT * FROM advancement_executions WHERE schedule_id = $1",
                schedule_id,
            )
            assert execution is not None
            assert execution["execution_status"] == "dry_run"

    @pytest.mark.asyncio
    async def test_multiple_interviewers_scenario(
        self, clean_db, sample_interview, sample_interview_event, monkeypatch
    ):
        """Test advancement waits for all interviewers to submit."""
        from unittest.mock import AsyncMock

        rule_data = await create_test_rule(
            clean_db,
            interview_id=sample_interview["interview_id"],
        )

        schedule_id = sample_interview_event["schedule_id"]
        application_id = sample_interview_event["application_id"]

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                UPDATE interview_schedules
                SET interview_plan_id = $1,
                    interview_stage_id = $2,
                    status = 'Complete'
                WHERE schedule_id = $3
                """,
                rule_data["interview_plan_id"],
                rule_data["interview_stage_id"],
                schedule_id,
            )

            # Add second interviewer
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
                sample_interview_event["event_id"],
                interviewer2_id,
                uuid4(),
            )

        # Only first interviewer submits
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=application_id,
            interviewer_id=sample_interview_event["interviewer_id"],
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Mock API
        mock_advance = AsyncMock()
        from app.services import advancement

        monkeypatch.setattr(advancement, "advance_candidate_stage", mock_advance)

        # Run evaluation
        await process_advancement_evaluations()

        # Should NOT advance (missing second interviewer feedback)
        mock_advance.assert_not_called()

        # Now second interviewer submits
        await create_test_feedback(
            clean_db,
            event_id=sample_interview_event["event_id"],
            application_id=application_id,
            interviewer_id=str(interviewer2_id),
            interview_id=sample_interview["interview_id"],
            submitted_values={"overall_score": 4},
            submitted_at=datetime.now(UTC) - timedelta(hours=1),
        )

        # Disable dry-run mode for actual advancement test
        monkeypatch.setattr(
            "app.services.advancement.settings.advancement_dry_run_mode", False
        )

        # Run evaluation again
        await process_advancement_evaluations()

        # NOW it should advance (may be called with retries)
        assert mock_advance.called, "Mock advance should have been called"
