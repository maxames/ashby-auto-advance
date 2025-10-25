"""Tests for metadata sync operations (app/services/metadata_sync.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import metadata_sync as metadata_sync_module


@pytest.mark.asyncio
async def test_sync_jobs_fetches_and_stores(clean_db):
    """Jobs fetched from API and inserted into DB."""
    job_id = str(uuid4())
    plan_id = str(uuid4())

    mock_job = {
        "id": job_id,
        "title": "Senior Engineer",
        "status": "Open",
        "departmentId": str(uuid4()),
        "defaultInterviewPlanId": plan_id,
        "interviewPlanIds": [plan_id],
        "employmentType": "FullTime",
        "location": {"name": "San Francisco"},
        "createdAt": "2024-10-20T14:30:00Z",
        "updatedAt": "2024-10-20T14:30:00Z",
    }

    mock_response = {
        "success": True,
        "results": [mock_job],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await metadata_sync_module.sync_jobs()

        # Verify API was called
        mock_post.assert_called_once()

        # Verify job was stored
        async with clean_db.acquire() as conn:
            job = await conn.fetchrow("SELECT * FROM jobs WHERE job_id = $1", job_id)
            assert job is not None
            assert job["title"] == "Senior Engineer"
            assert job["status"] == "Open"

            # Verify plan mapping created
            mapping = await conn.fetchrow(
                "SELECT * FROM job_interview_plans WHERE job_id = $1 AND interview_plan_id = $2",
                job_id,
                plan_id,
            )
            assert mapping is not None
            assert mapping["is_default"] is True


@pytest.mark.asyncio
async def test_sync_jobs_handles_pagination(clean_db):
    """Continues fetching until moreDataAvailable is False."""
    job1_id = str(uuid4())
    job2_id = str(uuid4())

    # First page
    page1_response = {
        "success": True,
        "results": [
            {
                "id": job1_id,
                "title": "Job 1",
                "status": "Open",
                "interviewPlanIds": [],
            }
        ],
        "moreDataAvailable": True,
        "nextCursor": "cursor123",
    }

    # Second page
    page2_response = {
        "success": True,
        "results": [
            {
                "id": job2_id,
                "title": "Job 2",
                "status": "Open",
                "interviewPlanIds": [],
            }
        ],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.side_effect = [page1_response, page2_response]

        await metadata_sync_module.sync_jobs()

        # Verify API was called twice
        assert mock_post.call_count == 2

        # Verify both jobs stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM jobs")
            assert count == 2


@pytest.mark.asyncio
async def test_sync_jobs_upserts_existing_jobs(clean_db):
    """ON CONFLICT updates existing jobs."""
    job_id = str(uuid4())

    # Insert initial job
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job_id,
            "Old Title",
            "Open",
        )

    # Sync with updated title
    mock_job = {
        "id": job_id,
        "title": "New Title",
        "status": "Closed",
        "interviewPlanIds": [],
    }

    mock_response = {
        "success": True,
        "results": [mock_job],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await metadata_sync_module.sync_jobs()

        # Verify job was updated
        async with clean_db.acquire() as conn:
            job = await conn.fetchrow("SELECT * FROM jobs WHERE job_id = $1", job_id)
            assert job["title"] == "New Title"
            assert job["status"] == "Closed"


@pytest.mark.asyncio
async def test_sync_jobs_creates_plan_mappings(clean_db):
    """Job interview plan associations created correctly."""
    job_id = str(uuid4())
    plan1_id = str(uuid4())
    plan2_id = str(uuid4())

    mock_job = {
        "id": job_id,
        "title": "Engineer",
        "status": "Open",
        "interviewPlanIds": [plan1_id, plan2_id],
        "defaultInterviewPlanId": plan1_id,
    }

    mock_response = {
        "success": True,
        "results": [mock_job],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await metadata_sync_module.sync_jobs()

        # Verify both plan mappings created
        async with clean_db.acquire() as conn:
            mappings = await conn.fetch(
                "SELECT * FROM job_interview_plans WHERE job_id = $1 ORDER BY is_default DESC",
                job_id,
            )
            assert len(mappings) == 2

            # Default plan should be first
            assert str(mappings[0]["interview_plan_id"]) == plan1_id
            assert mappings[0]["is_default"] is True

            assert str(mappings[1]["interview_plan_id"]) == plan2_id
            assert mappings[1]["is_default"] is False


@pytest.mark.asyncio
async def test_sync_jobs_api_error_handled(clean_db):
    """API errors logged, doesn't crash."""
    mock_response = {
        "success": False,
        "error": "API Error",
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        # Should not raise exception
        await metadata_sync_module.sync_jobs()

        # Verify no jobs were stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM jobs")
            assert count == 0


@pytest.mark.asyncio
async def test_sync_interview_plans_fetches_and_stores(clean_db):
    """Plans fetched and inserted."""
    plan_id = str(uuid4())

    mock_plan = {
        "id": plan_id,
        "title": "Engineering Onsite",
        "isArchived": False,
        "createdAt": "2024-10-20T14:30:00Z",
        "updatedAt": "2024-10-20T14:30:00Z",
    }

    mock_response = {
        "success": True,
        "results": [mock_plan],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await metadata_sync_module.sync_interview_plans()

        # Verify plan was stored
        async with clean_db.acquire() as conn:
            plan = await conn.fetchrow(
                "SELECT * FROM interview_plans WHERE interview_plan_id = $1",
                plan_id,
            )
            assert plan is not None
            assert plan["title"] == "Engineering Onsite"
            assert plan["is_archived"] is False


@pytest.mark.asyncio
async def test_sync_interview_stages_fetches_for_all_plans(clean_db):
    """Stages synced for all active plans."""
    plan1_id = str(uuid4())
    plan2_id = str(uuid4())
    stage1_id = str(uuid4())
    stage2_id = str(uuid4())

    # Insert plans
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_plans (interview_plan_id, title, is_archived, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            plan1_id,
            "Plan 1",
            False,
        )
        await conn.execute(
            """
            INSERT INTO interview_plans (interview_plan_id, title, is_archived, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            plan2_id,
            "Plan 2",
            False,
        )

    # Mock stage responses
    mock_stages_plan1 = [
        {
            "id": stage1_id,
            "title": "Stage 1",
            "orderInInterviewPlan": 1,
            "type": "Active",
        }
    ]

    mock_stages_plan2 = [
        {
            "id": stage2_id,
            "title": "Stage 2",
            "orderInInterviewPlan": 1,
            "type": "Active",
        }
    ]

    with patch(
        "app.services.metadata_sync.list_interview_stages_for_plan",
        new_callable=AsyncMock,
    ) as mock_stages:
        mock_stages.side_effect = [mock_stages_plan1, mock_stages_plan2]

        await metadata_sync_module.sync_interview_stages()

        # Verify stages for both plans were fetched
        assert mock_stages.call_count == 2

        # Verify both stages stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM interview_stages")
            assert count == 2


@pytest.mark.asyncio
async def test_sync_interview_stages_deletes_old_stages(clean_db):
    """Old stages deleted before inserting new ones."""
    plan_id = str(uuid4())
    old_stage_id = str(uuid4())
    new_stage_id = str(uuid4())

    # Insert plan
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_plans (interview_plan_id, title, is_archived, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            plan_id,
            "Test Plan",
            False,
        )

        # Insert old stage
        await conn.execute(
            """
            INSERT INTO interview_stages
            (interview_stage_id, interview_plan_id, title, type, order_in_plan, synced_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            old_stage_id,
            plan_id,
            "Old Stage",
            "Active",
            1,
        )

    # Sync with new stage
    mock_new_stage = [
        {
            "id": new_stage_id,
            "title": "New Stage",
            "orderInInterviewPlan": 1,
            "type": "Active",
        }
    ]

    with patch(
        "app.services.metadata_sync.list_interview_stages_for_plan",
        new_callable=AsyncMock,
    ) as mock_stages:
        mock_stages.return_value = mock_new_stage

        await metadata_sync_module.sync_interview_stages()

        # Verify old stage was deleted and new stage inserted
        async with clean_db.acquire() as conn:
            old_exists = await conn.fetchval(
                "SELECT COUNT(*) FROM interview_stages WHERE interview_stage_id = $1",
                old_stage_id,
            )
            assert old_exists == 0

            new_exists = await conn.fetchval(
                "SELECT COUNT(*) FROM interview_stages WHERE interview_stage_id = $1",
                new_stage_id,
            )
            assert new_exists == 1
