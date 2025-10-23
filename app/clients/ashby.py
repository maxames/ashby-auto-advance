"""Ashby API client for feedback forms and candidate information."""

from __future__ import annotations

import base64
from typing import Any, cast

import aiohttp
from structlog import get_logger

from app.core.config import settings
from app.types.ashby import (
    ApplicationChangeStageResponseTD,
    CandidateTD,
    FeedbackSubmissionTD,
    InterviewStageTD,
    JobInfoTD,
)

logger = get_logger()


class AshbyClient:
    """HTTP client for Ashby API with Basic Auth."""

    def __init__(self) -> None:
        """Initialize Ashby client with API key from settings."""
        self.api_key = settings.ashby_api_key
        self.base_url = "https://api.ashbyhq.com"
        self.timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout

        # Basic auth: base64(api_key:)
        credentials = base64.b64encode(f"{self.api_key}:".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json; version=1",
            "Content-Type": "application/json",
        }

    async def post(self, endpoint: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """
        Make POST request to Ashby API.

        Args:
            endpoint: API endpoint (e.g., "candidate.info")
            json_data: Request body

        Returns:
            Response JSON dict

        Raises:
            aiohttp.ClientError: On request failure
        """
        url = f"{self.base_url}/{endpoint}"

        logger.info("ashby_api_request", endpoint=endpoint)

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, json=json_data, headers=self.headers) as response:
                response.raise_for_status()
                result: dict[str, Any] = await response.json()

                if not result.get("success"):
                    # Extract error from multiple possible fields
                    error_msg = result.get("errors") or result.get("error") or "Unknown error"
                    error_info = result.get("errorInfo", {})

                    logger.error(
                        "ashby_api_error",
                        endpoint=endpoint,
                        errors=error_msg,
                        error_code=(
                            error_info.get("code") if isinstance(error_info, dict) else None
                        ),
                        request_id=(
                            error_info.get("requestId") if isinstance(error_info, dict) else None
                        ),
                    )

                    # Raise exception to stop execution
                    error_display = error_msg if isinstance(error_msg, str) else str(error_msg)
                    raise Exception(f"Ashby API request failed ({endpoint}): {error_display}")

                return result


# Module-level singleton
ashby_client = AshbyClient()


async def fetch_candidate_info(candidate_id: str) -> CandidateTD:
    """
    Fetch candidate details from Ashby API.

    Args:
        candidate_id: Ashby candidate UUID

    Returns:
        Candidate data (typed)

    Raises:
        Exception: If API call fails
    """
    response = await ashby_client.post("candidate.info", {"id": candidate_id})

    if not response["success"]:
        raise Exception(f"Ashby API request failed (candidate.info): {response.get('error')}")

    data = response["results"]

    # Sanity check critical fields
    if "id" not in data or "name" not in data:
        raise ValueError(f"Invalid candidate payload for {candidate_id}")

    return cast(CandidateTD, data)


async def fetch_job_info(job_id: str) -> JobInfoTD:
    """
    Fetch job details from Ashby API.

    Args:
        job_id: Ashby job UUID

    Returns:
        Job data (typed)

    Raises:
        Exception: If API call fails
    """
    response = await ashby_client.post("job.info", {"id": job_id})

    if not response["success"]:
        raise Exception(f"Ashby API request failed (job.info): {response.get('error')}")

    data = response["results"]

    if "id" not in data or "title" not in data:
        raise ValueError(f"Invalid job payload for {job_id}")

    return cast(JobInfoTD, data)


async def fetch_resume_url(file_handle: str) -> str | None:
    """
    Convert Ashby file handle to actual S3 URL.

    Args:
        file_handle: Ashby file handle

    Returns:
        S3 URL or None if fetch fails
    """
    try:
        response = await ashby_client.post("file.info", {"fileHandle": file_handle})

        if response["success"]:
            return str(response["results"]["url"])

        logger.warning("file_info_failed", handle=file_handle)
        return None
    except Exception as e:
        logger.error("file_fetch_error", error=str(e))
        return None


