"""Tests for scheduler service (app/services/scheduler.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.scheduler import setup_scheduler, shutdown_scheduler, start_scheduler


def test_setup_scheduler_adds_all_jobs():
    """Setup adds all 6 background jobs."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Verify 6 jobs added
        assert mock_add_job.call_count == 6


def test_setup_scheduler_sync_feedback_job_config():
    """Sync feedback job configured with correct parameters."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the sync_feedback_for_active_schedules call
        calls = mock_add_job.call_args_list
        sync_feedback_call = None
        for call in calls:
            if call[1].get("id") == "sync_feedback":
                sync_feedback_call = call
                break

        assert sync_feedback_call is not None
        kwargs = sync_feedback_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["minutes"] == 30
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1
        assert kwargs["replace_existing"] is True


def test_setup_scheduler_advancement_evaluations_job_config():
    """Advancement evaluations job configured correctly."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the advancement_evaluations call
        calls = mock_add_job.call_args_list
        advancement_call = None
        for call in calls:
            if call[1].get("id") == "advancement_evaluations":
                advancement_call = call
                break

        assert advancement_call is not None
        kwargs = advancement_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["minutes"] == 30
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1


def test_setup_scheduler_refetch_fields_job_config():
    """Refetch advancement fields job configured correctly."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the refetch_advancement_fields call
        calls = mock_add_job.call_args_list
        refetch_call = None
        for call in calls:
            if call[1].get("id") == "refetch_advancement_fields":
                refetch_call = call
                break

        assert refetch_call is not None
        kwargs = refetch_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["hours"] == 1
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1


def test_setup_scheduler_sync_forms_job_config():
    """Sync feedback forms job configured correctly."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the sync_feedback_forms call
        calls = mock_add_job.call_args_list
        sync_forms_call = None
        for call in calls:
            if call[1].get("id") == "sync_feedback_forms":
                sync_forms_call = call
                break

        assert sync_forms_call is not None
        kwargs = sync_forms_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["hours"] == 6
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1


def test_setup_scheduler_sync_interviews_job_config():
    """Sync interviews job configured correctly."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the sync_interviews call
        calls = mock_add_job.call_args_list
        sync_interviews_call = None
        for call in calls:
            if call[1].get("id") == "sync_interviews":
                sync_interviews_call = call
                break

        assert sync_interviews_call is not None
        kwargs = sync_interviews_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["hours"] == 12
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1


def test_setup_scheduler_sync_slack_users_job_config():
    """Sync Slack users job configured correctly."""
    with patch("app.services.scheduler.scheduler.add_job") as mock_add_job:
        setup_scheduler()

        # Find the sync_slack_users call
        calls = mock_add_job.call_args_list
        sync_users_call = None
        for call in calls:
            if call[1].get("id") == "sync_slack_users":
                sync_users_call = call
                break

        assert sync_users_call is not None
        kwargs = sync_users_call[1]
        assert kwargs["trigger"] == "interval"
        assert kwargs["hours"] == 12
        assert kwargs["coalesce"] is True
        assert kwargs["max_instances"] == 1


def test_start_scheduler():
    """Start scheduler calls scheduler.start()."""
    with patch("app.services.scheduler.scheduler.start") as mock_start:
        start_scheduler()

        mock_start.assert_called_once()


def test_shutdown_scheduler():
    """Shutdown scheduler calls scheduler.shutdown(wait=True)."""
    with patch("app.services.scheduler.scheduler.shutdown") as mock_shutdown:
        shutdown_scheduler()

        mock_shutdown.assert_called_once_with(wait=True)
