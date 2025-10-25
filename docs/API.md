# API Reference

## Base URL

```
http://localhost:8000  # Development
https://your-domain.com  # Production
```

## Authentication

### Ashby Webhooks

All Ashby webhook requests include an HMAC-SHA256 signature for verification:

```
Ashby-Signature: sha256=<hex_digest>
```

The signature is computed using:
- Secret: `ASHBY_WEBHOOK_SECRET` environment variable
- Body: Raw request body (bytes)
- Algorithm: HMAC-SHA256

### Slack Interactions

Slack requests are verified using the Slack SDK with the `SLACK_SIGNING_SECRET` environment variable.

### Admin Endpoints

**Note**: Currently no authentication. Should be protected behind firewall or add API key authentication in production.

---

## Endpoints

### Health Check

**`GET /health`**

Check application health and database connectivity.

#### Response

**200 OK** - Application is healthy

```json
{
  "status": "healthy",
  "database": "connected",
  "scheduler": "running",
  "pool": {
    "size": 10,
    "free": 8,
    "in_use": 2
  },
  "metadata": {
    "jobs": 4,
    "plans": 3,
    "stages": 12,
    "last_synced": "2024-10-25T18:30:00Z"
  }
}
```

**Response Fields:**
- `metadata.jobs` - Number of jobs cached
- `metadata.plans` - Number of interview plans cached
- `metadata.stages` - Number of interview stages cached
- `metadata.last_synced` - ISO timestamp of last metadata sync (null if never synced)

**503 Service Unavailable** - Database unavailable

```json
{
  "detail": "Database unavailable"
}
```

---

### Root

**`GET /`**

Root endpoint returning application name.

#### Response

**200 OK**

```json
{
  "message": "Ashby Auto-Advancement System"
}
```

---

## Ashby Webhooks

### Handle Webhook

**`POST /webhooks/ashby`**

Receive and process Ashby webhook events.

**Rate Limit**: 100 requests/minute per IP

#### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `x-ashby-signature` | Yes* | HMAC-SHA256 signature (`sha256=<hex>`) |
| `Content-Type` | Yes | `application/json` |

*Not required for ping/test webhooks

#### Request Body

**Ping Webhook** (setup verification):

```json
{
  "action": "ping",
  "type": "ping"
}
```

**Interview Schedule Update**:

```json
{
  "action": "interviewSchedule.updated",
  "webhookEvent": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  },
  "interviewSchedule": {
    "id": "schedule-uuid",
    "applicationId": "app-uuid",
    "interviewStageId": "stage-uuid",
    "status": "Scheduled",
    "candidateId": "candidate-id",
    "updatedAt": "2024-10-19T14:30:00.000Z",
    "interviewEvents": [
      {
        "id": "event-uuid",
        "interviewId": "interview-uuid",
        "startTime": "2024-10-19T15:00:00.000Z",
        "endTime": "2024-10-19T15:30:00.000Z",
        "feedbackLink": "https://ashbyhq.com/feedback/...",
        "meetingLink": "https://zoom.us/j/...",
        "location": "Zoom",
        "hasSubmittedFeedback": false,
        "createdAt": "2024-10-19T14:00:00.000Z",
        "updatedAt": "2024-10-19T14:30:00.000Z",
        "interviewers": [
          {
            "id": "interviewer-uuid",
            "firstName": "Jane",
            "lastName": "Doe",
            "email": "jane@company.com",
            "globalRole": "Interviewer",
            "isEnabled": true
          }
        ]
      }
    ]
  }
}
```

#### Responses

**200 OK** - Ping webhook acknowledged

```json
{
  "status": "ok",
  "message": "pong"
}
```

**204 No Content** - Webhook processed successfully

**400 Bad Request** - Invalid JSON or malformed payload

```json
{
  "detail": "Invalid JSON"
}
```

**401 Unauthorized** - Invalid or missing signature

```json
{
  "detail": "Invalid webhook signature"
}
```

**429 Too Many Requests** - Rate limit exceeded

```json
{
  "error": "Rate limit exceeded: 100 per 1 minute"
}
```

---

## Slack Interactions

