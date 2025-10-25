"""Tests for interview schedule processing (app/services/interviews.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.interviews import (
    delete_schedule,
    process_schedule_update,
    upsert_schedule_with_events,
)


@pytest.mark.asyncio
async def test_process_schedule_update_scheduled_status(clean_db):
    """Scheduled status triggers upsert."""
    schedule_id = str(uuid4())
    schedule = {
        "id": schedule_id,
        "status": "Scheduled",
        "applicationId": str(uuid4()),
        "interviewStageId": str(uuid4()),
        "candidateId": str(uuid4()),
        "interviewEvents": [],
    }

    with patch(
        "app.services.interviews.upsert_schedule_with_events", new_callable=AsyncMock
    ) as mock_upsert:
        await process_schedule_update(schedule)

        mock_upsert.assert_called_once_with(schedule, schedule_id, "Scheduled")


@pytest.mark.asyncio
async def test_process_schedule_update_complete_status(clean_db):
    """Complete status triggers upsert."""
    schedule_id = str(uuid4())
    schedule = {
        "id": schedule_id,
        "status": "Complete",
        "applicationId": str(uuid4()),
        "interviewStageId": str(uuid4()),
        "candidateId": str(uuid4()),
        "interviewEvents": [],
    }

    with patch(
        "app.services.interviews.upsert_schedule_with_events", new_callable=AsyncMock
    ) as mock_upsert:
        await process_schedule_update(schedule)

        mock_upsert.assert_called_once_with(schedule, schedule_id, "Complete")


@pytest.mark.asyncio
async def test_process_schedule_update_cancelled_status(clean_db):
    """Cancelled status triggers delete."""
    schedule_id = str(uuid4())
    schedule = {
        "id": schedule_id,
        "status": "Cancelled",
        "applicationId": str(uuid4()),
    }

    with patch(
        "app.services.interviews.delete_schedule", new_callable=AsyncMock
    ) as mock_delete:
        await process_schedule_update(schedule)

        mock_delete.assert_called_once_with(schedule_id)


@pytest.mark.asyncio
async def test_process_schedule_update_invalid_status_ignored(clean_db):
    """Invalid statuses logged and ignored."""
    schedule = {
        "id": str(uuid4()),
        "status": "InvalidStatus",
        "applicationId": str(uuid4()),
    }

    with (
        patch(
            "app.services.interviews.delete_schedule", new_callable=AsyncMock
        ) as mock_delete,
        patch(
            "app.services.interviews.upsert_schedule_with_events",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        await process_schedule_update(schedule)

        # Neither delete nor upsert should be called
        mock_delete.assert_not_called()
        mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_delete_schedule_removes_record(clean_db):
    """Schedule deletion verified in database."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())

    # First create a schedule
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_schedules
            (schedule_id, application_id, interview_stage_id, status, candidate_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            schedule_id,
            app_id,
            stage_id,
            "Scheduled",
            str(uuid4()),
        )

        # Verify it exists
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM interview_schedules WHERE schedule_id = $1)",
            schedule_id,
        )
        assert exists is True

    # Delete it
    await delete_schedule(schedule_id)

    # Verify it's gone
    async with clean_db.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM interview_schedules WHERE schedule_id = $1)",
            schedule_id,
        )
        assert exists is False


@pytest.mark.asyncio
async def test_upsert_schedule_creates_new_schedule(clean_db):
    """New schedule inserted with correct fields."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())
    candidate_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": candidate_id,
        "interviewEvents": [],
    }

    # Mock the API calls that fetch advancement fields
    with patch(
        "app.clients.ashby.fetch_interview_stage_info", new_callable=AsyncMock
    ) as mock_stage_info:
        mock_stage_info.return_value = {"interviewPlanId": str(uuid4())}

        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify schedule exists in database
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1", schedule_id
        )

        assert row is not None
        assert str(row["application_id"]) == app_id
        assert str(row["interview_stage_id"]) == stage_id
        assert str(row["candidate_id"]) == candidate_id
        assert row["status"] == "Scheduled"


@pytest.mark.asyncio
async def test_upsert_schedule_updates_existing_schedule(clean_db):
    """Existing schedule updated with new data."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())

    # First create a schedule with initial status
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_schedules
            (schedule_id, application_id, interview_stage_id, status, candidate_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            schedule_id,
            app_id,
            stage_id,
            "Scheduled",
            str(uuid4()),
        )

    # Update the schedule with new status
    new_candidate_id = str(uuid4())
    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": new_candidate_id,
        "interviewEvents": [],
    }

    with patch(
        "app.clients.ashby.fetch_interview_stage_info", new_callable=AsyncMock
    ) as mock_stage_info:
        mock_stage_info.return_value = {"interviewPlanId": str(uuid4())}

        await upsert_schedule_with_events(schedule, schedule_id, "Complete")

    # Verify schedule was updated
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1", schedule_id
        )

        assert row is not None
        assert row["status"] == "Complete"
        assert str(row["candidate_id"]) == new_candidate_id


