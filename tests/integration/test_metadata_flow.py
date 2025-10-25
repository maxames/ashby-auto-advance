"""Integration tests for metadata sync and query."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.metadata import get_jobs, get_plans_for_job, get_stages_for_plan
from app.services.metadata_sync import (
    sync_interview_plans,
    sync_interview_stages,
    sync_jobs,
)


@pytest.mark.asyncio
async def test_complete_metadata_sync_flow(clean_db):
    """Test syncing jobs → plans → stages → query."""
    job_id = str(uuid4())
    plan_id = str(uuid4())
    stage_id = str(uuid4())

    # Mock Ashby responses
    mock_job = {
        "id": job_id,
        "title": "Senior Engineer",
        "status": "Open",
        "interviewPlanIds": [plan_id],
        "defaultInterviewPlanId": plan_id,
    }

    mock_plan = {
        "id": plan_id,
        "title": "Engineering Onsite",
        "isArchived": False,
    }

    mock_stage = {
        "id": stage_id,
        "title": "Technical Screen",
        "orderInInterviewPlan": 1,
        "type": "Active",
    }

    with (
        patch(
            "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
        ) as mock_post,
        patch(
            "app.services.metadata_sync.list_interview_stages_for_plan",
            new_callable=AsyncMock,
        ) as mock_stages,
    ):
        # Setup mocks
        mock_post.side_effect = [
            {
                "success": True,
                "results": [mock_job],
                "moreDataAvailable": False,
            },  # job.list
            {
                "success": True,
                "results": [mock_plan],
                "moreDataAvailable": False,
            },  # plan.list
        ]
        mock_stages.return_value = [mock_stage]

        # Sync all metadata
        await sync_jobs()
        await sync_interview_plans()
        await sync_interview_stages()

        # Query and verify
        jobs = await get_jobs()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Engineer"

        plans = await get_plans_for_job(job_id)
        assert len(plans) == 1
        assert plans[0]["title"] == "Engineering Onsite"
        assert plans[0]["is_default"] is True

        stages = await get_stages_for_plan(plan_id)
        assert len(stages) == 1
        assert stages[0]["title"] == "Technical Screen"
        assert stages[0]["order"] == 1


@pytest.mark.asyncio
async def test_metadata_sync_with_multiple_jobs(clean_db):
    """Test multiple jobs with shared plans."""
    job1_id = str(uuid4())
    job2_id = str(uuid4())
    plan_id = str(uuid4())

    # Mock jobs with shared plan
    mock_jobs = [
        {
            "id": job1_id,
            "title": "Senior Engineer",
            "status": "Open",
            "interviewPlanIds": [plan_id],
            "defaultInterviewPlanId": plan_id,
        },
        {
            "id": job2_id,
            "title": "Junior Engineer",
            "status": "Open",
            "interviewPlanIds": [plan_id],
            "defaultInterviewPlanId": plan_id,
        },
    ]

    mock_plan = {
        "id": plan_id,
        "title": "Engineering Interview Process",
        "isArchived": False,
    }

    with patch(
        "app.services.metadata_sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.side_effect = [
            {"success": True, "results": mock_jobs, "moreDataAvailable": False},
            {"success": True, "results": [mock_plan], "moreDataAvailable": False},
        ]

        await sync_jobs()
        await sync_interview_plans()

        # Verify both jobs share the same plan
        async with clean_db.acquire() as conn:
            mappings = await conn.fetch(
                "SELECT * FROM job_interview_plans WHERE interview_plan_id = $1",
                plan_id,
            )
            assert len(mappings) == 2

            # Verify both jobs
            jobs = await get_jobs()
            assert len(jobs) == 2


@pytest.mark.asyncio
async def test_metadata_queries_with_empty_database(clean_db):
    """Test empty state handling."""
    # Query empty database
    jobs = await get_jobs()
    assert jobs == []

    # Query non-existent job
    plans = await get_plans_for_job(str(uuid4()))
    assert plans == []

    # Query non-existent plan
    stages = await get_stages_for_plan(str(uuid4()))
    assert stages == []
