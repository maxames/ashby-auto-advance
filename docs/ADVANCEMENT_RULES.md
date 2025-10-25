# Advancement Rules Configuration

## Overview

Advancement rules automatically move candidates to the next interview stage when they meet specific criteria. This guide explains how to configure, test, and monitor advancement rules.

The system evaluates candidates every 30 minutes based on:
- Feedback scores from all assigned interviewers
- Configurable thresholds for each interview type
- Job-specific or global rules

When requirements are met, candidates automatically advance. When they fail, recruiters receive Slack notifications with a one-click rejection workflow.

## Rule System Architecture

### Three-Part Structure

1. **Rules** - Define when to evaluate (job + interview plan + stage)
2. **Requirements** - Define what must be true (scores >= thresholds)
3. **Actions** - Define what happens (advance or notify)

### Rule Matching

Rules are matched based on:
- `interview_plan_id` (required) - Which interview process
- `interview_stage_id` (required) - Which stage in that process
- `job_id` (optional) - Which specific job (NULL = applies to all jobs)

**Priority:** Job-specific rules take precedence over global rules (job_id = NULL)

**Example**: If you have both:
- Rule A: job_id = "senior-eng-uuid", interview_plan_id = "plan-1", interview_stage_id = "tech-screen"
- Rule B: job_id = NULL, interview_plan_id = "plan-1", interview_stage_id = "tech-screen"

Rule A will be used for the "senior-eng" job, Rule B for all other jobs using that plan and stage.

## Creating Rules

### Via Admin API

**Endpoint:** `POST /admin/create-advancement-rule`

### Example 1: Simple Technical Screen

Advance after a single interview with overall_score >= 3:

```json
{
  "job_id": null,
  "interview_plan_id": "01234567-89ab-cdef-0123-456789abcdef",
  "interview_stage_id": "tech-screen-stage-uuid",
  "target_stage_id": null,
  "requirements": [
    {
      "interview_id": "tech-screen-interview-uuid",
      "score_field_path": "overall_score",
      "operator": ">=",
      "threshold_value": "3",
      "is_required": true
    }
  ],
  "actions": [
    {
      "action_type": "advance_stage",
      "execution_order": 1
    }
  ]
}
```

**Result**: Candidate with overall_score >= 3 automatically advances to next stage.

### Example 2: Multi-Interview Onsite

Require multiple interviews with different thresholds:

```json
{
  "job_id": "senior-eng-job-uuid",
  "interview_plan_id": "eng-plan-uuid",
  "interview_stage_id": "onsite-stage-uuid",
  "target_stage_id": "offer-stage-uuid",
  "requirements": [
    {
      "interview_id": "technical-deep-dive-uuid",
      "score_field_path": "overall_score",
      "operator": ">=",
      "threshold_value": "4",
      "is_required": true
    },
    {
      "interview_id": "technical-deep-dive-uuid",
      "score_field_path": "coding_ability",
      "operator": ">=",
      "threshold_value": "3",
      "is_required": true
    },
    {
      "interview_id": "culture-fit-uuid",
      "score_field_path": "team_fit",
      "operator": ">=",
      "threshold_value": "4",
      "is_required": true
    },
    {
      "interview_id": "hiring-manager-uuid",
      "score_field_path": "overall_score",
      "operator": ">=",
      "threshold_value": "4",
      "is_required": true
    }
  ],
  "actions": [
    {
      "action_type": "advance_stage",
      "execution_order": 1
    }
  ]
}
```

**Result**: All four requirements must pass. If any fail, recruiter gets rejection notification.

### Example 3: Explicit Target Stage

Skip stages by specifying explicit target:

```json
{
  "job_id": null,
  "interview_plan_id": "fast-track-plan-uuid",
  "interview_stage_id": "phone-screen-uuid",
  "target_stage_id": "offer-stage-uuid",
  "requirements": [
    {
      "interview_id": "phone-screen-interview-uuid",
      "score_field_path": "strong_yes",
      "operator": "==",
      "threshold_value": "true",
      "is_required": true
    }
  ],
  "actions": [
    {
      "action_type": "advance_stage",
      "execution_order": 1
    }
  ]
}
```

