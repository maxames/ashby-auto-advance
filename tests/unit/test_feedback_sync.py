"""Unit tests for feedback sync service."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.feedback_sync import (
    sync_feedback_for_active_schedules,
    sync_feedback_for_application,
)
from tests.fixtures.factories import create_test_schedule


class TestSyncFeedbackForApplication:
    """Tests for sync_feedback_for_application function."""

    @pytest.mark.asyncio
    async def test_inserts_new_feedback_submissions(self, clean_db, monkeypatch):
        """Test inserts new feedback submissions from Ashby API."""
        from unittest.mock import AsyncMock

        application_id = str(uuid4())
        event_id = str(uuid4())
        interview_id = str(uuid4())
        interviewer_id = str(uuid4())

        # Create event in database
        schedule = await create_test_schedule(clean_db, application_id=application_id)

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, created_at, updated_at,
                 start_time, end_time, feedback_link, has_submitted_feedback, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW(), NOW(), NOW() + INTERVAL '1 hour',
                        'https://ashby.com/feedback', false, '{}')
                """,
                uuid4(event_id),
                uuid4(schedule["schedule_id"]),
                uuid4(interview_id),
            )

        # Mock Ashby API response
        mock_feedback = [
            {
                "id": str(uuid4()),
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": interview_id,
                "submittedByUserId": interviewer_id,
                "submittedAt": datetime.now(UTC).isoformat(),
                "submittedValues": {"overall_score": 4},
            }
        ]

        from app.clients import ashby

        monkeypatch.setattr(
            ashby, "fetch_application_feedback", AsyncMock(return_value=mock_feedback)
        )

        # Sync
        count = await sync_feedback_for_application(application_id)

        assert count == 1

        # Check database
        async with clean_db.acquire() as conn:
            feedback_count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_submissions WHERE application_id = $1",
                uuid4(application_id),
            )
            assert feedback_count == 1

    @pytest.mark.asyncio
    async def test_idempotent_doesnt_duplicate_existing(self, clean_db, monkeypatch):
        """Test doesn't duplicate feedback that already exists."""
        from unittest.mock import AsyncMock

        application_id = str(uuid4())
        event_id = str(uuid4())
        interview_id = str(uuid4())
        interviewer_id = str(uuid4())
        feedback_id = str(uuid4())

        # Create event
        schedule = await create_test_schedule(clean_db, application_id=application_id)

        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, created_at, updated_at,
                 start_time, end_time, feedback_link, has_submitted_feedback, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW(), NOW(), NOW() + INTERVAL '1 hour',
                        'https://ashby.com/feedback', false, '{}')
                """,
                uuid4(event_id),
                uuid4(schedule["schedule_id"]),
                uuid4(interview_id),
            )

        # Insert existing feedback
        async with clean_db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_submissions
                (feedback_id, application_id, event_id, interviewer_id, interview_id,
                 submitted_at, submitted_values, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW(), '{"overall_score": 4}', NOW())
                """,
                uuid4(feedback_id),
                uuid4(application_id),
                uuid4(event_id),
                uuid4(interviewer_id),
                uuid4(interview_id),
            )

        # Mock API to return same feedback
        mock_feedback = [
            {
                "id": feedback_id,
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": interview_id,
                "submittedByUserId": interviewer_id,
                "submittedAt": datetime.now(UTC).isoformat(),
                "submittedValues": {"overall_score": 4},
            }
        ]

        from app.clients import ashby

        monkeypatch.setattr(
            ashby, "fetch_application_feedback", AsyncMock(return_value=mock_feedback)
        )

        # Sync
        count = await sync_feedback_for_application(application_id)

        assert count == 0  # No new submissions

        # Check still only one record
        async with clean_db.acquire() as conn:
            feedback_count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_submissions WHERE application_id = $1",
                uuid4(application_id),
            )
            assert feedback_count == 1

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, clean_db, monkeypatch):
        """Test handles empty feedback list gracefully."""
        from unittest.mock import AsyncMock

        application_id = str(uuid4())

        # Mock empty response
        from app.clients import ashby

        monkeypatch.setattr(
            ashby, "fetch_application_feedback", AsyncMock(return_value=[])
        )

        # Sync
        count = await sync_feedback_for_application(application_id)

        assert count == 0


class TestSyncFeedbackForActiveSchedules:
    """Tests for sync_feedback_for_active_schedules function."""

    @pytest.mark.asyncio
    async def test_processes_all_active_schedules(self, clean_db, monkeypatch):
        """Test processes schedules with WaitingOnFeedback and Complete status."""
        from unittest.mock import AsyncMock

        # Create schedules with different statuses
        app1 = str(uuid4())
        app2 = str(uuid4())
        await create_test_schedule(clean_db, application_id=app1, status="Complete")
        await create_test_schedule(
            clean_db, application_id=app2, status="WaitingOnFeedback"
        )
        await create_test_schedule(clean_db, status="Scheduled")  # Should be ignored

        # Mock API
        from app.clients import ashby

        monkeypatch.setattr(
            ashby, "fetch_application_feedback", AsyncMock(return_value=[])
        )

        # Sync
        await sync_feedback_for_active_schedules()

        # Should have called API for both active applications
        assert ashby.fetch_application_feedback.call_count == 2

    @pytest.mark.asyncio
    async def test_continues_on_individual_failures(self, clean_db, monkeypatch):
        """Test continues processing even if one application fails."""
        from unittest.mock import AsyncMock

        # Create two schedules
        app1 = str(uuid4())
        app2 = str(uuid4())
        await create_test_schedule(clean_db, application_id=app1, status="Complete")
        await create_test_schedule(clean_db, application_id=app2, status="Complete")

        # Mock API to fail on first, succeed on second
        call_count = 0

        async def mock_fetch(application_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API Error")
            return []

        from app.clients import ashby

        monkeypatch.setattr(ashby, "fetch_application_feedback", mock_fetch)

        # Should not raise exception
        await sync_feedback_for_active_schedules()

        # Should have tried both
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_logs_summary_statistics(self, clean_db, monkeypatch, caplog):
        """Test logs summary of sync operation."""
        from unittest.mock import AsyncMock

        # Create schedule
        await create_test_schedule(clean_db, status="Complete")

        # Mock API
        from app.clients import ashby

        monkeypatch.setattr(
            ashby, "fetch_application_feedback", AsyncMock(return_value=[])
        )

        # Sync
        import logging

        caplog.set_level(logging.INFO)
        await sync_feedback_for_active_schedules()

        # Check logs contain completion message
        assert any(
            "feedback_sync" in record.message.lower() for record in caplog.records
        )
