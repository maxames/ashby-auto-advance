"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Database
    database_url: str

    # Ashby
    ashby_webhook_secret: str
    ashby_api_key: str

    # Slack
    slack_bot_token: str
    slack_signing_secret: str

    # Application
    log_level: str = "INFO"

    # Advancement automation
    advancement_dry_run_mode: bool = False
    advancement_feedback_timeout_days: int = 7
    advancement_feedback_min_wait_minutes: int = 30
    admin_slack_channel_id: str | None = None
    default_archive_reason_id: str

    class Config:
        """Pydantic configuration."""

        env_file = ".env"


settings = Settings.model_validate({})
