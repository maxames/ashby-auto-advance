"""Tests for configuration settings (app/core/config.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_archive_reason_validation_valid():
    """Valid archive reason ID is accepted."""
    settings = Settings(
        database_url="postgresql://localhost/test",
        ashby_webhook_secret="test_secret",
        ashby_api_key="test_key",
        slack_bot_token="xoxb-test",
        slack_signing_secret="test_signing",
        default_archive_reason_id="550e8400-e29b-41d4-a716-446655440000",
    )

    assert settings.default_archive_reason_id == "550e8400-e29b-41d4-a716-446655440000"


def test_archive_reason_validation_empty_raises_error():
    """Empty archive reason ID raises ValueError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            database_url="postgresql://localhost/test",
            ashby_webhook_secret="test_secret",
            ashby_api_key="test_key",
            slack_bot_token="xoxb-test",
            slack_signing_secret="test_signing",
            default_archive_reason_id="",
        )

    # Verify error message
    error_str = str(exc_info.value)
    assert "DEFAULT_ARCHIVE_REASON_ID is required" in error_str


def test_archive_reason_validation_whitespace_raises_error():
    """Whitespace-only archive reason ID raises ValueError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            database_url="postgresql://localhost/test",
            ashby_webhook_secret="test_secret",
            ashby_api_key="test_key",
            slack_bot_token="xoxb-test",
            slack_signing_secret="test_signing",
            default_archive_reason_id="   ",
        )

    error_str = str(exc_info.value)
    assert "DEFAULT_ARCHIVE_REASON_ID is required" in error_str


def test_archive_reason_validation_strips_whitespace():
    """Whitespace around archive reason ID is stripped."""
    settings = Settings(
        database_url="postgresql://localhost/test",
        ashby_webhook_secret="test_secret",
        ashby_api_key="test_key",
        slack_bot_token="xoxb-test",
        slack_signing_secret="test_signing",
        default_archive_reason_id="  550e8400-e29b-41d4-a716-446655440000  ",
    )

    # Verify whitespace was stripped
    assert settings.default_archive_reason_id == "550e8400-e29b-41d4-a716-446655440000"


def test_default_values():
    """Settings model has correct field defaults."""
    # Verify the Settings model has the correct default values defined
    # We check the model schema to see what defaults are defined
    fields = Settings.model_fields

    assert fields["log_level"].default == "INFO"
    assert fields["advancement_dry_run_mode"].default is False
    assert fields["advancement_feedback_timeout_days"].default == 7
    assert fields["advancement_feedback_min_wait_minutes"].default == 30
    assert fields["admin_slack_channel_id"].default is None


def test_settings_from_env_file(monkeypatch):
    """Settings can be loaded from environment variables."""
    # Set environment variables
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test_env")
    monkeypatch.setenv("ASHBY_WEBHOOK_SECRET", "env_webhook_secret")
    monkeypatch.setenv("ASHBY_API_KEY", "env_api_key")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "env_signing_secret")
    monkeypatch.setenv(
        "DEFAULT_ARCHIVE_REASON_ID", "550e8400-e29b-41d4-a716-446655440000"
    )
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ADVANCEMENT_DRY_RUN_MODE", "true")

    settings = Settings()

    assert settings.database_url == "postgresql://localhost/test_env"
    assert settings.log_level == "DEBUG"
    assert settings.advancement_dry_run_mode is True
