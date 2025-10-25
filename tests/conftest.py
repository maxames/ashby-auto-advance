"""Pytest configuration for tests."""

import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest_asyncio
from asyncpg import create_pool
from dotenv import load_dotenv

# Load .env.test file if it exists
env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path)

# Set test environment variables before any imports (only if not already set)
os.environ.setdefault("ASHBY_WEBHOOK_SECRET", "test_webhook_secret")
os.environ.setdefault("ASHBY_API_KEY", "test_api_key")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test_signing_secret")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/ashby_feedback_test")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("DEFAULT_ARCHIVE_REASON_ID", "00000000-0000-0000-0000-000000000000")


@pytest_asyncio.fixture
async def db_pool():
    """Create a test database connection pool and initialize app's DB."""
    from app.core import database as db_module
    from app.core.config import settings

    pool = await create_pool(settings.database_url, min_size=1, max_size=5)

    # Initialize the app's database singleton so service functions work
    db_module.db.pool = pool

    yield pool

    # Clean up
    db_module.db.pool = None
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """Clean database before each test."""
    async with db_pool.acquire() as conn:
        # Clear all tables in reverse dependency order
        await conn.execute("DELETE FROM advancement_executions")
        await conn.execute("DELETE FROM advancement_rule_actions")
        await conn.execute("DELETE FROM advancement_rule_requirements")
        await conn.execute("DELETE FROM advancement_rules")
        await conn.execute("DELETE FROM feedback_submissions")
        await conn.execute("DELETE FROM interview_assignments")
        await conn.execute("DELETE FROM interview_events")
        await conn.execute("DELETE FROM interview_schedules")
        await conn.execute("DELETE FROM feedback_form_definitions")
        await conn.execute("DELETE FROM interviews")
        await conn.execute("DELETE FROM slack_users")
        await conn.execute("DELETE FROM ashby_webhook_payloads")
        await conn.execute("DELETE FROM interview_stages")
        await conn.execute("DELETE FROM job_interview_plans")
        await conn.execute("DELETE FROM interview_plans")
        await conn.execute("DELETE FROM jobs")

    yield db_pool


@pytest_asyncio.fixture
async def sample_slack_user(clean_db):
    """Create a sample Slack user in the database."""
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO slack_users
            (slack_user_id, email, real_name, display_name, is_bot, deleted, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """,
            "U123456",
            "test@example.com",
            "Test User",
            "testuser",
            False,
            False,
        )

    return {"slack_user_id": "U123456", "email": "test@example.com"}


@pytest_asyncio.fixture
async def sample_interview(clean_db):
    """Create a sample interview definition in the database."""
    interview_id = uuid4()
    form_def_id = uuid4()
    job_id = uuid4()

    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interviews
            (interview_id, title, external_title, is_archived, is_debrief,
             instructions_html, instructions_plain, job_id,
             feedback_form_definition_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            """,
            interview_id,
            "Technical Interview",
            "Tech Screen",
            False,
            False,
            "<p>Instructions</p>",
            "Instructions",
            job_id,
            form_def_id,
        )

    return {
        "interview_id": str(interview_id),
        "form_definition_id": str(form_def_id),
        "job_id": str(job_id),
    }


@pytest_asyncio.fixture
async def sample_feedback_form(clean_db):
    """Create a sample feedback form definition in the database."""
    import json

    form_def_id = uuid4()

    form_definition = {
        "id": str(form_def_id),
        "title": "Technical Interview Feedback",
        "formDefinition": {
            "sections": [
                {
                    "title": "Assessment",
                    "fields": [
                        {
                            "field": {
                                "path": "overall_score",
                                "type": "Score",
                                "title": "Overall Score",
                            },
                            "isRequired": True,
                        }
                    ],
                }
            ]
        },
    }

    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feedback_form_definitions
            (form_definition_id, title, definition, is_archived, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            form_def_id,
            "Technical Interview Feedback",
            json.dumps(form_definition),
            False,
        )

    return form_definition


