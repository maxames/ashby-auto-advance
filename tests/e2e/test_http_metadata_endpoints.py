"""E2E HTTP tests for metadata endpoints."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests.fixtures.factories import (
    create_test_interview_plan,
    create_test_job,
    create_test_stage,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_jobs_http_endpoint(http_client, clean_db):
    """GET /admin/metadata/jobs returns jobs."""
    # Create test jobs
    await create_test_job(clean_db, title="Backend Engineer", status="Open")
    await create_test_job(clean_db, title="Frontend Engineer", status="Closed")

    # Call endpoint
    response = await http_client.get("/admin/metadata/jobs?active_only=true")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert len(data["jobs"]) == 1  # Only open job
    assert data["jobs"][0]["title"] == "Backend Engineer"
    assert data["jobs"][0]["status"] == "Open"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_job_plans_http_endpoint(http_client, clean_db):
    """GET /admin/metadata/jobs/{job_id}/plans returns plans."""
    job_id = str(uuid4())
    plan1_id = str(uuid4())
    plan2_id = str(uuid4())

    # Create job
    await create_test_job(clean_db, job_id=job_id, title="Engineer")

    # Create plans
    await create_test_interview_plan(clean_db, plan_id=plan1_id, title="Onsite")
    await create_test_interview_plan(clean_db, plan_id=plan2_id, title="Phone Screen")

    # Create mappings
    async with clean_db.acquire() as conn:
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

    # Call endpoint
    response = await http_client.get(f"/admin/metadata/jobs/{job_id}/plans")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert len(data["plans"]) == 2
    # Default plan should be first
    assert data["plans"][0]["title"] == "Onsite"
    assert data["plans"][0]["is_default"] is True


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_plan_stages_http_endpoint(http_client, clean_db):
    """GET /admin/metadata/plans/{plan_id}/stages returns stages."""
    plan_id = str(uuid4())

    # Create plan
    await create_test_interview_plan(clean_db, plan_id=plan_id, title="Onsite")

    # Create stages
    await create_test_stage(clean_db, plan_id=plan_id, title="Tech Screen", order=1)
    await create_test_stage(clean_db, plan_id=plan_id, title="System Design", order=2)

    # Call endpoint
    response = await http_client.get(f"/admin/metadata/plans/{plan_id}/stages")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert len(data["stages"]) == 2
    # Verify ordering
    assert data["stages"][0]["title"] == "Tech Screen"
    assert data["stages"][0]["order"] == 1
    assert data["stages"][1]["title"] == "System Design"
    assert data["stages"][1]["order"] == 2


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_interviews_http_endpoint(http_client, clean_db, sample_interview):
    """GET /admin/metadata/interviews returns interviews."""
    # sample_interview fixture already creates an interview

    # Call endpoint
    response = await http_client.get("/admin/metadata/interviews")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "interviews" in data
    assert len(data["interviews"]) >= 1
    # Verify structure
    assert "id" in data["interviews"][0]
    assert "title" in data["interviews"][0]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_metadata_endpoints_have_openapi_schemas(http_client):
    """Metadata endpoints have proper OpenAPI schemas in /docs."""
    response = await http_client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()

    # Verify metadata endpoints exist in OpenAPI spec
    assert "/admin/metadata/jobs" in openapi["paths"]
    assert "/admin/metadata/jobs/{job_id}/plans" in openapi["paths"]
    assert "/admin/metadata/plans/{plan_id}/stages" in openapi["paths"]
    assert "/admin/metadata/interviews" in openapi["paths"]

    # Verify response schemas are defined
    assert "JobsListResponse" in openapi["components"]["schemas"]
    assert "PlansListResponse" in openapi["components"]["schemas"]
    assert "StagesListResponse" in openapi["components"]["schemas"]
    assert "InterviewsListResponse" in openapi["components"]["schemas"]
