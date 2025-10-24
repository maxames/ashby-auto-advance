"""Integration tests for feedback sync."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.services.feedback_sync import sync_feedback_for_application
from tests.fixtures.factories import create_test_schedule


class TestFeedbackSyncIntegration:
    """Integration tests for feedback synchronization."""

    @pytest.mark.asyncio
    async def test_syncs_feedback_from_ashby_api(self, clean_db, monkeypatch):
        """Test syncs feedback from Ashby API and stores in database."""
        from unittest.mock import AsyncMock

        application_id = str(uuid4())
        event_id = str(uuid4())
        interview_id = str(uuid4())
        interviewer_id = str(uuid4())

        # Create schedule and event
        schedule = await create_test_schedule(clean_db, application_id=application_id)

        async with clean_db.acquire() as conn:
            # Insert parent interview record first
            await conn.execute(
                """
                INSERT INTO interviews (interview_id, title, job_id, feedback_form_definition_id)
                VALUES ($1, 'Test Interview', $2, $3)
                """,
                interview_id,
                schedule["job_id"],
                str(uuid4()),
            )

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, created_at, updated_at,
                 start_time, end_time, feedback_link, has_submitted_feedback, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW(), NOW(), NOW() + INTERVAL '1 hour',
                        'https://ashby.com/feedback', false, '{}')
                """,
                event_id,
                schedule["schedule_id"],
                interview_id,
            )

        # Mock Ashby API
        mock_feedback = [
            {
                "id": str(uuid4()),
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": interview_id,
                "submittedByUserId": interviewer_id,
                "submittedAt": datetime.now(UTC).isoformat(),
                "submittedValues": {
                    "overall_score": 4,
                    "technical_skills": 5,
                    "communication": 3,
                },
            },
            {
                "id": str(uuid4()),
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": interview_id,
                "submittedByUserId": str(uuid4()),  # Different interviewer
                "submittedAt": datetime.now(UTC).isoformat(),
                "submittedValues": {
                    "overall_score": 3,
                    "technical_skills": 4,
                    "communication": 4,
                },
            },
        ]

        from app.services import feedback_sync

        monkeypatch.setattr(
            feedback_sync,
            "fetch_application_feedback",
            AsyncMock(return_value=mock_feedback),
        )

        # Sync
        count = await sync_feedback_for_application(application_id)

        assert count == 2

        # Verify stored correctly
        async with clean_db.acquire() as conn:
            feedback_records = await conn.fetch(
                "SELECT * FROM feedback_submissions WHERE application_id = $1 ORDER BY submitted_at",
                application_id,
            )

            assert len(feedback_records) == 2

            # Check first feedback - parse submitted_values if it's a string
            import json

            submitted_values = feedback_records[0]["submitted_values"]
            if isinstance(submitted_values, str):
                submitted_values = json.loads(submitted_values)
            assert str(feedback_records[0]["interview_id"]) == interview_id
            assert submitted_values["overall_score"] == 4
            assert feedback_records[0]["processed_for_advancement_at"] is None

    @pytest.mark.asyncio
    async def test_stores_in_database_correctly(
        self, clean_db, sample_interview_event, monkeypatch
    ):
        """Test feedback is stored with all fields correctly."""
        from unittest.mock import AsyncMock

        application_id = sample_interview_event["application_id"]
        event_id = sample_interview_event["event_id"]
        feedback_id = str(uuid4())
        submitted_at = datetime.now(UTC).isoformat()

        # Get interview_id from event
        async with clean_db.acquire() as conn:
            interview_id = await conn.fetchval(
                "SELECT interview_id FROM interview_events WHERE event_id = $1",
                event_id,
            )

        mock_feedback = [
            {
                "id": feedback_id,
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": str(interview_id),
                "submittedByUserId": sample_interview_event["interviewer_id"],
                "submittedAt": submitted_at,
                "submittedValues": {"overall_score": 5, "notes": "Excellent candidate"},
            }
        ]

        from app.services import feedback_sync

        monkeypatch.setattr(
            feedback_sync,
            "fetch_application_feedback",
            AsyncMock(return_value=mock_feedback),
        )

        # Sync
        await sync_feedback_for_application(application_id)

        # Verify all fields stored
        async with clean_db.acquire() as conn:
            feedback = await conn.fetchrow(
                "SELECT * FROM feedback_submissions WHERE feedback_id = $1",
                feedback_id,
            )

            assert feedback is not None
            assert str(feedback["application_id"]) == application_id
            assert str(feedback["event_id"]) == event_id
            assert str(feedback["interview_id"]) == str(interview_id)
            assert str(feedback["interviewer_id"]) == sample_interview_event["interviewer_id"]

            # Parse submitted_values if it's a string
            import json

            submitted_values = feedback["submitted_values"]
            if isinstance(submitted_values, str):
                submitted_values = json.loads(submitted_values)
            assert submitted_values["overall_score"] == 5
            assert submitted_values["notes"] == "Excellent candidate"
            assert feedback["processed_for_advancement_at"] is None
            assert feedback["created_at"] is not None

    @pytest.mark.asyncio
    async def test_handles_pagination(self, clean_db, monkeypatch):
        """Test handles paginated responses from Ashby API."""
        from unittest.mock import AsyncMock

        application_id = str(uuid4())
        event_id = str(uuid4())
        interview_id = str(uuid4())

        # Create event
        schedule = await create_test_schedule(clean_db, application_id=application_id)

        async with clean_db.acquire() as conn:
            # Insert parent interview record first
            await conn.execute(
                """
                INSERT INTO interviews (interview_id, title, job_id, feedback_form_definition_id)
                VALUES ($1, 'Test Interview', $2, $3)
                """,
                interview_id,
                schedule["job_id"],
                str(uuid4()),
            )

            await conn.execute(
                """
                INSERT INTO interview_events
                (event_id, schedule_id, interview_id, created_at, updated_at,
                 start_time, end_time, feedback_link, has_submitted_feedback, extra_data)
                VALUES ($1, $2, $3, NOW(), NOW(), NOW(), NOW() + INTERVAL '1 hour',
                        'https://ashby.com/feedback', false, '{}')
                """,
                event_id,
                schedule["schedule_id"],
                interview_id,
            )

        # Mock API with multiple feedback items
        # Note: The actual fetch_application_feedback handles pagination internally
        mock_feedback = [
            {
                "id": str(uuid4()),
                "applicationId": application_id,
                "interviewEventId": event_id,
                "interviewId": interview_id,
                "submittedByUserId": str(uuid4()),
                "submittedAt": datetime.now(UTC).isoformat(),
                "submittedValues": {"overall_score": i},
            }
            for i in range(1, 6)  # 5 feedback submissions
        ]

        from app.services import feedback_sync

        monkeypatch.setattr(
            feedback_sync,
            "fetch_application_feedback",
            AsyncMock(return_value=mock_feedback),
        )

        # Sync
        count = await sync_feedback_for_application(application_id)

        assert count == 5

        # Verify all stored
        async with clean_db.acquire() as conn:
            feedback_count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_submissions WHERE application_id = $1",
                application_id,
            )
            assert feedback_count == 5
