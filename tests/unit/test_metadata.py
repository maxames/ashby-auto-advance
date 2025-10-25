"""Tests for metadata query service (app/services/metadata.py)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services import metadata as metadata_service


@pytest.mark.asyncio
async def test_get_jobs_returns_all_jobs(clean_db):
    """Returns all jobs when active_only=False."""
    job1_id = str(uuid4())
    job2_id = str(uuid4())

    # Insert open and closed jobs
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job1_id,
            "Open Job",
            "Open",
        )
        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job2_id,
            "Closed Job",
            "Closed",
        )

    jobs = await metadata_service.get_jobs(active_only=False)

    assert len(jobs) == 2
    assert any(j["title"] == "Open Job" for j in jobs)
    assert any(j["title"] == "Closed Job" for j in jobs)


@pytest.mark.asyncio
async def test_get_jobs_filters_active_only(clean_db):
    """Returns only open jobs when active_only=True."""
    job1_id = str(uuid4())
    job2_id = str(uuid4())

    # Insert open and closed jobs
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job1_id,
            "Open Job",
            "Open",
        )
        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job2_id,
            "Closed Job",
            "Closed",
        )

    jobs = await metadata_service.get_jobs(active_only=True)

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Open Job"
    assert jobs[0]["status"] == "Open"


@pytest.mark.asyncio
async def test_get_jobs_returns_empty_list(clean_db):
    """Returns empty list when no jobs exist."""
    jobs = await metadata_service.get_jobs()

    assert jobs == []


@pytest.mark.asyncio
async def test_get_plans_for_job_returns_plans_with_default_flag(clean_db):
    """Returns plans ordered by is_default DESC."""
    job_id = str(uuid4())
    plan1_id = str(uuid4())
    plan2_id = str(uuid4())

    # Insert plans and mappings
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_plans (interview_plan_id, title, is_archived, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            plan1_id,
            "Default Plan",
            False,
        )
        await conn.execute(
            """
            INSERT INTO interview_plans (interview_plan_id, title, is_archived, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            plan2_id,
            "Other Plan",
            False,
        )

        await conn.execute(
            """
            INSERT INTO jobs (job_id, title, status, synced_at)
            VALUES ($1, $2, $3, NOW())
            """,
            job_id,
            "Test Job",
            "Open",
        )

        await conn.execute(
            """
            INSERT INTO job_interview_plans (job_id, interview_plan_id, is_default)
            VALUES ($1, $2, $3)
            """,
            job_id,
            plan1_id,
            True,
        )
        await conn.execute(
            """
            INSERT INTO job_interview_plans (job_id, interview_plan_id, is_default)
            VALUES ($1, $2, $3)
            """,
            job_id,
            plan2_id,
            False,
        )

    plans = await metadata_service.get_plans_for_job(job_id)

    assert len(plans) == 2
    # Default plan should be first
    assert plans[0]["title"] == "Default Plan"
    assert plans[0]["is_default"] is True
    assert plans[1]["title"] == "Other Plan"
    assert plans[1]["is_default"] is False


@pytest.mark.asyncio
async def test_get_stages_for_plan_returns_ordered_stages(clean_db):
    """Returns stages ordered by order_in_plan."""
    plan_id = str(uuid4())
    stage1_id = str(uuid4())
    stage2_id = str(uuid4())
    stage3_id = str(uuid4())

    # Insert plan and stages in random order
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

        # Insert stages with different orders
        await conn.execute(
            """
            INSERT INTO interview_stages
            (interview_stage_id, interview_plan_id, title, type, order_in_plan, synced_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            stage2_id,
            plan_id,
            "Stage 2",
            "Active",
            2,
        )
        await conn.execute(
            """
            INSERT INTO interview_stages
            (interview_stage_id, interview_plan_id, title, type, order_in_plan, synced_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            stage1_id,
            plan_id,
            "Stage 1",
            "Active",
            1,
        )
        await conn.execute(
            """
            INSERT INTO interview_stages
            (interview_stage_id, interview_plan_id, title, type, order_in_plan, synced_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            stage3_id,
            plan_id,
            "Stage 3",
            "Active",
            3,
        )

    stages = await metadata_service.get_stages_for_plan(plan_id)

    assert len(stages) == 3
    # Verify ordering
    assert stages[0]["title"] == "Stage 1"
    assert stages[0]["order"] == 1
    assert stages[1]["title"] == "Stage 2"
    assert stages[1]["order"] == 2
    assert stages[2]["title"] == "Stage 3"
    assert stages[2]["order"] == 3


@pytest.mark.asyncio
async def test_get_interviews_filters_by_job(clean_db):
    """Returns only interviews for specified job."""
    job1_id = str(uuid4())
    job2_id = str(uuid4())
    interview1_id = str(uuid4())
    interview2_id = str(uuid4())

    # Insert interviews for different jobs
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interviews
            (interview_id, title, external_title, is_archived, is_debrief,
             instructions_html, instructions_plain, job_id,
             feedback_form_definition_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
            interview1_id,
            "Interview for Job 1",
            None,
            False,
            False,
            None,
            None,
            job1_id,
            None,
        )
        await conn.execute(
            """
            INSERT INTO interviews
            (interview_id, title, external_title, is_archived, is_debrief,
             instructions_html, instructions_plain, job_id,
             feedback_form_definition_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
            interview2_id,
            "Interview for Job 2",
            None,
            False,
            False,
            None,
            None,
            job2_id,
            None,
        )

    interviews = await metadata_service.get_interviews(job_id=job1_id)

    assert len(interviews) == 1
    assert interviews[0]["title"] == "Interview for Job 1"


@pytest.mark.asyncio
async def test_get_interviews_excludes_archived(clean_db):
    """Excludes archived interviews."""
    interview1_id = str(uuid4())
    interview2_id = str(uuid4())

    # Insert active and archived interviews
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interviews
            (interview_id, title, external_title, is_archived, is_debrief,
             instructions_html, instructions_plain, job_id,
             feedback_form_definition_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
            interview1_id,
            "Active Interview",
            None,
            False,
            False,
            None,
            None,
            None,
            None,
        )
        await conn.execute(
            """
            INSERT INTO interviews
            (interview_id, title, external_title, is_archived, is_debrief,
             instructions_html, instructions_plain, job_id,
             feedback_form_definition_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
            interview2_id,
            "Archived Interview",
            None,
            True,
            False,
            None,
            None,
            None,
            None,
        )

    interviews = await metadata_service.get_interviews()

    assert len(interviews) == 1
    assert interviews[0]["title"] == "Active Interview"