async def fetch_application_feedback(application_id: str) -> list[FeedbackSubmissionTD]:
    """
    Fetch all feedback submissions for an application from Ashby API.

    Handles pagination automatically.

    Args:
        application_id: Ashby application UUID

    Returns:
        List of feedback submissions (typed)

    Raises:
        Exception: If API call fails
    """
    all_submissions: list[FeedbackSubmissionTD] = []
    cursor: str | None = None

    while True:
        request_data: dict[str, Any] = {
            "applicationId": application_id,
            "limit": 100,
        }
        if cursor:
            request_data["cursor"] = cursor

        response = await ashby_client.post("applicationFeedback.list", request_data)

        if not response["success"]:
            raise Exception(
                f"Ashby API request failed (applicationFeedback.list): {response.get('error')}"
            )

        results = response.get("results", [])
        all_submissions.extend(cast(list[FeedbackSubmissionTD], results))

        # Check for next page
        next_cursor = response.get("nextCursor")
        if not next_cursor:
            break
        cursor = next_cursor

    logger.info(
        "application_feedback_fetched",
        application_id=application_id,
        count=len(all_submissions),
    )

    return all_submissions


async def fetch_interview_stage_info(stage_id: str) -> InterviewStageTD:
    """
    Fetch interview stage details from Ashby API.

    Args:
        stage_id: Ashby interview stage UUID

    Returns:
        Interview stage data (typed)

    Raises:
        Exception: If API call fails
    """
    response = await ashby_client.post("interviewStage.info", {"interviewStageId": stage_id})

    if not response["success"]:
        raise Exception(f"Ashby API request failed (interviewStage.info): {response.get('error')}")

    return cast(InterviewStageTD, response["results"])


async def list_interview_stages_for_plan(
    interview_plan_id: str,
) -> list[InterviewStageTD]:
    """
    List all interview stages for an interview plan.

    Returns stages ordered by orderInInterviewPlan.

    Args:
        interview_plan_id: Ashby interview plan UUID

    Returns:
        List of interview stages (typed, sorted by order)

    Raises:
        Exception: If API call fails
    """
    response = await ashby_client.post(
        "interviewStage.list",
        {"interviewPlanId": interview_plan_id},
    )

    if not response["success"]:
        raise Exception(f"Ashby API request failed (interviewStage.list): {response.get('error')}")

    stages = cast(list[InterviewStageTD], response.get("results", []))

    # Sort by orderInInterviewPlan
    stages.sort(key=lambda s: s["orderInInterviewPlan"])

    logger.info(
        "interview_stages_listed",
        interview_plan_id=interview_plan_id,
        count=len(stages),
    )

    return stages


async def advance_candidate_stage(
    application_id: str, target_stage_id: str
) -> ApplicationChangeStageResponseTD:
    """
    Advance candidate to target interview stage.

    Args:
        application_id: Ashby application UUID
        target_stage_id: Target interview stage UUID

    Returns:
        Updated application data (typed)

    Raises:
        Exception: If API call fails
    """
    response = await ashby_client.post(
        "application.changeStage",
        {
            "applicationId": application_id,
            "interviewStageId": target_stage_id,
        },
    )

    if not response["success"]:
        raise Exception(
            f"Ashby API request failed (application.changeStage): {response.get('error')}"
        )

    logger.info(
        "candidate_advanced",
        application_id=application_id,
        target_stage_id=target_stage_id,
    )

    return cast(ApplicationChangeStageResponseTD, response["results"])


async def archive_candidate(
    application_id: str,
    archive_reason_id: str,
    communication_template_id: str | None = None,
) -> dict[str, Any]:
    """
    Archive candidate application with optional rejection email.

    Args:
        application_id: Ashby application UUID
        archive_reason_id: Archive reason UUID
        communication_template_id: Optional email template UUID

    Returns:
        Updated application data

    Raises:
        Exception: If API call fails
    """
    request_data: dict[str, Any] = {
        "applicationId": application_id,
        "archiveReasonId": archive_reason_id,
    }

    if communication_template_id:
        request_data["archiveEmail"] = {
            "communicationTemplateId": communication_template_id,
        }

    response = await ashby_client.post("application.changeStage", request_data)

    if not response["success"]:
        raise Exception(
            f"Ashby API request failed (application.changeStage/archive): {response.get('error')}"
        )

    logger.info(
        "candidate_archived",
        application_id=application_id,
        archive_reason_id=archive_reason_id,
        sent_email=communication_template_id is not None,
    )

    return response["results"]
