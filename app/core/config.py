"""Application configuration."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    model_config = SettingsConfigDict(env_file=".env")

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

    # Frontend (for CORS)
    frontend_url: str = "http://localhost:5173"

    # Advancement automation
    advancement_dry_run_mode: bool = False
    advancement_feedback_timeout_days: int = 7
    advancement_feedback_min_wait_minutes: int = 30
    admin_slack_channel_id: str | None = None
    default_archive_reason_id: str  # Required, not optional

    @property
    def frontend_urls(self) -> list[str]:
        """Parse frontend URLs from comma-separated env var."""
        return [url.strip() for url in self.frontend_url.split(",")]

    @field_validator("default_archive_reason_id")
    @classmethod
    def validate_archive_reason(cls, v: str) -> str:
        """Validate archive reason ID is present."""
        if not v or not v.strip():
            raise ValueError(
                "DEFAULT_ARCHIVE_REASON_ID is required for candidate rejections. "
                "Get this UUID from Ashby: Settings > Archive Reasons"
            )
        return v.strip()


settings = Settings()
