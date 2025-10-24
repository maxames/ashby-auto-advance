"""Tests for Ashby API client (app/clients/ashby.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import respx
from httpx import Response

from app.clients.ashby import (
    advance_candidate_stage,
    archive_candidate,
    fetch_application_feedback,
    fetch_interview_stage_info,
    list_interview_stages_for_plan,
)


@pytest.mark.asyncio
async def test_fetch_application_feedback_success():
    """Returns list of feedback submissions."""
    application_id = str(uuid4())
    feedback_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": [
            {
                "id": feedback_id,
                "applicationId": application_id,
                "submittedValues": {"overall_score": 4},
                "submittedAt": "2024-10-20T14:00:00.000Z",
            }
        ],
        "moreDataAvailable": False,
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await fetch_application_feedback(application_id)

        assert len(result) == 1
        assert result[0]["id"] == feedback_id


@pytest.mark.asyncio
async def test_fetch_application_feedback_pagination():
    """Handles multiple pages of feedback."""
    application_id = str(uuid4())

    # First page
    page1_response = {
        "success": True,
        "results": [{"id": str(uuid4()), "applicationId": application_id}],
        "moreDataAvailable": True,
        "nextCursor": "cursor123",
    }

    # Second page
    page2_response = {
        "success": True,
        "results": [{"id": str(uuid4()), "applicationId": application_id}],
        "moreDataAvailable": False,
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [page1_response, page2_response]

        result = await fetch_application_feedback(application_id)

        # Should have combined results from both pages
        assert len(result) == 2
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_fetch_interview_stage_info_success():
    """Returns stage info with interviewPlanId."""
    stage_id = str(uuid4())
    plan_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": {
            "id": stage_id,
            "title": "Technical Screen",
            "interviewPlanId": plan_id,
            "orderInInterviewPlan": 2,
        },
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await fetch_interview_stage_info(stage_id)

        assert result["id"] == stage_id
        assert result["interviewPlanId"] == plan_id


@pytest.mark.asyncio
async def test_fetch_interview_stage_info_not_found():
    """Handles API errors gracefully."""
    stage_id = str(uuid4())

    mock_response = {
        "success": False,
        "error": "Stage not found",
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # Should raise exception for non-success response
        with pytest.raises(Exception) as exc_info:
            await fetch_interview_stage_info(stage_id)

        assert "Stage not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_advance_candidate_stage_success():
    """Returns success response."""
    application_id = str(uuid4())
    stage_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": {
            "id": application_id,
            "currentInterviewStage": {
                "id": stage_id,
                "title": "Final Interview",
            },
        },
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await advance_candidate_stage(application_id, stage_id)

        # Function returns just the results portion
        assert result["id"] == application_id
        assert result["currentInterviewStage"]["id"] == stage_id


@pytest.mark.asyncio
async def test_advance_candidate_stage_verifies_parameters():
    """Verifies correct API parameters are passed."""
    application_id = str(uuid4())
    stage_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": {"id": application_id},
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await advance_candidate_stage(application_id, stage_id)

        # Verify correct parameters were passed to API
        call_args = mock_post.call_args[0]
        assert call_args[0] == "application.changeStage"
        assert call_args[1]["applicationId"] == application_id
        assert call_args[1]["interviewStageId"] == stage_id


@pytest.mark.asyncio
async def test_list_interview_stages_for_plan_success():
    """Returns list of stages in order."""
    plan_id = str(uuid4())
    stage1_id = str(uuid4())
    stage2_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": [
            {
                "id": stage1_id,
                "title": "Phone Screen",
                "orderInInterviewPlan": 1,
                "interviewPlanId": plan_id,
            },
            {
                "id": stage2_id,
                "title": "Technical Interview",
                "orderInInterviewPlan": 2,
                "interviewPlanId": plan_id,
            },
        ],
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await list_interview_stages_for_plan(plan_id)

        assert len(result) == 2
        assert result[0]["orderInInterviewPlan"] == 1
        assert result[1]["orderInInterviewPlan"] == 2


@pytest.mark.asyncio
async def test_list_interview_stages_for_plan_empty():
    """Handles empty results."""
    plan_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": [],
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await list_interview_stages_for_plan(plan_id)

        assert result == []


@pytest.mark.asyncio
async def test_archive_candidate_success():
    """Archives candidate with reason."""
    application_id = str(uuid4())
    archive_reason_id = str(uuid4())

    mock_response = {
        "success": True,
        "results": {
            "id": application_id,
            "archivedAt": "2024-10-20T14:00:00.000Z",
        },
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await archive_candidate(application_id, archive_reason_id)

        # Function returns just the results portion
        assert result["id"] == application_id
        assert "archivedAt" in result

        # Verify correct parameters were passed
        call_args = mock_post.call_args[0]
        assert call_args[1]["applicationId"] == application_id
        assert call_args[1]["archiveReasonId"] == archive_reason_id


@pytest.mark.asyncio
async def test_ashby_client_api_error_handling():
    """Non-success responses raise exceptions."""
    application_id = str(uuid4())

    mock_response = {
        "success": False,
        "error": "Application not found",
    }

    with patch("app.clients.ashby.ashby_client.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # Should raise exception for non-success response
        with pytest.raises(Exception) as exc_info:
            await fetch_application_feedback(application_id)

        assert "Application not found" in str(exc_info.value)