### Handle Interaction

**`POST /slack/interactions`**

Handle Slack interactive component events (rejection button clicks only).

#### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `x-slack-signature` | Yes | Slack request signature |
| `x-slack-request-timestamp` | Yes | Request timestamp (prevents replays) |
| `Content-Type` | Yes | `application/x-www-form-urlencoded` |

#### Request Body

Slack sends form-encoded payload with a `payload` field containing JSON.

**Rejection Button Click**:

```json
{
  "type": "block_actions",
  "user": {
    "id": "U123ABC456",
    "name": "jane.doe"
  },
  "actions": [
    {
      "action_id": "send_rejection",
      "type": "button",
      "value": "{\"application_id\":\"app-uuid\",\"action\":\"send_rejection\"}"
    }
  ],
  "message": {
    "ts": "1234567890.123456"
  },
  "channel": {
    "id": "D123ABC456"
  }
}
```

#### Responses

**200 OK** - Button click processed

The system asynchronously:
1. Archives candidate in Ashby using `DEFAULT_ARCHIVE_REASON_ID`
2. Records rejection in `advancement_executions` table
3. Updates Slack message to show "Rejection Email Sent"

If rejection fails, message is updated with error details.

---

## Admin Endpoints

### Sync Feedback Forms

**`POST /admin/sync-forms`**

Manually trigger feedback form synchronization from Ashby.

Useful after creating or updating feedback forms in Ashby.

#### Response

**200 OK**

```json
{
  "status": "completed",
  "message": "Feedback forms synced"
}
```

---

### Sync Slack Users

**`POST /admin/sync-slack-users`**

Manually trigger Slack user synchronization.

Useful after new employees join or email addresses change.

#### Response

**200 OK**

```json
{
  "status": "completed",
  "message": "Slack users synced"
}
```

---

### Sync Interviews

**`POST /admin/sync-interviews`**

Manually trigger interview definitions synchronization from Ashby.

Useful after creating or updating interviews in Ashby.

#### Response

**200 OK**

```json
{
  "status": "completed",
  "message": "Interviews synced"
}
```

---

### Sync Metadata

**`POST /admin/sync-metadata`**

Manually trigger metadata synchronization (jobs, plans, stages) from Ashby.

Syncs all metadata needed for UI dropdowns. Useful for immediate refresh during development.

#### Response

**200 OK**

```json
{
  "status": "completed",
  "message": "Metadata synced (jobs, plans, stages)"
}
```

---

### Get Advancement Statistics

**`GET /admin/stats`**

Retrieve advancement system statistics and execution metrics.

#### Response

**200 OK**

```json
{
  "active_rules": 5,
  "pending_evaluations": 12,
  "total_executions_30d": 68,
  "success_count": 42,
  "failed_count": 3,
  "dry_run_count": 15,
  "rejected_count": 8,
  "recent_failures": [
    {
      "execution_id": "exec-uuid",
      "schedule_id": "schedule-uuid",
      "application_id": "app-uuid",
      "failure_reason": "Failed to advance candidate stage: Network error",
      "executed_at": "2024-10-23T14:30:00Z"
    }
  ]
}
```

---

### Trigger Advancement Evaluation

**`POST /admin/trigger-advancement-evaluation`**

Manually trigger advancement evaluation for testing.

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `schedule_id` | No* | Specific schedule UUID to evaluate |
| `application_id` | No* | Evaluate all schedules for this application |

*Must provide either `schedule_id` OR `application_id`

#### Response

**200 OK** - With schedule_id

```json
{
  "schedule_id": "schedule-uuid",
  "evaluation": {
    "ready": true,
    "rule_id": "rule-uuid",
    "target_stage_id": "target-stage-uuid",
    "evaluation_results": {
      "all_passed": true,
      "results": [...]
    },
    "application_id": "app-uuid"
  }
}
```

**200 OK** - With application_id

```json
{
  "application_id": "app-uuid",
  "schedules_evaluated": 2,
  "results": [
    {
      "schedule_id": "schedule-uuid-1",
      "evaluation": { "ready": false, "blocking_reason": "no_matching_rule" }
    },
    {
      "schedule_id": "schedule-uuid-2",
      "evaluation": { "ready": true, "rule_id": "rule-uuid", ... }
    }
  ]
}
```