**Result**: Strong yes candidates skip intermediate stages and go straight to offer.

### Using curl

Save your rule as `rule.json` and create it:

```bash
curl -X POST https://your-domain.com/admin/create-advancement-rule \
  -H "Content-Type: application/json" \
  -d @rule.json
```

Response:
```json
{
  "rule_id": "rule-uuid",
  "requirement_ids": ["req-uuid-1", "req-uuid-2"],
  "action_ids": ["action-uuid"],
  "status": "created"
}
```

## Rule Components

### Requirements

Each requirement checks a specific score field from feedback.

**Fields:**

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `interview_id` | UUID | Which interview to check | `"tech-screen-uuid"` |
| `score_field_path` | string | Field name in feedback form | `"overall_score"` |
| `operator` | string | Comparison type | `">="`, `">"`, `"=="`, `"<="`, `"<"` |
| `threshold_value` | string | Minimum acceptable value | `"3"`, `"4"`, `"true"` |
| `is_required` | boolean | If true, interview must be completed | `true` |

**Finding Score Field Paths:**

Method 1 - From Ashby UI:
1. Go to Ashby → Settings → Feedback Forms
2. Edit your feedback form
3. Look at field IDs (e.g., "Overall Assessment" often maps to `overall_score`)

Method 2 - From API Response:
1. Use a test feedback submission
2. Query: `SELECT submitted_values FROM feedback_submissions LIMIT 1`
3. Inspect the JSON keys (e.g., `{"overall_score": 4, "technical_skills": 3}`)

**Common Score Fields:**
- `overall_score` - Overall assessment (1-5 scale)
- `technical_skills` - Technical competency
- `communication` - Communication skills
- `culture_fit` - Cultural alignment
- `strong_yes` - Binary strong hire recommendation (boolean)

**All Requirements Must Pass:**
- If ANY requirement fails, advancement is blocked
- Recruiter receives rejection notification with feedback summary

### Target Stage

Two options for where to advance candidates:

**1. Explicit Target** (recommended for skipping stages)

```json
"target_stage_id": "offer-stage-uuid"
```

Use when:
- You want to skip intermediate stages
- Different outcomes go to different stages
- Fast-track exceptional candidates

**2. Sequential (next in order)**

```json
"target_stage_id": null
```

Use when:
- Standard progression through all stages
- Simpler rule configuration
- Stages are sequential and consistent

How it works:
- System fetches all stages for the interview plan
- Finds current stage's `orderInInterviewPlan` value
- Advances to stage with `orderInInterviewPlan + 1`
- Fails if no next stage exists (e.g., current stage is final)

### Actions

Currently supported action types:

**`advance_stage`** - Move candidate to target stage
```json
{
  "action_type": "advance_stage",
  "action_config": null,
  "execution_order": 1
}
```

**Future actions** (not yet implemented):
- `send_email` - Send custom email template
- `create_task` - Create Ashby task for recruiter
- `update_field` - Update application custom fields
- `add_tag` - Add tags to application

## Evaluation Logic

### When Evaluation Runs

The scheduler triggers evaluation every 30 minutes for schedules matching:

**Criteria:**
- Status: `WaitingOnFeedback` or `Complete`
- Has `interview_plan_id` (fetched during webhook processing)
- Not evaluated recently OR updated since last evaluation
- Within timeout window (default: 7 days from status change to Complete)

**Query used:**
```sql
SELECT *
FROM interview_schedules
WHERE status IN ('WaitingOnFeedback', 'Complete')
  AND (last_evaluated_for_advancement_at IS NULL
       OR updated_at > last_evaluated_for_advancement_at)
  AND updated_at > NOW() - INTERVAL '7 days'
  AND interview_plan_id IS NOT NULL;
```

### Multiple Interviewers