@pytest.mark.asyncio
async def test_upsert_schedule_inserts_events_and_assignments(
    clean_db, sample_interview
):
    """Events and interviewers created."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())
    event_id = str(uuid4())
    interviewer_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": str(uuid4()),
        "interviewEvents": [
            {
                "id": event_id,
                "interviewId": sample_interview["interview_id"],
                "startTime": "2024-10-20T14:00:00.000Z",
                "endTime": "2024-10-20T15:00:00.000Z",
                "feedbackLink": "https://ashby.com/feedback",
                "location": "Zoom",
                "meetingLink": "https://zoom.us/test",
                "hasSubmittedFeedback": False,
                "createdAt": "2024-10-19T10:00:00.000Z",
                "updatedAt": "2024-10-19T10:00:00.000Z",
                "extraData": {},
                "interviewers": [
                    {
                        "id": interviewer_id,
                        "firstName": "Test",
                        "lastName": "User",
                        "email": "test@example.com",
                        "globalRole": "Interviewer",
                        "trainingRole": "Trained",
                        "isEnabled": True,
                        "updatedAt": "2024-10-19T10:00:00.000Z",
                        "interviewerPool": {
                            "id": str(uuid4()),
                            "title": "Test Pool",
                            "isArchived": False,
                            "trainingPath": {},
                        },
                    }
                ],
            }
        ],
    }

    # Mock API calls
    with (
        patch(
            "app.clients.ashby.fetch_interview_stage_info", new_callable=AsyncMock
        ) as mock_stage_info,
        patch(
            "app.clients.ashby.ashby_client.post", new_callable=AsyncMock
        ) as mock_ashby_post,
    ):
        mock_stage_info.return_value = {"interviewPlanId": str(uuid4())}
        # Mock the interview.info call
        mock_ashby_post.return_value = {
            "success": True,
            "results": {
                "id": sample_interview["interview_id"],
                "title": "Technical Interview",
                "externalTitle": "Tech Screen",
                "isArchived": False,
                "isDebrief": False,
                "instructionsHtml": "<p>Instructions</p>",
                "instructionsPlain": "Instructions",
                "jobId": sample_interview["job_id"],
                "feedbackFormDefinitionId": sample_interview["form_definition_id"],
            },
        }

        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify event and assignment exist in database
    async with clean_db.acquire() as conn:
        event = await conn.fetchrow(
            "SELECT * FROM interview_events WHERE event_id = $1", event_id
        )
        assert event is not None
        assert str(event["schedule_id"]) == schedule_id

        assignment = await conn.fetchrow(
            "SELECT * FROM interview_assignments WHERE event_id = $1", event_id
        )
        assert assignment is not None
        assert str(assignment["interviewer_id"]) == interviewer_id


@pytest.mark.asyncio
async def test_upsert_schedule_fetches_advancement_fields(clean_db):
    """interview_plan_id and job_id fetched from API."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())
    plan_id = str(uuid4())
    job_id = str(uuid4())
    interview_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": str(uuid4()),
        "interviewEvents": [
            {
                "id": str(uuid4()),
                "interviewId": interview_id,
                "interview": {"jobId": job_id},
                "startTime": "2024-10-20T14:00:00.000Z",
                "endTime": "2024-10-20T15:00:00.000Z",
                "createdAt": "2024-10-19T10:00:00.000Z",
                "updatedAt": "2024-10-19T10:00:00.000Z",
                "hasSubmittedFeedback": False,
                "interviewers": [],
            }
        ],
    }

    # Mock API calls
    with (
        patch(
            "app.clients.ashby.fetch_interview_stage_info", new_callable=AsyncMock
        ) as mock_stage_info,
        patch(
            "app.clients.ashby.ashby_client.post", new_callable=AsyncMock
        ) as mock_ashby_post,
    ):
        mock_stage_info.return_value = {"interviewPlanId": plan_id}

        # Mock both interview.info and application.info API calls
        def mock_api_call(endpoint, data):
            if endpoint == "interview.info":
                return {
                    "success": True,
                    "results": {
                        "id": interview_id,
                        "title": "Test Interview",
                    },
                }
            elif endpoint == "application.info":
                return {
                    "success": True,
                    "results": {
                        "job": {"id": job_id},
                    },
                }
            return {"success": False}

        mock_ashby_post.side_effect = mock_api_call

        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify advancement fields were set
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT interview_plan_id, job_id FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )

        assert row is not None
        assert str(row["interview_plan_id"]) == plan_id
        assert str(row["job_id"]) == job_id


