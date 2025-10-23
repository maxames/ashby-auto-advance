"""Test fixtures and factories."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4


def create_interview_event(
    event_id: str = "event_test",
    schedule_id: str = "schedule_test",
    interview_id: str = "interview_test",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    interviewer_email: str = "test@example.com",
) -> dict:
    """Create test interview event data."""
    if start_time is None:
        start_time = datetime.now(UTC) + timedelta(minutes=10)
    if end_time is None:
        end_time = start_time + timedelta(hours=1)

    return {
        "event_id": event_id,
        "schedule_id": schedule_id,
        "interview_id": interview_id,
        "start_time": start_time,
        "end_time": end_time,
        "interviewer_email": interviewer_email,
        "slack_user_id": "U123456",
        "interview_title": "Technical Interview",
        "feedback_form_definition_id": "form_def_123",
        "candidate_id": "candidate_789",
        "application_id": "app_456",
        "interviewer_id": "interviewer_111",
    }


def create_feedback_draft(
    event_id: str = "event_test",
    interviewer_id: str = "interviewer_test",
    form_values: dict | None = None,
) -> dict:
    """Create test feedback draft data."""
    if form_values is None:
        form_values = {"overall_score": "3", "notes": "Test feedback notes"}

    return {
        "event_id": event_id,
        "interviewer_id": interviewer_id,
        "form_values": form_values,
    }


def create_ashby_webhook_payload(
    schedule_id: str = "schedule_test",
    status: str = "Scheduled",
    event_id: str = "event_test",
) -> dict:
    """Create test Ashby webhook payload."""
    return {
        "action": "interviewScheduleUpdate",
        "data": {
            "interviewSchedule": {
                "id": schedule_id,
                "status": status,
                "applicationId": "app_test",
                "candidateId": "candidate_test",
                "interviewStageId": "stage_test",
                "interviewEvents": [
                    {
                        "id": event_id,
                        "interviewId": "interview_test",
                        "startTime": "2024-10-20T14:00:00.000Z",
                        "endTime": "2024-10-20T15:00:00.000Z",
                        "feedbackLink": "https://ashby.com/feedback",
                        "location": "Zoom",
                        "meetingLink": "https://zoom.us/test",
                        "hasSubmittedFeedback": False,
                        "createdAt": "2024-10-19T10:00:00.000Z",
                        "updatedAt": "2024-10-19T10:00:00.000Z",
                        "extraData": {},
                        "interviewers": [
                            {
                                "id": "interviewer_test",
                                "firstName": "Test",
                                "lastName": "User",
                                "email": "test@example.com",
                                "globalRole": "Interviewer",
                                "trainingRole": "Trained",
                                "isEnabled": True,
                                "updatedAt": "2024-10-19T10:00:00.000Z",
                                "interviewerPool": {
                                    "id": "pool_test",
                                    "title": "Test Pool",
                                    "isArchived": False,
                                    "trainingPath": {},
                                },
                            }
                        ],
                    }
                ],
            }
        },
    }


async def create_test_rule(
    db_pool,
    interview_plan_id: str | None = None,
    interview_stage_id: str | None = None,
    interview_id: str | None = None,
    target_stage_id: str | None = None,
    job_id: str | None = None,
    score_field: str = "overall_score",
    operator: str = ">=",
    threshold: str = "3",
) -> dict:
    """Insert an advancement rule into the database for testing."""
    import json
    from uuid import UUID

    if interview_plan_id is None:
        interview_plan_id = str(uuid4())
    if interview_stage_id is None:
        interview_stage_id = str(uuid4())
    if interview_id is None:
        interview_id = str(uuid4())
    if target_stage_id is None:
        target_stage_id = str(uuid4())

    rule_id = uuid4()
    requirement_id = uuid4()
    action_id = uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO advancement_rules
            (rule_id, job_id, interview_plan_id, interview_stage_id,
             target_stage_id, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, true, NOW(), NOW())
            """,
            rule_id,
            job_id,
            interview_plan_id,
            interview_stage_id,
            target_stage_id,
        )

        await conn.execute(
            """
            INSERT INTO advancement_rule_requirements
            (requirement_id, rule_id, interview_id, score_field_path,
             operator, threshold_value, is_required, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
            """,
            requirement_id,
            rule_id,
            interview_id,
            score_field,
            operator,
            threshold,
        )

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
        "interview_plan_id": interview_plan_id,
        "interview_stage_id": interview_stage_id,
        "target_stage_id": target_stage_id,
        "interview_id": interview_id,
    }


async def create_test_schedule(
    db_pool,
    schedule_id: str | None = None,
    application_id: str | None = None,
    interview_stage_id: str | None = None,
    interview_plan_id: str | None = None,
    job_id: str | None = None,
    status: str = "Complete",
) -> dict:
    """Insert a schedule into the database for testing."""
    from uuid import UUID

    if schedule_id is None:
        schedule_id = str(uuid4())
    if application_id is None:
        application_id = str(uuid4())
    if interview_stage_id is None:
        interview_stage_id = str(uuid4())
    if interview_plan_id is None:
        interview_plan_id = str(uuid4())

    candidate_id = str(uuid4())

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interview_schedules
            (schedule_id, application_id, interview_stage_id, interview_plan_id,
             job_id, candidate_id, status, updated_at, last_evaluated_for_advancement_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NULL)
            """,
            schedule_id,
            application_id,
            interview_stage_id,
            interview_plan_id,
            job_id,
            candidate_id,
            status,
        )

    return {
        "schedule_id": schedule_id,
        "application_id": application_id,
        "interview_stage_id": interview_stage_id,
        "interview_plan_id": interview_plan_id,
        "job_id": job_id,
        "candidate_id": candidate_id,
    }


async def create_test_feedback(
    db_pool,
    event_id: str,
    application_id: str,
    interviewer_id: str,
    interview_id: str,
    submitted_values: dict | None = None,
    submitted_at: datetime | None = None,
) -> dict:
    """Insert feedback submission into the database for testing."""
    import json
    from uuid import UUID

    if submitted_values is None:
        submitted_values = {"overall_score": 4}
    if submitted_at is None:
        submitted_at = datetime.now(UTC) - timedelta(hours=1)

    feedback_id = uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO feedback_submissions
            (feedback_id, application_id, event_id, interviewer_id, interview_id,
             submitted_at, submitted_values, processed_for_advancement_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, NOW())
            """,
            feedback_id,
            application_id,
            event_id,
            interviewer_id,
            interview_id,
            submitted_at,
            json.dumps(submitted_values),
        )

        # Update schedule's updated_at to trigger re-evaluation (matches production behavior)
        await conn.execute(
            """
            UPDATE interview_schedules s
            SET updated_at = NOW()
            FROM interview_events e
            WHERE e.schedule_id = s.schedule_id
              AND e.event_id = $1
            """,
            event_id,
        )

    return {
        "feedback_id": str(feedback_id),
        "event_id": event_id,
        "application_id": application_id,
        "interviewer_id": interviewer_id,
        "interview_id": interview_id,
        "submitted_values": submitted_values,
    }