If an interview event has multiple assigned interviewers:

**Requirements:**
- **ALL interviewers must submit feedback** (count check)
- **ALL submitted scores must pass thresholds** (score check)
- Missing feedback from any interviewer blocks advancement

**Example: Panel Interview**

Setup:
- Technical interview with 3 interviewers: Alice, Bob, Carol
- Requirement: `overall_score >= 4`

Scenario 1 - All Pass:
- Alice: overall_score = 5 (PASS)
- Bob: overall_score = 4 (PASS)
- Carol: overall_score = 5 (PASS)
- **Result:** ADVANCE

Scenario 2 - One Fails:
- Alice: overall_score = 5 (PASS)
- Bob: overall_score = 4 (PASS)
- Carol: overall_score = 2 (FAIL)
- **Result:** BLOCKED (rejection notification sent)

Scenario 3 - Missing Feedback:
- Alice: overall_score = 5 (PASS)
- Bob: overall_score = 4 (PASS)
- Carol: (not submitted yet)
- **Result:** BLOCKED (waiting for all feedback)

### 30-Minute Wait Period

After the last feedback is submitted:
- System waits 30 minutes (configurable via `ADVANCEMENT_FEEDBACK_MIN_WAIT_MINUTES`)
- Allows time for all panel members to submit
- Prevents premature advancement if submissions are staggered

**Why wait?**
- Interview at 2:00 PM ends
- Interviewer A submits at 2:15 PM
- Interviewer B submits at 2:35 PM
- Without wait: System would evaluate at 2:30 PM (before B submits) and fail
- With wait: System evaluates at 3:05 PM (35 min after last submission) and succeeds

### Dry-Run Mode

**Highly recommended for testing rules before enabling real advancements.**

Enable in environment:
```bash
ADVANCEMENT_DRY_RUN_MODE=true
```

**Behavior when enabled:**
- Evaluation runs normally
- Logs show what WOULD happen
- Records created in `advancement_executions` with status = 'dry_run'
- No actual API calls to advance candidates
- No candidates moved

**Monitor dry-run logs:**
```
DRY_RUN: Would advance candidate (schedule_id=abc-123, application_id=def-456, target_stage=xyz-789)
```

**Testing workflow:**
1. Set `ADVANCEMENT_DRY_RUN_MODE=true`
2. Create your rule via API
3. Wait for scheduler (30 min) OR manually trigger:
   ```bash
   curl -X POST http://localhost:8000/admin/trigger-advancement-evaluation?schedule_id=<uuid>
   ```
4. Check logs and database:
   ```sql
   SELECT * FROM advancement_executions WHERE execution_status = 'dry_run' ORDER BY executed_at DESC;
   ```
5. Verify evaluation_results JSON looks correct
6. If everything looks good, set `ADVANCEMENT_DRY_RUN_MODE=false`

## Rejection Notifications

When a candidate fails requirements:

### What Happens

1. System sends Slack message to admin channel (if `ADMIN_SLACK_CHANNEL_ID` set)
2. Message includes:
   - Candidate name and contact info
   - Job title
   - Link to Ashby profile
   - Feedback summary with scores from all interviews
   - Button: "Archive & Send Rejection Email" (with confirmation dialog)
3. Recruiter reviews feedback
4. Clicks button to archive candidate
5. System archives in Ashby using `DEFAULT_ARCHIVE_REASON_ID`
6. Message updates to show "Rejection Email Sent"

### Configuration

**Required:**
```bash
DEFAULT_ARCHIVE_REASON_ID=<uuid-from-ashby>
```

**Optional (but recommended):**
```bash
ADMIN_SLACK_CHANNEL_ID=C123ABC456
```

**To get DEFAULT_ARCHIVE_REASON_ID:**
1. Log in to Ashby
2. Go to **Settings → Archive Reasons**
3. Find or create a reason:
   - "Did not meet hiring bar"
   - "Auto-rejected based on feedback scores"
   - "Failed technical assessment"
