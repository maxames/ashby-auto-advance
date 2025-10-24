# Advancement Rules Configuration Files

This directory contains configuration templates for different interview scenarios. These configs make it easy to create advancement rules without manually typing UUIDs every time.

## How to Use

1. **Copy an example config** that matches your interview type
2. **Get UUIDs from Ashby** (see instructions below)
3. **Paste UUIDs** into your config file
4. **Save with a descriptive name** (e.g., `swe_tech_screen.json`)
5. **Use in the testing script** by selecting it from the menu

## Getting UUIDs from Ashby

### Method 1: From the Ashby UI (Recommended)

**Interview Plan ID:**
1. Log in to Ashby
2. Go to **Settings** → **Interview Plans**
3. Click on the interview plan you want to configure
4. The UUID is in the URL: `https://app.ashbyhq.com/admin/interview-plans/{INTERVIEW_PLAN_ID}`
5. Copy the UUID (looks like `01234567-89ab-cdef-0123-456789abcdef`)

**Interview Stage ID:**
1. While viewing an interview plan, scroll to the stages section
2. Click on a stage to edit it
3. The UUID is in the URL: `https://app.ashbyhq.com/admin/interview-stages/{INTERVIEW_STAGE_ID}`
4. Copy the UUID

**Interview ID:**
1. Go to **Settings** → **Interviews**
2. Click on an interview type (e.g., "Technical Screen")
3. The UUID is in the URL: `https://app.ashbyhq.com/admin/interviews/{INTERVIEW_ID}`
4. Copy the UUID

**Job ID (optional):**
1. Go to **Jobs** and click on a specific job
2. The UUID is in the URL: `https://app.ashbyhq.com/jobs/{JOB_ID}`
3. Copy the UUID
4. Use `null` for global rules that apply to all jobs

### Method 2: From the Ashby API

You can also query the Ashby API directly:

```bash
# List interview plans
curl -X POST https://api.ashbyhq.com/interviewPlan.list \
  -H "Authorization: Basic YOUR_ENCODED_API_KEY" \
  -H "Content-Type: application/json"

# List interviews
curl -X POST https://api.ashbyhq.com/interview.list \
  -H "Authorization: Basic YOUR_ENCODED_API_KEY" \
  -H "Content-Type: application/json"
```

## Finding Score Field Names

Score field names come from your Ashby feedback forms. To find them:

### Method 1: Check a Submitted Feedback

1. Go to a candidate who has completed feedback
2. View their feedback submission
3. Note the field names (e.g., "Overall Score", "Technical Skills")

**Common field name conventions:**
- Field labels in Ashby UI may differ from actual field names
- Usually snake_case: `overall_score`, `technical_skills`, `culture_fit`
- Sometimes camelCase: `overallScore`, `technicalSkills`

### Method 2: Query the Database

If you have database access:

```sql
SELECT submitted_values
FROM feedback_submissions
WHERE interview_id = 'YOUR_INTERVIEW_ID'
LIMIT 1;
```

The JSON keys are your score field names.

### Method 3: Check Feedback Forms Settings

1. Go to **Settings** → **Feedback Forms**
2. Edit a feedback form
3. Look at the field IDs/names

## Configuration Format

```json
{
  "name": "Human-readable name",
  "description": "What this config is for",
  "job_id": null,  // null = global, or paste job UUID for job-specific
  "interview_plan_id": "UUID of the interview plan",
  "interview_stage_id": "UUID of the stage (e.g., Tech Screen, Onsite)",
  "target_stage_id": null,  // null = next sequential, or paste UUID to skip stages
  "interviews": [
    {
      "interview_id": "UUID of interview type",
      "name": "Human-readable interview name",
      "score_fields": ["field1", "field2"]  // Available score fields
    }
  ],
  "default_threshold": "3",  // Default minimum score
  "default_operator": ">="  // Default comparison operator
}
```

## Example Scenarios

### Tech Screen (Single Interviewer)
**Use:** `example_tech_screen.json`
- One interviewer conducts technical assessment
- Advance to next stage if overall_score >= 3

### Onsite (Multiple Sequential Interviews)
**Use:** `example_onsite.json`
- Multiple separate interviews (system design, culture, hiring manager)
- ALL interviews must have passing scores
- Advances directly to offer stage (skipping intermediate stages)

### Panel Interview (Multiple Interviewers, One Event)
**Use:** `example_panel_interview.json`
- Single interview with 2+ interviewers
- ALL interviewers must submit feedback
- ALL submitted scores must pass threshold

## Tips

1. **Start with global rules** (`job_id: null`) to test across all jobs
2. **Use explicit target_stage_id** when you want to skip stages
3. **Keep configs version-controlled** for different environments (dev/staging/prod)
4. **Document your score field names** to avoid confusion
5. **Test in dry-run mode first** before enabling real advancements

## Troubleshooting

**"Invalid UUID" errors:**
- Make sure UUIDs are in the correct format (8-4-4-4-12 hex characters)
- Check for extra spaces or quotation marks
- Verify the UUID exists in Ashby (might have been deleted)

**"Score field not found" errors:**
- Double-check the exact field name from a real feedback submission
- Field names are case-sensitive
- Remove any spaces or special characters

**"No matching rule" errors:**
- Ensure interview_plan_id matches the plan being used
- Ensure interview_stage_id matches the current stage
- Check if job_id is restricting the rule to a specific job

## Getting Help

See the main documentation in `docs/ADVANCEMENT_RULES.md` for:
- Complete rule creation guide
- Evaluation logic
- Monitoring and troubleshooting
- Best practices