@pytest.mark.asyncio
async def test_upsert_schedule_advancement_fetch_failure_handled(clean_db):
    """API failure doesn't crash processing."""
    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": str(uuid4()),
        "interviewEvents": [],
    }

    # Mock API call to raise an exception
    with patch(
        "app.clients.ashby.fetch_interview_stage_info", new_callable=AsyncMock
    ) as mock_stage_info:
        mock_stage_info.side_effect = Exception("API Error")

        # Should not raise, just log warning
        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify schedule was still created (without advancement fields)
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1", schedule_id
        )

        assert row is not None
        assert row["interview_plan_id"] is None
        assert row["job_id"] is None


@pytest.mark.asyncio
async def test_upsert_schedule_retries_advancement_fields_fetch(clean_db):
    """Test advancement fields fetch retries 3 times with delays [0.5s, 1.0s] on failures."""
    from unittest.mock import AsyncMock, call

    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())
    plan_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": str(uuid4()),
        "interviewEvents": [],
    }

    # Mock to fail twice, then succeed on 3rd attempt
    mock_stage_info = AsyncMock(
        side_effect=[
            Exception("Transient error"),
            Exception("Still failing"),
            {"interviewPlanId": plan_id},  # Success on attempt 3
        ]
    )
    mock_sleep = AsyncMock()

    with (
        patch("app.clients.ashby.fetch_interview_stage_info", mock_stage_info),
        patch("app.services.interviews.asyncio.sleep", mock_sleep),
    ):
        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify 3 attempts made (attempts 1, 2, 3)
    assert mock_stage_info.call_count == 3

    # Verify delays [0.5s, 1.0s] - calculated as 0.5 * attempt
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([call(0.5), call(1.0)])

    # Verify schedule was created with advancement fields
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT interview_plan_id FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert row is not None
        assert str(row["interview_plan_id"]) == plan_id


@pytest.mark.asyncio
async def test_upsert_schedule_continues_after_advancement_fields_retry_exhaustion(
    clean_db,
):
    """Test schedule is still created even when all advancement field retries fail."""
    from unittest.mock import AsyncMock

    schedule_id = str(uuid4())
    app_id = str(uuid4())
    stage_id = str(uuid4())

    schedule = {
        "id": schedule_id,
        "applicationId": app_id,
        "interviewStageId": stage_id,
        "candidateId": str(uuid4()),
        "interviewEvents": [],
    }

    # Mock to always fail
    mock_stage_info = AsyncMock(side_effect=Exception("Persistent API error"))
    mock_sleep = AsyncMock()

    with (
        patch("app.clients.ashby.fetch_interview_stage_info", mock_stage_info),
        patch("app.services.interviews.asyncio.sleep", mock_sleep),
    ):
        # Should not raise, just log warnings
        await upsert_schedule_with_events(schedule, schedule_id, "Scheduled")

    # Verify 3 attempts made
    assert mock_stage_info.call_count == 3

    # Verify 2 sleep calls
    assert mock_sleep.call_count == 2

    # Verify schedule was still created (graceful degradation - without advancement fields)
    async with clean_db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM interview_schedules WHERE schedule_id = $1",
            schedule_id,
        )
        assert row is not None
        assert str(row["schedule_id"]) == schedule_id
        assert str(row["application_id"]) == app_id
        assert row["interview_plan_id"] is None  # Failed to fetch
        assert row["job_id"] is None