4. Copy the UUID (visible in URL or via API)

**To get ADMIN_SLACK_CHANNEL_ID:**
1. Open Slack
2. Go to the channel you want to use
3. Click channel name → More → Copy link
4. Extract ID from URL: `https://yourworkspace.slack.com/archives/C123ABC456`
5. The ID is `C123ABC456`

### Example Notification

```
WARNING: Candidate Did Not Meet Advancement Criteria

John Smith
Position: Senior Software Engineer
Email: john.smith@email.com
Phone: +1 555-0123

View Profile in Ashby

━━━━━━━━━━━━━━━━━━━━━━━━

Interview Feedback Summary

Technical Deep Dive
• Overall Score: 2
• Coding Ability: 3
• System Design: 2

Culture Fit Interview
• Team Fit: 3
• Communication: 4

━━━━━━━━━━━━━━━━━━━━━━━━

[Archive & Send Rejection Email]

This candidate was automatically flagged because they did not meet
the scoring thresholds for advancement.
```

## Monitoring

### Query Templates

**Check pending evaluations:**
```sql
SELECT COUNT(*)
FROM interview_schedules
WHERE status IN ('WaitingOnFeedback', 'Complete')
  AND (last_evaluated_for_advancement_at IS NULL
       OR updated_at > last_evaluated_for_advancement_at)
  AND interview_plan_id IS NOT NULL;
```

**View recent executions:**
```sql
SELECT
  execution_status,
  COUNT(*) as count
FROM advancement_executions
WHERE executed_at > NOW() - INTERVAL '7 days'
GROUP BY execution_status
ORDER BY count DESC;
```

Expected statuses:
- `success` - Candidate successfully advanced
- `failed` - API call failed (network error, etc.)
- `dry_run` - Dry-run mode enabled
- `rejected` - Manually rejected by recruiter

**Find failed advancements:**
```sql
SELECT
  schedule_id,
  application_id,
  failure_reason,
  executed_at
FROM advancement_executions
WHERE execution_status = 'failed'
  AND executed_at > NOW() - INTERVAL '24 hours'
ORDER BY executed_at DESC;
```

**Check rule effectiveness:**
```sql
SELECT
  r.rule_id,
  r.interview_stage_id,
  COUNT(e.execution_id) as total_evaluations,
  SUM(CASE WHEN e.execution_status = 'success' THEN 1 ELSE 0 END) as successes,
  SUM(CASE WHEN e.execution_status = 'rejected' THEN 1 ELSE 0 END) as rejections,
  ROUND(
    SUM(CASE WHEN e.execution_status = 'success' THEN 1 ELSE 0 END)::numeric /
    NULLIF(COUNT(e.execution_id), 0) * 100,
    2
  ) as success_rate_pct
FROM advancement_rules r
LEFT JOIN advancement_executions e ON e.rule_id = r.rule_id
WHERE r.is_active = true
  AND e.executed_at > NOW() - INTERVAL '30 days'
GROUP BY r.rule_id, r.interview_stage_id
ORDER BY total_evaluations DESC;
```

**View evaluation details:**
```sql
SELECT
  execution_id,
  execution_status,
  evaluation_results::jsonb,
  executed_at
FROM advancement_executions
WHERE schedule_id = '<your-schedule-uuid>'
ORDER BY executed_at DESC;
```

This shows the full evaluation JSON including which requirements passed/failed.

### Admin API

**Get statistics:**
```bash
curl https://your-domain.com/admin/stats
```

Response:
```json
{
  "active_rules": 5,
  "pending_evaluations": 12,
  "total_executions_30d": 68,
  "success_count": 42,
  "failed_count": 3,
  "dry_run_count": 15,
  "rejected_count": 8,
  "recent_failures": [...]
}
```

**Manually trigger evaluation:**
```bash
# By schedule ID
curl -X POST https://your-domain.com/admin/trigger-advancement-evaluation?schedule_id=<uuid>

# By application ID (evaluates all schedules for that application)
curl -X POST https://your-domain.com/admin/trigger-advancement-evaluation?application_id=<uuid>
```

