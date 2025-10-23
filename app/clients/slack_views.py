"""Slack Block Kit views for modals and messages."""

from __future__ import annotations

import json
from typing import Any

from structlog import get_logger

from app.types.ashby import CandidateTD

logger = get_logger()


def build_rejection_notification(
    candidate_data: CandidateTD,
    feedback_summaries: list[dict[str, Any]],
    application_id: str,
    job_title: str,
    ashby_profile_url: str,
) -> list[dict[str, Any]]:
    """
    Build Slack notification for candidate who failed advancement criteria.

    Includes candidate info, feedback summary, and action button to send rejection.

    Args:
        candidate_data: Candidate info from Ashby
        feedback_summaries: List of feedback data with scores
        application_id: Application UUID
        job_title: Job title
        ashby_profile_url: Direct link to candidate profile in Ashby

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    # Header
    candidate_name = candidate_data.get("name", "Candidate")
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️  Candidate Did Not Meet Advancement Criteria",
            },
        }
    )

    # Candidate Information
    primary_email = candidate_data.get("primaryEmailAddress", {}).get("value", "")
    primary_phone = candidate_data.get("primaryPhoneNumber", {}).get("value", "")
    position = candidate_data.get("position", "")
    company = candidate_data.get("company", "")

    info_text = f"*{candidate_name}*\n"
    info_text += f"Position: {job_title}\n"
    if primary_email:
        info_text += f"📧 {primary_email}\n"
    if primary_phone:
        info_text += f"📱 {primary_phone}\n"
    if position and company:
        info_text += f"Current: {position} at {company}"

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": info_text}})

    # Ashby Profile Link
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{ashby_profile_url}|View Profile in Ashby>",
            },
        }
    )

    blocks.append({"type": "divider"})

    # Feedback Summary
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📋 Interview Feedback Summary*"},
        }
    )

    for feedback in feedback_summaries:
        interview_title = feedback.get("interview_title", "Interview")
        scores = feedback.get("scores", {})

        # Build scores text
        scores_text = ""
        for field_path, value in scores.items():
            # Format field path nicely (e.g., "overall_score" -> "Overall Score")
            field_name = field_path.replace("_", " ").title()
            scores_text += f"• {field_name}: {value}\n"

        feedback_text = f"*{interview_title}*\n{scores_text}"
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": feedback_text}}
        )

    blocks.append({"type": "divider"})

    # Action Button - Send Rejection
    button_metadata = json.dumps(
        {"application_id": application_id, "action": "send_rejection"}
    )

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Archive & Send Rejection Email",
                    },
                    "style": "danger",
                    "action_id": "send_rejection",
                    "value": button_metadata,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Confirm Rejection"},
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"Are you sure you want to archive {candidate_name} "
                                "and send a rejection email?"
                            ),
                        },
                        "confirm": {
                            "type": "plain_text",
                            "text": "Yes, Send Rejection",
                        },
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                }
            ],
        }
    )

    # Footer
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "_This candidate was automatically flagged because they did not "
                        "meet the scoring thresholds for advancement._"
                    ),
                }
            ],
        }
    )

    return blocks
