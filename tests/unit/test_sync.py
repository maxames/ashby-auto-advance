"""Tests for sync operations (app/services/sync.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import sync as sync_module


@pytest.mark.asyncio
async def test_sync_feedback_forms_fetches_and_stores(clean_db):
    """Forms fetched from API and inserted into DB."""
    form_id = str(uuid4())
    mock_form = {
        "id": form_id,
        "title": "Technical Interview Feedback",
        "isArchived": False,
    }

    mock_response = {
        "success": True,
        "results": [mock_form],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await sync_module.sync_feedback_forms()

        # Verify API was called
        mock_post.assert_called_once()

        # Verify form was stored in database
        async with clean_db.acquire() as conn:
            form = await conn.fetchrow(
                "SELECT * FROM feedback_form_definitions WHERE form_definition_id = $1",
                form_id,
            )
            assert form is not None
            assert form["title"] == "Technical Interview Feedback"


@pytest.mark.asyncio
async def test_sync_feedback_forms_handles_pagination(clean_db):
    """Continues fetching until moreDataAvailable is False."""
    form1_id = str(uuid4())
    form2_id = str(uuid4())

    # First page
    page1_response = {
        "success": True,
        "results": [{"id": form1_id, "title": "Form 1", "isArchived": False}],
        "moreDataAvailable": True,
        "nextCursor": "cursor123",
    }

    # Second page
    page2_response = {
        "success": True,
        "results": [{"id": form2_id, "title": "Form 2", "isArchived": False}],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.side_effect = [page1_response, page2_response]

        await sync_module.sync_feedback_forms()

        # Verify API was called twice
        assert mock_post.call_count == 2

        # Verify both forms stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_form_definitions"
            )
            assert count == 2


@pytest.mark.asyncio
async def test_sync_feedback_forms_upserts_existing_forms(clean_db):
    """ON CONFLICT updates existing forms."""
    form_id = str(uuid4())

    # Insert initial form
    async with clean_db.acquire() as conn:
        import json

        await conn.execute(
            """
            INSERT INTO feedback_form_definitions
            (form_definition_id, title, definition, is_archived, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            """,
            form_id,
            "Old Title",
            json.dumps({"id": form_id}),
            False,
        )

    # Sync with updated title
    mock_form = {
        "id": form_id,
        "title": "New Title",
        "isArchived": False,
    }

    mock_response = {
        "success": True,
        "results": [mock_form],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await sync_module.sync_feedback_forms()

        # Verify form was updated
        async with clean_db.acquire() as conn:
            form = await conn.fetchrow(
                "SELECT * FROM feedback_form_definitions WHERE form_definition_id = $1",
                form_id,
            )
            assert form["title"] == "New Title"


@pytest.mark.asyncio
async def test_sync_feedback_forms_api_error_handled(clean_db):
    """API errors logged, doesn't crash."""
    mock_response = {
        "success": False,
        "error": "API Error",
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        # Should not raise exception
        await sync_module.sync_feedback_forms()

        # Verify no forms were stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM feedback_form_definitions"
            )
            assert count == 0


@pytest.mark.asyncio
async def test_sync_interviews_fetches_and_stores(clean_db):
    """Interviews fetched and inserted."""
    interview_id = str(uuid4())
    job_id = str(uuid4())
    form_id = str(uuid4())

    mock_interview = {
        "id": interview_id,
        "title": "Technical Interview",
        "externalTitle": "Tech Screen",
        "isArchived": False,
        "isDebrief": False,
        "instructionsHtml": "<p>Instructions</p>",
        "instructionsPlain": "Instructions",
        "jobId": job_id,
        "feedbackFormDefinitionId": form_id,
    }

    mock_response = {
        "success": True,
        "results": [mock_interview],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await sync_module.sync_interviews()

        # Verify interview was stored
        async with clean_db.acquire() as conn:
            interview = await conn.fetchrow(
                "SELECT * FROM interviews WHERE interview_id = $1",
                interview_id,
            )
            assert interview is not None
            assert interview["title"] == "Technical Interview"


@pytest.mark.asyncio
async def test_sync_interviews_handles_pagination(clean_db):
    """Pagination loop works correctly."""
    interview1_id = str(uuid4())
    interview2_id = str(uuid4())

    # First page
    page1_response = {
        "success": True,
        "results": [{"id": interview1_id, "title": "Interview 1"}],
        "moreDataAvailable": True,
        "nextCursor": "cursor123",
    }

    # Second page
    page2_response = {
        "success": True,
        "results": [{"id": interview2_id, "title": "Interview 2"}],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.side_effect = [page1_response, page2_response]

        await sync_module.sync_interviews()

        # Verify both interviews stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM interviews")
            assert count == 2


@pytest.mark.asyncio
async def test_sync_interviews_upserts_existing_interviews(clean_db):
    """Existing interviews updated."""
    interview_id = str(uuid4())

    # Insert initial interview
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
            "Old Title",
            "Old External",
            False,
            False,
            None,
            None,
            None,
            None,
        )

    # Sync with updated title
    mock_interview = {
        "id": interview_id,
        "title": "New Title",
        "externalTitle": "New External",
    }

    mock_response = {
        "success": True,
        "results": [mock_interview],
        "moreDataAvailable": False,
    }

    with patch(
        "app.services.sync.ashby_client.post", new_callable=AsyncMock
    ) as mock_post:
        mock_post.return_value = mock_response

        await sync_module.sync_interviews()

        # Verify interview was updated
        async with clean_db.acquire() as conn:
            interview = await conn.fetchrow(
                "SELECT * FROM interviews WHERE interview_id = $1",
                interview_id,
            )
            assert interview["title"] == "New Title"


@pytest.mark.asyncio
async def test_sync_slack_users_fetches_and_stores(clean_db):
    """Slack users fetched and inserted."""
    mock_user = {
        "id": "U123456",
        "is_bot": False,
        "deleted": False,
        "real_name": "Test User",
        "profile": {
            "email": "test@example.com",
            "display_name": "testuser",
        },
    }

    mock_response = {
        "ok": True,
        "members": [mock_user],
    }

    with patch(
        "app.services.sync.slack_client.client.users_list", new_callable=AsyncMock
    ) as mock_users_list:
        mock_users_list.return_value = mock_response

        await sync_module.sync_slack_users()

        # Verify user was stored
        async with clean_db.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM slack_users WHERE slack_user_id = $1",
                "U123456",
            )
            assert user is not None
            assert user["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_sync_slack_users_filters_bots(clean_db):
    """is_bot=True users skipped."""
    mock_bot = {
        "id": "B123456",
        "is_bot": True,
        "deleted": False,
        "profile": {"email": "bot@example.com"},
    }

    mock_response = {
        "ok": True,
        "members": [mock_bot],
    }

    with patch(
        "app.services.sync.slack_client.client.users_list", new_callable=AsyncMock
    ) as mock_users_list:
        mock_users_list.return_value = mock_response

        await sync_module.sync_slack_users()

        # Verify bot was NOT stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM slack_users")
            assert count == 0


@pytest.mark.asyncio
async def test_sync_slack_users_filters_deleted(clean_db):
    """deleted=True users skipped."""
    mock_deleted_user = {
        "id": "U123456",
        "is_bot": False,
        "deleted": True,
        "profile": {"email": "deleted@example.com"},
    }

    mock_response = {
        "ok": True,
        "members": [mock_deleted_user],
    }

    with patch(
        "app.services.sync.slack_client.client.users_list", new_callable=AsyncMock
    ) as mock_users_list:
        mock_users_list.return_value = mock_response

        await sync_module.sync_slack_users()

        # Verify deleted user was NOT stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM slack_users")
            assert count == 0


@pytest.mark.asyncio
async def test_sync_slack_users_filters_no_email(clean_db):
    """Users without email skipped."""
    mock_user_no_email = {
        "id": "U123456",
        "is_bot": False,
        "deleted": False,
        "real_name": "Test User",
        "profile": {
            "display_name": "testuser",
            # No email field
        },
    }

    mock_response = {
        "ok": True,
        "members": [mock_user_no_email],
    }

    with patch(
        "app.services.sync.slack_client.client.users_list", new_callable=AsyncMock
    ) as mock_users_list:
        mock_users_list.return_value = mock_response

        await sync_module.sync_slack_users()

        # Verify user without email was NOT stored
        async with clean_db.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM slack_users")
            assert count == 0


@pytest.mark.asyncio
async def test_sync_slack_users_upserts_existing_users(clean_db):
    """Existing users updated."""
    # Insert initial user
    async with clean_db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO slack_users
            (slack_user_id, email, real_name, display_name, is_bot, deleted, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """,
            "U123456",
            "old@example.com",
            "Old Name",
            "oldname",
            False,
            False,
        )

    # Sync with updated email
    mock_user = {
        "id": "U123456",
        "is_bot": False,
        "deleted": False,
        "real_name": "New Name",
        "profile": {
            "email": "new@example.com",
            "display_name": "newname",
        },
    }

    mock_response = {
        "ok": True,
        "members": [mock_user],
    }

    with patch(
        "app.services.sync.slack_client.client.users_list", new_callable=AsyncMock
    ) as mock_users_list:
        mock_users_list.return_value = mock_response

        await sync_module.sync_slack_users()

        # Verify user was updated
        async with clean_db.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM slack_users WHERE slack_user_id = $1",
                "U123456",
            )
            assert user["email"] == "new@example.com"
            assert user["real_name"] == "New Name"