**List all active rules:**
```sql
SELECT
  r.rule_id,
  r.job_id,
  r.interview_plan_id,
  r.interview_stage_id,
  r.target_stage_id,
  COUNT(req.requirement_id) as requirement_count
FROM advancement_rules r
LEFT JOIN advancement_rule_requirements req ON req.rule_id = r.rule_id
WHERE r.is_active = true
GROUP BY r.rule_id
ORDER BY r.created_at DESC;
```

## Common Issues

### "No matching rule"

**Cause:** No active rule matches the combination of job + interview_plan + interview_stage

**Symptoms in logs:**
```
no_matching_rule (job_id=..., interview_plan_id=..., interview_stage_id=...)
```

**Solution:**

1. Verify rule exists:
   ```sql
   SELECT * FROM advancement_rules WHERE is_active = true;
   ```

2. Check what the schedule has:
   ```sql
   SELECT
     schedule_id,
     job_id,
     interview_plan_id,
     interview_stage_id
   FROM interview_schedules
   WHERE schedule_id = '<your-schedule-uuid>';
   ```

3. Ensure rule's `job_id` matches (or is NULL for global)

4. Check interview_plan_id was fetched:
   ```sql
   SELECT COUNT(*) FROM interview_schedules WHERE interview_plan_id IS NULL;
   ```
   If many are NULL, webhook processing may be failing

### "Missing feedback"

**Cause:** Not all assigned interviewers have submitted feedback

**Symptoms in logs:**
```
blocking_reason: no_feedback_submitted
```
or in evaluation_results:
```json
{
  "passed": false,
  "reason": "missing_feedback_2_of_3"
}
```

**Solution:**

1. Check how many interviewers were assigned:
   ```sql
   SELECT COUNT(*) FROM interview_assignments WHERE event_id = '<event-uuid>';
   ```

2. Check how many submitted feedback:
   ```sql
   SELECT COUNT(*) FROM feedback_submissions WHERE event_id = '<event-uuid>';
   ```

3. If mismatch, either:
   - Wait for remaining interviewers to submit
   - Manually adjust the interview assignments if someone was removed

### "Feedback too recent"

**Cause:** Feedback submitted less than 30 minutes ago (or configured wait time)

**Symptoms in logs:**
```
blocking_reason: feedback_too_recent_30min_wait
```

**Solution:**

Wait for the configured period to elapse. The system will automatically re-evaluate.

**To adjust wait period:**
```bash
ADVANCEMENT_FEEDBACK_MIN_WAIT_MINUTES=15  # Reduce to 15 minutes
```

**Why we wait:**
- Prevents premature advancement if multiple interviewers submit at different times
- Gives all panel members time to complete feedback
- Ensures complete evaluation before making decision

### "Target stage not found"

**Cause:** Using sequential advancement (`target_stage_id: null`) but no next stage exists

**Symptoms in logs:**
```
target_stage_error: No next stage found (current order: 5, plan: plan-uuid)
```

**Solution:**

1. Check if current stage is the last one:
   ```bash
   # Call Ashby API to list stages
   curl -X POST https://api.ashbyhq.com/interviewStage.list \
     -H "Authorization: Basic <your-encoded-key>" \
     -d '{"interviewPlanId": "plan-uuid"}'
   ```

2. If it's the last stage, use explicit `target_stage_id` instead of null
3. Or create a rule without auto-advancement for final stages

### "Score field missing"

**Cause:** Score field path doesn't exist in feedback submission

**Symptoms in evaluation_results:**
```json
{
  "passed": false,
  "reason": "score_field_missing_overall_score"
}
```

**Solution:**

1. Check what fields exist in feedback:
   ```sql
   SELECT submitted_values
   FROM feedback_submissions
   WHERE event_id = '<event-uuid>'
   LIMIT 1;
   ```