---

### Create Advancement Rule

**`POST /admin/create-advancement-rule`**

Create a new advancement rule with requirements and actions.

#### Request Body

```json
{
  "job_id": "job-uuid",
  "interview_plan_id": "plan-uuid",
  "interview_stage_id": "stage-uuid",
  "target_stage_id": null,
  "requirements": [
    {
      "interview_id": "interview-uuid",
      "score_field_path": "overall_score",
      "operator": ">=",
      "threshold_value": "3",
      "is_required": true
    }
  ],
  "actions": [
    {
      "action_type": "advance_stage",
      "action_config": null,
      "execution_order": 1
    }
  ]
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | UUID \| null | Optional job filter (null = applies to all jobs) |
| `interview_plan_id` | UUID | Interview plan this rule applies to |
| `interview_stage_id` | UUID | Interview stage this rule applies to |
| `target_stage_id` | UUID \| null | Target stage (null = next sequential) |
| `requirements` | array | List of score requirements (all must pass) |
| `actions` | array | Actions to execute when requirements pass |

**Requirement Fields:**

| Field | Description |
|-------|-------------|
| `interview_id` | Interview definition UUID |
| `score_field_path` | Field name in feedback (e.g., "overall_score") |
| `operator` | Comparison: `>=`, `>`, `==`, `<=`, `<` |
| `threshold_value` | Minimum acceptable value (string) |
| `is_required` | If false, interview is optional |

#### Response

**200 OK**

```json
{
  "rule_id": "rule-uuid",
  "requirement_ids": ["req-uuid-1", "req-uuid-2"],
  "action_ids": ["action-uuid"],
  "status": "created"
}
```

---

### List Jobs

**`GET /admin/metadata/jobs`**

Get list of jobs for UI dropdowns.

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `active_only` | No | If true, only return open jobs (default: true) |

#### Response

**200 OK**

```json
{
  "jobs": [
    {
      "id": "job-uuid",
      "title": "Senior Software Engineer",
      "status": "Open",
      "department_id": "dept-uuid",
      "location": "San Francisco",
      "employment_type": "FullTime"
    }
  ]
}
```

---

### Get Job Plans

**`GET /admin/metadata/jobs/{job_id}/plans`**

Get interview plans for a specific job.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `job_id` | Yes | Job UUID |

#### Response

**200 OK**

```json
{
  "plans": [
    {
      "id": "plan-uuid",
      "title": "Engineering Onsite",
      "is_default": true
    }
  ]
}
```

---

### Get Plan Stages

**`GET /admin/metadata/plans/{plan_id}/stages`**

Get interview stages for an interview plan.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `plan_id` | Yes | Interview plan UUID |

#### Response

**200 OK**

```json
{
  "stages": [
    {
      "id": "stage-uuid",
      "title": "Technical Screen",
      "type": "Active",
      "order": 1
    },
    {
      "id": "stage-uuid-2",
      "title": "Onsite Interview",
      "type": "Active",
      "order": 2
    }
  ]
}
```

---

### List Interviews

**`GET /admin/metadata/interviews`**

Get list of interviews, optionally filtered by job.

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `job_id` | No | Filter interviews by job UUID |

#### Response

**200 OK**

```json
{
  "interviews": [
    {
      "id": "interview-uuid",
      "title": "Technical Screen",
      "job_id": "job-uuid",
      "feedback_form_id": "form-uuid"
    }
  ]
}
```

---

### Get Feedback Form Fields

**`GET /admin/metadata/feedback-forms/{form_id}/fields`**

Get scoreable fields from a feedback form for use in advancement rule requirements.

Returns only field types that can be scored (Score, ValueSelect, Rating). Excludes text fields like RichText.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `form_id` | Yes | Feedback form definition UUID |

#### Response

**200 OK**

```json
{
  "fields": [
    {
      "path": "overall_score",
      "label": "Overall Assessment",
      "type": "Score",
      "options": null
    },
    {
      "path": "recommendation",
      "label": "Hiring Recommendation",
      "type": "ValueSelect",
      "options": [
        {"label": "Strong Hire", "value": "strong_hire"},
        {"label": "Hire", "value": "hire"},
        {"label": "No Hire", "value": "no_hire"}
      ]
    }
  ]
}
```

**Field Types:**
- `Score` - Numeric rating field
- `ValueSelect` - Dropdown with predefined options
- `Rating` - Star rating or similar

---

### List Advancement Rules

**`GET /admin/rules`**

List all advancement rules with their requirements and actions.

#### Query Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `active_only` | No | If true, only return active rules (default: true) |

#### Response

**200 OK**

```json
{
  "count": 2,
  "rules": [
    {
      "rule_id": "rule-uuid",
      "job_id": null,
      "interview_plan_id": "plan-uuid",
      "interview_stage_id": "stage-uuid",
      "target_stage_id": null,
      "is_active": true,
      "created_at": "2024-10-20T14:30:00Z",
      "updated_at": "2024-10-20T14:30:00Z",
      "requirements": [
        {
          "requirement_id": "req-uuid",
          "interview_id": "interview-uuid",
          "score_field_path": "overall_score",
          "operator": ">=",
          "threshold_value": "3",
          "is_required": true,
          "created_at": "2024-10-20T14:30:00Z"
        }
      ],
      "actions": [
        {
          "action_id": "action-uuid",
          "action_type": "advance_stage",
          "action_config": null,
          "execution_order": 1,
          "created_at": "2024-10-20T14:30:00Z"
        }
      ]
    }
  ]
}
```

---

### Get Advancement Rule

**`GET /admin/rules/{rule_id}`**

Get detailed information about a specific advancement rule.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `rule_id` | Yes | Rule UUID |

#### Response

**200 OK**

Same structure as individual rule object in list response above.

**404 Not Found**

```json
{
  "detail": "Rule {rule_id} not found"
}
```

---

### Delete Advancement Rule

**`DELETE /admin/rules/{rule_id}`**

Soft-delete an advancement rule by setting is_active=false.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `rule_id` | Yes | Rule UUID to delete |

#### Response

**200 OK**

```json
{
  "status": "deleted",
  "rule_id": "rule-uuid"
}
```

**404 Not Found**

```json
{
  "detail": "Rule {rule_id} not found or already deleted"
}
```

---

### Get Advancement Stats

**`GET /admin/stats`**

Get advancement execution statistics and monitoring data.

#### Response

**200 OK**

```json
{
  "active_rules": 5,
  "pending_evaluations": 12,
  "total_executions_30d": 68,
  "success_count": 42,
  "failed_count": 3,
  "dry_run_count": 15,
  "rejected_count": 8,
  "recent_failures": [
    {
      "execution_id": "exec-uuid",
      "schedule_id": "schedule-uuid",
      "application_id": "app-uuid",
      "failure_reason": "Failed to advance candidate stage: Network error",
      "executed_at": "2024-10-23T14:30:00Z"
    }
  ]
}
```

---

## Error Handling

### Standard Error Format

All errors follow this standardized format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

The `details` field is only included when `EXPOSE_ERROR_DETAILS=true` (default for dev/staging).

**Error Codes:**

| Code | HTTP Status | Description |
|------|------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 422 | Request validation failed (includes details array) |
| `EXTERNAL_SERVICE_ERROR` | 502 | External API (Ashby/Slack) failure |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `CONFIGURATION_ERROR` | 500 | System misconfigured |
| `HTTP_400` | 400 | Bad Request - Invalid JSON, malformed payload |
| `HTTP_401` | 401 | Unauthorized - Invalid signature |
| `HTTP_404` | 404 | Not Found - Resource doesn't exist |
| `HTTP_422` | 422 | Unprocessable Entity - Validation error |
| `HTTP_429` | 429 | Too Many Requests - Rate limit exceeded |
| `HTTP_500` | 500 | Internal Error - Unexpected server error |
| `HTTP_503` | 503 | Service Unavailable - Database unavailable |
| `INTERNAL_ERROR` | 500 | Unexpected error occurred |

**Request ID:**

All responses (success and error) include `X-Request-ID` header. Reference this ID when reporting issues.

**Error Details:**

When `EXPOSE_ERROR_DETAILS=true` (default for dev/staging), errors include a `details` object with additional context:

```json
{
  "error": {
    "code": "EXTERNAL_SERVICE_ERROR",
    "message": "Ashby API request failed: Invalid request",
    "details": {
      "service": "ashby",
      "endpoint": "candidate.info",
      "candidate_id": "abc-123"
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

Set `EXPOSE_ERROR_DETAILS=false` in production to hide sensitive details.

**Example Error Response:**

```bash
curl -i https://api.example.com/admin/rules/invalid-id

HTTP/1.1 404 Not Found
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "error": {
    "code": "HTTP_404",
    "message": "Rule invalid-id not found",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | OK | Request succeeded |
| 204 | No Content | Webhook processed successfully |
| 400 | Bad Request | Invalid JSON, malformed payload |
| 401 | Unauthorized | Invalid signature |
| 403 | Forbidden | Missing permissions |
| 404 | Not Found | Endpoint doesn't exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected application error |
| 503 | Service Unavailable | Database unavailable |

---

## Webhook Setup

### Ashby Configuration

1. Go to **Settings → Webhooks** in Ashby
2. Click **Create Webhook**
3. Set URL: `https://your-domain.com/webhooks/ashby`
4. Select event: **Interview Schedule Updated**
5. Set secret: Use your `ASHBY_WEBHOOK_SECRET` value
6. Click **Test Webhook** (should return 200 OK with "pong")
7. Save

### Slack App Configuration

1. Go to **api.slack.com/apps**
2. Create new app or select existing
3. Under **Interactivity & Shortcuts**:
   - Enable Interactivity
   - Request URL: `https://your-domain.com/slack/interactions`
4. Under **OAuth & Permissions**:
   - Add scopes: `chat:write`, `users:read`, `users:read.email`, `files.remote:write`
   - Install to workspace
   - Copy **Bot User OAuth Token** to `SLACK_BOT_TOKEN`
5. Under **Basic Information**:
   - Copy **Signing Secret** to `SLACK_SIGNING_SECRET`

---

## Rate Limiting

### Current Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/webhooks/ashby` | 100 requests | 1 minute |
| All other endpoints | No limit | - |

### Rate Limit Response

**429 Too Many Requests**

```json
{
  "error": "Rate limit exceeded: 100 per 1 minute"
}
```

**Headers**:
- `X-RateLimit-Limit`: Maximum requests per window
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `Retry-After`: Seconds to wait before retrying

---

## Testing

### Interactive Documentation

FastAPI provides auto-generated interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Example: Test Webhook Locally

```bash
# Compute signature
SECRET="your_webhook_secret"
BODY='{"action":"ping"}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# Send request
curl -X POST http://localhost:8000/webhooks/ashby \
  -H "Content-Type: application/json" \
  -H "x-ashby-signature: sha256=$SIGNATURE" \
  -d "$BODY"
```

### Example: Simulate Interview Webhook

See `tests/fixtures/sample_payloads.py` for complete webhook payload examples.

```python
import httpx
import hmac
import hashlib

secret = "your_webhook_secret"
payload = {
    "action": "interviewSchedule.updated",
    "interviewSchedule": { /* ... */ }
}

body = json.dumps(payload).encode()
signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

response = httpx.post(
    "http://localhost:8000/webhooks/ashby",
    content=body,
    headers={
        "Content-Type": "application/json",
        "x-ashby-signature": f"sha256={signature}"
    }
)
```

---

## Versioning

Current version: **2.0.0**

The API currently does not use versioning. Breaking changes will be communicated via:
- GitHub releases
- CHANGELOG.md updates
- Migration guides in documentation

Future versions may use URL versioning (`/v2/webhooks/ashby`) or header versioning.

### Version History

- **2.0.0** - Auto-advancement system (removed feedback modals, added advancement automation)
- **1.0.0** - Initial release (feedback reminders via Slack)

