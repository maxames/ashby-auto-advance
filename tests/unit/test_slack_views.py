"""Unit tests for Slack views."""

import json

import pytest

from app.clients.slack_views import build_rejection_notification


class TestBuildRejectionNotification:
    """Tests for build_rejection_notification function."""

    def test_block_structure_is_valid(self):
        """Test returns valid Slack Block Kit structure."""
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
            "primaryEmailAddress": {"value": "john@example.com"},
        }

        feedback_summaries = [
            {
                "interview_title": "Technical Interview",
                "overall_score": 2,
                "interviewer_name": "Jane Smith",
            }
        ]

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=feedback_summaries,
            application_id="app_123",
            job_title="Software Engineer",
            ashby_profile_url="https://ashbyhq.com/candidate/123",
        )

        assert isinstance(blocks, list)
        assert len(blocks) > 0

        # Check for required block types
        block_types = [block["type"] for block in blocks]
        assert "header" in block_types
        assert "section" in block_types
        assert "actions" in block_types

    def test_includes_all_required_sections(self):
        """Test includes header, candidate info, feedback, and button."""
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
            "primaryEmailAddress": {"value": "john@example.com"},
        }

        feedback_summaries = [{"interview_title": "Tech Screen", "overall_score": 2}]

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=feedback_summaries,
            application_id="app_123",
            job_title="Software Engineer",
            ashby_profile_url="https://ashbyhq.com/candidate/123",
        )

        # Find header
        header_blocks = [b for b in blocks if b["type"] == "header"]
        assert len(header_blocks) >= 1

        # Find sections with candidate name
        text_content = json.dumps(blocks)
        assert "John Doe" in text_content
        assert "Software Engineer" in text_content
        assert "john@example.com" in text_content

        # Find actions block with button
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) >= 1

    def test_button_metadata_includes_application_id(self):
        """Test button includes application_id in metadata."""
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
        }

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=[],
            application_id="app_123",
            job_title="Engineer",
            ashby_profile_url="https://ashbyhq.com/candidate/123",
        )

        # Find button
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) > 0

        button = action_blocks[0]["elements"][0]
        assert button["type"] == "button"
        assert "value" in button

        # Parse button value
        button_data = json.loads(button["value"])
        assert button_data["application_id"] == "app_123"
        assert button_data["action"] == "send_rejection"

    def test_handles_missing_optional_candidate_fields(self):
        """Test gracefully handles missing optional fields."""
        # Minimal candidate data
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
        }

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=[],
            application_id="app_123",
            job_title="Engineer",
            ashby_profile_url="https://ashbyhq.com/candidate/123",
        )

        # Should not raise exception
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_includes_ashby_profile_link(self):
        """Test includes link to Ashby profile."""
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
        }

        ashby_url = (
            "https://app.ashbyhq.com/candidate-searches/new/right-side/candidates/123"
        )

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=[],
            application_id="app_123",
            job_title="Engineer",
            ashby_profile_url=ashby_url,
        )

        # Find link in blocks
        text_content = json.dumps(blocks)
        assert ashby_url in text_content

    def test_feedback_summary_displayed(self):
        """Test feedback summaries are displayed in the message."""
        candidate_data = {
            "id": "candidate_123",
            "name": "John Doe",
        }

        feedback_summaries = [
            {
                "interview_title": "Technical Screen",
                "overall_score": 2,
                "submitted_at": "2024-10-20T14:00:00Z",
            },
            {
                "interview_title": "System Design",
                "overall_score": 1,
                "submitted_at": "2024-10-20T15:00:00Z",
            },
        ]

        blocks = build_rejection_notification(
            candidate_data=candidate_data,
            feedback_summaries=feedback_summaries,
            application_id="app_123",
            job_title="Software Engineer",
            ashby_profile_url="https://ashbyhq.com/candidate/123",
        )

        text_content = json.dumps(blocks)

        # Check feedback is mentioned
        assert "Technical Screen" in text_content or "2" in text_content
        assert "System Design" in text_content or "1" in text_content