2. Verify field path matches exactly (case-sensitive):
   - Incorrect: `"Overall_Score"`, `"overallScore"`
   - Correct: `"overall_score"`

3. Update rule with correct field path

## Best Practices

### 1. Start with Dry-Run Mode

**Always** test rules in dry-run mode before enabling real advancements:

```bash
ADVANCEMENT_DRY_RUN_MODE=true
```

Benefits:
- See exactly what would happen
- No risk of incorrect advancements
- Can iterate on thresholds safely
- Full audit trail of decisions

**Testing checklist:**
- [ ] Create rule in dry-run mode
- [ ] Wait for evaluation (30 min) or manually trigger
- [ ] Check `advancement_executions` for dry_run records
- [ ] Review evaluation_results JSON
- [ ] Verify thresholds are correct
- [ ] Monitor for 24-48 hours
- [ ] Disable dry-run mode

### 2. Test on Non-Critical Candidates

Start with:
- Lower-stakes positions
- High-volume roles where mistakes are less costly
- Intern/contractor hiring

Avoid:
- Executive positions
- Your first rule on C-suite candidates
- Critical senior hires

### 3. Monitor the Audit Trail

Regularly check `advancement_executions` for unexpected behavior:

```sql
SELECT * FROM advancement_executions
WHERE execution_status = 'failed'
  OR execution_status = 'rejected'
ORDER BY executed_at DESC
LIMIT 20;
```

Look for:
- Higher than expected rejection rate
- Failed API calls (network issues)
- Unexpected blocking reasons

### 4. Use Job-Specific Rules When Possible

More control than global rules:

```json
{
  "job_id": "specific-job-uuid",  // Targets one job
  "interview_plan_id": "...",
  "interview_stage_id": "..."
}
```

Benefits:
- Different thresholds for different roles
- Senior vs junior positions can have different bars
- Easier to debug (smaller scope)

When to use global rules (`job_id: null`):
- Standardized interview processes across all jobs
- Simple pass/fail criteria that apply universally
- Easier maintenance (one rule instead of many)

### 5. Document Your Thresholds

Keep a spreadsheet or document tracking:

| Job | Stage | Interview | Score Field | Threshold | Rationale | Created By | Date |
|-----|-------|-----------|-------------|-----------|-----------|------------|------|
| Senior SWE | Tech Screen | Coding | overall_score | >= 4 | Need strong signal early | Jane | 2024-10-15 |
| Senior SWE | Onsite | System Design | technical_depth | >= 3 | Minimum competency | Jane | 2024-10-15 |

Benefits:
- Know why thresholds were set
- Easy to review and adjust
- Onboarding for new recruiters
- Historical reference

### 6. Set Up Admin Channel

Configure `ADMIN_SLACK_CHANNEL_ID` for:

**Rejection notifications:**
- Recruiter can review and take action
- Centralized visibility into rejections
- Quick access to candidate profiles

**Error alerts:**
- API failures
- Unexpected edge cases
- System health issues

**Recommended setup:**
- Create `#recruitment-automation` channel
- Add all recruiters
- Pin instructions for handling rejection notifications

### 7. Regular Threshold Reviews

Review advancement success rates quarterly or after major changes:

**Questions to ask:**
- Are thresholds too high? (many rejections, talent pipeline drying up)
- Too low? (quality issues emerging in later stages)
- Different thresholds needed for different roles?
- Are certain interviews better predictors than others?

**Data-driven approach:**
```sql
-- Compare advancement rates by rule
SELECT
  r.interview_stage_id,
  COUNT(*) as total_evaluations,
  SUM(CASE WHEN e.execution_status = 'success' THEN 1 ELSE 0 END) as advancements,
  SUM(CASE WHEN e.execution_status = 'rejected' THEN 1 ELSE 0 END) as rejections,
  ROUND(
    SUM(CASE WHEN e.execution_status = 'success' THEN 1 ELSE 0 END)::numeric /
    COUNT(*) * 100,
    1
  ) as advancement_rate_pct
FROM advancement_rules r
JOIN advancement_executions e ON e.rule_id = r.rule_id
WHERE e.executed_at > NOW() - INTERVAL '90 days'
GROUP BY r.interview_stage_id;
```