@pytest_asyncio.fixture
async def sample_interview_event(clean_db, sample_interview, sample_slack_user) -> dict[str, Any]:
    """Create a complete interview event for feedback tests."""
    schedule_id = uuid4()
    event_id = uuid4()
    application_id = uuid4()
    stage_id = uuid4()
    interviewer_id = uuid4()

    async with clean_db.acquire() as conn:
        # Create schedule
        await conn.execute(
            """
            INSERT INTO interview_schedules
            (schedule_id, application_id, interview_stage_id, status, candidate_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            """,
            schedule_id,
            application_id,
            stage_id,
            "Scheduled",
            "candidate_test",
        )

        # Create event
        # Note: UUID() conversion is used here for database INSERT operations
        # because asyncpg expects UUID type for UUID columns. Service layer
        # functions should receive string UUIDs per production type hints.
        await conn.execute(
            """
            INSERT INTO interview_events
            (event_id, schedule_id, interview_id, created_at, updated_at,
             start_time, end_time, feedback_link, location, meeting_link,
             has_submitted_feedback, extra_data)
            VALUES ($1, $2, $3, NOW(), NOW(), NOW() + INTERVAL '1 hour', NOW() + INTERVAL '2 hours',
                    $4, $5, $6, $7, $8)
            """,
            event_id,
            schedule_id,
            UUID(sample_interview["interview_id"]),  # Convert string to UUID
            "https://ashby.com/feedback",
            "Zoom",
            "https://zoom.us/test",
            False,
            "{}",
        )

        # Create interviewer assignment
        await conn.execute(
            """
            INSERT INTO interview_assignments
            (event_id, interviewer_id, first_name, last_name, email,
             global_role, training_role, is_enabled, manager_id,
             interviewer_pool_id, interviewer_pool_title,
             interviewer_pool_is_archived, training_path, interviewer_updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
            """,
            event_id,
            interviewer_id,
            "Test",
            "User",
            "test@example.com",
            "Interviewer",
            "Trained",
            True,
            None,
            uuid4(),
            "Test Pool",
            False,
            "{}",
        )

    return {
        "event_id": str(event_id),
        "schedule_id": str(schedule_id),
        "interviewer_id": str(interviewer_id),
        "application_id": str(application_id),
    }


@pytest_asyncio.fixture
async def sample_advancement_rule(clean_db, sample_interview):
    """Create a sample advancement rule with requirements and actions."""
    import json

    rule_id = uuid4()
    requirement_id = uuid4()
    action_id = uuid4()
    interview_plan_id = uuid4()
    interview_stage_id = uuid4()
    target_stage_id = uuid4()

    async with clean_db.acquire() as conn:
        # Create rule
        await conn.execute(
            """
            INSERT INTO advancement_rules
            (rule_id, job_id, interview_plan_id, interview_stage_id,
             target_stage_id, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, true, NOW(), NOW())
            """,
            rule_id,
            None,  # job_id NULL = applies to all jobs
            interview_plan_id,
            interview_stage_id,
            target_stage_id,
        )

        # Create requirement
        await conn.execute(
            """
            INSERT INTO advancement_rule_requirements
            (requirement_id, rule_id, interview_id, score_field_path,
             operator, threshold_value, is_required, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
            """,
            requirement_id,
            rule_id,
            UUID(sample_interview["interview_id"]),
            "overall_score",
            ">=",
            "3",
        )

        # Create action
        await conn.execute(
            """
            INSERT INTO advancement_rule_actions
            (action_id, rule_id, action_type, action_config, execution_order, created_at)
            VALUES ($1, $2, $3, $4, 1, NOW())
            """,
            action_id,
            rule_id,
            "advance_stage",
            json.dumps({}),
        )

    return {
        "rule_id": str(rule_id),
        "requirement_id": str(requirement_id),
        "action_id": str(action_id),
        "interview_plan_id": str(interview_plan_id),
        "interview_stage_id": str(interview_stage_id),
        "target_stage_id": str(target_stage_id),
        "interview_id": sample_interview["interview_id"],
    }


@pytest_asyncio.fixture
async def sample_feedback_submission(clean_db, sample_interview_event):
    """Create a sample feedback submission."""
    import json

    feedback_id = uuid4()
    event_id = UUID(sample_interview_event["event_id"])
    application_id = UUID(sample_interview_event["application_id"])
    interviewer_id = UUID(sample_interview_event["interviewer_id"])

    async with clean_db.acquire() as conn:
        # Get interview_id from the event
        interview_id = await conn.fetchval(
            "SELECT interview_id FROM interview_events WHERE event_id = $1", event_id
        )

        await conn.execute(
            """
            INSERT INTO feedback_submissions
            (feedback_id, application_id, event_id, interviewer_id, interview_id,
             submitted_at, submitted_values, processed_for_advancement_at, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW() - INTERVAL '1 hour', $6, NULL, NOW())
            """,
            feedback_id,
            application_id,
            event_id,
            interviewer_id,
            interview_id,
            json.dumps({"overall_score": 4, "technical_skills": 5}),
        )

    return {
        "feedback_id": str(feedback_id),
        "event_id": sample_interview_event["event_id"],
        "application_id": sample_interview_event["application_id"],
        "interviewer_id": sample_interview_event["interviewer_id"],
        "submitted_values": {"overall_score": 4, "technical_skills": 5},
    }


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end HTTP tests (slower)")
    config.addinivalue_line("markers", "unit: marks tests as unit tests (fast)")
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (medium speed)"
    )