## Troubleshooting

### Enable Debug Logging

For detailed debugging, enable debug logs:

```bash
LOG_LEVEL=DEBUG
```

**Look for these log events:**

**Successful flow:**
- `rule_matched` - Rule was found for schedule
- `rule_requirements_evaluated` - All requirements checked
- `schedule_ready_for_advancement` - Passed all criteria
- `candidate_advanced_successfully` - API call succeeded

**Blocked flow:**
- `no_matching_rule` - No rule configured
- `blocking_reason: requirements_not_met` - Scores too low
- `blocking_reason: feedback_too_recent` - Within wait period
- `sending_rejection_notification` - Notifying recruiter

**Errors:**
- `advancement_attempt_failed` - API call failed (will retry)
- `advancement_failed` - All retries exhausted
- `rejection_notification_error` - Failed to send Slack message

### Check Scheduler

Verify both advancement jobs are running:

```bash
# Look for these every 30 minutes in logs:
grep "feedback_sync_started" app.log
grep "advancement_evaluations_started" app.log
```

If missing:
1. Check scheduler configured: Look for `scheduler_configured (jobs=9)` at startup
2. Check for scheduler errors
3. Restart application

### Verify Data Pipeline

**Step 1: Webhooks → Database**
```sql
-- Recent schedules should have interview_plan_id
SELECT
  schedule_id,
  status,
  interview_plan_id,
  job_id,
  created_at
FROM interview_schedules
ORDER BY created_at DESC
LIMIT 5;
```

**Step 2: Feedback Sync**
```sql
-- Should see recent feedback
SELECT
  COUNT(*) as total,
  MAX(created_at) as most_recent
FROM feedback_submissions;

-- Check for specific application
SELECT * FROM feedback_submissions
WHERE application_id = '<uuid>'
ORDER BY submitted_at DESC;
```

**Step 3: Rules Exist**
```sql
SELECT
  rule_id,
  interview_plan_id,
  interview_stage_id,
  is_active,
  created_at
FROM advancement_rules
ORDER BY created_at DESC;
```

**Step 4: Evaluations Running**
```sql
SELECT
  execution_status,
  COUNT(*),
  MAX(executed_at) as most_recent
FROM advancement_executions
GROUP BY execution_status;
```

### Debug Specific Schedule

To debug why a specific schedule isn't advancing:

```bash
# 1. Trigger manual evaluation
curl -X POST http://localhost:8000/admin/trigger-advancement-evaluation?schedule_id=<uuid>
```

Response will show:
- `ready: true` - Should advance (check if dry-run enabled)
- `ready: false` - Blocked (see blocking_reason)

Common blocking_reason values:
- `no_matching_rule` - No rule configured
- `no_feedback_submitted` - Waiting for feedback
- `feedback_too_recent_30min_wait` - Within wait period
- `requirements_not_met` - Scores don't pass thresholds

```bash
# 2. Check the evaluation results
psql $DATABASE_URL -c "
  SELECT evaluation_results::jsonb
  FROM advancement_executions
  WHERE schedule_id = '<uuid>'
  ORDER BY executed_at DESC
  LIMIT 1;
"
```

This shows detailed pass/fail for each requirement.

## Support

For issues or questions:

1. **Check logs**: `docker logs -f app | grep advancement`
2. **Query database**: See monitoring section above
3. **Review audit trail**:
   ```sql
   SELECT * FROM advancement_executions
   ORDER BY executed_at DESC
   LIMIT 50;
   ```
4. **GitHub Issues**: [github.com/maxames/ashby-auto-advance/issues](https://github.com/maxames/ashby-auto-advance/issues)
5. **Ashby API Docs**: [developers.ashbyhq.com](https://developers.ashbyhq.com)

---

Built with FastAPI and asyncpg | Version 2.0.0

