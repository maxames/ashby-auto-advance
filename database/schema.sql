-- ============================================
-- Ashby Auto-Advancement System - Database Schema
-- Version: 2.0
-- Description: Complete schema for webhook ingestion
--              and automated candidate advancement
-- ============================================
-- Setup: psql $DATABASE_URL -f database/schema.sql
-- ============================================

BEGIN;

-- ============================================
-- Core Webhook Ingestion Tables
-- ============================================

-- Interview Schedules
CREATE TABLE IF NOT EXISTS interview_schedules (
    schedule_id UUID PRIMARY KEY,
    application_id UUID NOT NULL,
    interview_stage_id UUID,
    status TEXT NOT NULL,
    candidate_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    job_id UUID,
    interview_plan_id UUID,
    last_evaluated_for_advancement_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_interview_schedules_application_id
ON interview_schedules(application_id);

CREATE INDEX IF NOT EXISTS idx_interview_schedules_job
ON interview_schedules(job_id)
WHERE job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_interview_schedules_evaluation
ON interview_schedules(status, last_evaluated_for_advancement_at);

-- Composite index for advancement evaluation queries
CREATE INDEX IF NOT EXISTS idx_interview_schedules_advancement_ready
ON interview_schedules(status, last_evaluated_for_advancement_at, updated_at)
WHERE status IN ('WaitingOnFeedback', 'Complete')
  AND interview_plan_id IS NOT NULL;

-- Interview Definitions (Reference Table)
CREATE TABLE IF NOT EXISTS interviews (
    interview_id UUID PRIMARY KEY,
    title TEXT,
    external_title TEXT,
    is_archived BOOLEAN,
    is_debrief BOOLEAN,
    instructions_html TEXT,
    instructions_plain TEXT,
    job_id UUID,
    feedback_form_definition_id UUID,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Interview Events
CREATE TABLE IF NOT EXISTS interview_events (
    event_id UUID PRIMARY KEY,
    schedule_id UUID NOT NULL REFERENCES interview_schedules(schedule_id) ON DELETE CASCADE,
    interview_id UUID NOT NULL REFERENCES interviews(interview_id),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    feedback_link TEXT,
    location TEXT,
    meeting_link TEXT,
    has_submitted_feedback BOOLEAN,
    extra_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_interview_events_schedule_id
ON interview_events(schedule_id);

CREATE INDEX IF NOT EXISTS idx_interview_events_interview_id
ON interview_events(interview_id);

CREATE INDEX IF NOT EXISTS idx_interview_events_start_time
ON interview_events(start_time);

-- Interview Assignments (Interviewers)
CREATE TABLE IF NOT EXISTS interview_assignments (
    event_id UUID NOT NULL REFERENCES interview_events(event_id) ON DELETE CASCADE,
    interviewer_id UUID NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    global_role TEXT,
    training_role TEXT,
    is_enabled BOOLEAN,
    manager_id UUID,
    interviewer_pool_id UUID,
    interviewer_pool_title TEXT,
    interviewer_pool_is_archived BOOLEAN,
    training_path JSONB,
    interviewer_updated_at TIMESTAMPTZ,
    PRIMARY KEY (event_id, interviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_interview_assignments_email
ON interview_assignments(email);

-- Webhook Audit Log
CREATE TABLE IF NOT EXISTS ashby_webhook_payloads (
    id BIGSERIAL PRIMARY KEY,
    schedule_id UUID,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    action TEXT,
    payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_ashby_webhook_payloads_received_at
ON ashby_webhook_payloads(received_at DESC);

CREATE INDEX IF NOT EXISTS idx_ashby_webhook_payloads_schedule_id
ON ashby_webhook_payloads(schedule_id);

-- ============================================
-- Feedback Application Tables
-- ============================================

-- Feedback Form Definitions
CREATE TABLE IF NOT EXISTS feedback_form_definitions (
    form_definition_id UUID PRIMARY KEY,
    title TEXT,
    definition JSONB NOT NULL,
    is_archived BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_forms_active
ON feedback_form_definitions(form_definition_id)
WHERE NOT is_archived;

-- Slack Users Directory
CREATE TABLE IF NOT EXISTS slack_users (
    slack_user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    real_name TEXT,
    display_name TEXT,
    is_bot BOOLEAN DEFAULT false,
    deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slack_users_email
ON slack_users(email);

-- Feedback Reminders Tracking
CREATE TABLE IF NOT EXISTS feedback_reminders_sent (
    event_id UUID NOT NULL REFERENCES interview_events(event_id) ON DELETE CASCADE,
    interviewer_id UUID NOT NULL,
    slack_user_id TEXT NOT NULL REFERENCES slack_users(slack_user_id),
    slack_channel_id TEXT NOT NULL,
    slack_message_ts TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    opened_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    PRIMARY KEY (event_id, interviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_reminders_sent_at
ON feedback_reminders_sent(sent_at);

CREATE INDEX IF NOT EXISTS idx_feedback_reminders_pending
ON feedback_reminders_sent(event_id)
WHERE submitted_at IS NULL;

-- Feedback Drafts
CREATE TABLE IF NOT EXISTS feedback_drafts (
    event_id UUID NOT NULL REFERENCES interview_events(event_id) ON DELETE CASCADE,
    interviewer_id UUID NOT NULL,
    form_values JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (event_id, interviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_drafts_updated
ON feedback_drafts(updated_at DESC);

-- ============================================
-- Auto-Advancement System Tables
-- ============================================

-- Advancement Rules Configuration
CREATE TABLE IF NOT EXISTS advancement_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID,
    interview_plan_id UUID NOT NULL,
    interview_stage_id UUID NOT NULL,
    target_stage_id UUID,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE advancement_rules IS 'Configuration for automatic candidate advancement rules';
COMMENT ON COLUMN advancement_rules.job_id IS 'Optional job filter - NULL means applies to all jobs';
COMMENT ON COLUMN advancement_rules.target_stage_id IS 'Target stage to advance to - NULL means next sequential stage';

CREATE INDEX IF NOT EXISTS idx_advancement_rules_active
ON advancement_rules(interview_plan_id, interview_stage_id)
WHERE is_active;

-- Advancement Rule Requirements
CREATE TABLE IF NOT EXISTS advancement_rule_requirements (
    requirement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES advancement_rules ON DELETE CASCADE,
    interview_id UUID NOT NULL,
    score_field_path TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold_value TEXT NOT NULL,
    is_required BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE advancement_rule_requirements IS 'Defines scoring requirements for advancement rules';
COMMENT ON COLUMN advancement_rule_requirements.score_field_path IS 'JSON path to score field in feedback submission';
COMMENT ON COLUMN advancement_rule_requirements.is_required IS 'If false, interview is optional for advancement';

CREATE INDEX IF NOT EXISTS idx_advancement_rule_requirements_rule
ON advancement_rule_requirements(rule_id);

-- Advancement Rule Actions
CREATE TABLE IF NOT EXISTS advancement_rule_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES advancement_rules ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    action_config JSONB,
    execution_order INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE advancement_rule_actions IS 'Actions to execute when rule conditions are met';
COMMENT ON COLUMN advancement_rule_actions.action_config IS 'JSON configuration for action (e.g., archive_reason_id)';

CREATE INDEX IF NOT EXISTS idx_advancement_rule_actions_rule
ON advancement_rule_actions(rule_id, execution_order);

-- Feedback Submissions from Ashby API
CREATE TABLE IF NOT EXISTS feedback_submissions (
    feedback_id UUID PRIMARY KEY,
    application_id UUID NOT NULL,
    event_id UUID NOT NULL REFERENCES interview_events ON DELETE CASCADE,
    interviewer_id UUID NOT NULL,
    interview_id UUID NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    submitted_values JSONB NOT NULL,
    processed_for_advancement_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE feedback_submissions IS 'Feedback submissions synced from Ashby API';
COMMENT ON COLUMN feedback_submissions.processed_for_advancement_at IS 'Timestamp when feedback was processed for advancement decision';

CREATE INDEX IF NOT EXISTS idx_feedback_submissions_event
ON feedback_submissions(event_id);

CREATE INDEX IF NOT EXISTS idx_feedback_submissions_application
ON feedback_submissions(application_id);

CREATE INDEX IF NOT EXISTS idx_feedback_submissions_pending
ON feedback_submissions(application_id, processed_for_advancement_at)
WHERE processed_for_advancement_at IS NULL;

-- Advancement Execution Audit Trail
CREATE TABLE IF NOT EXISTS advancement_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id UUID NOT NULL REFERENCES interview_schedules ON DELETE CASCADE,
    application_id UUID NOT NULL,
    rule_id UUID REFERENCES advancement_rules,
    from_stage_id UUID,
    to_stage_id UUID,
    execution_status TEXT NOT NULL,
    failure_reason TEXT,
    evaluation_results JSONB,
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    executed_by TEXT DEFAULT 'system'
);

COMMENT ON TABLE advancement_executions IS 'Complete audit trail of all advancement decisions and executions';
COMMENT ON COLUMN advancement_executions.evaluation_results IS 'Detailed JSON of rule evaluation for debugging';

CREATE INDEX IF NOT EXISTS idx_advancement_executions_schedule
ON advancement_executions(schedule_id, executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_advancement_executions_status
ON advancement_executions(execution_status, executed_at DESC);

CREATE INDEX IF NOT EXISTS idx_advancement_executions_application
ON advancement_executions(application_id, executed_at DESC);

-- ============================================
-- Metadata Cache Tables (for UI)
-- ============================================

-- Jobs cache for UI dropdowns
CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT,
    department_id UUID,
    default_interview_plan_id UUID,
    location_name TEXT,
    employment_type TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status) WHERE status = 'Open';

COMMENT ON TABLE jobs IS 'Cached job data from Ashby for UI metadata';

-- Interview Plans cache
CREATE TABLE IF NOT EXISTS interview_plans (
    interview_plan_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    is_archived BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_plans_active ON interview_plans(interview_plan_id) WHERE NOT is_archived;

COMMENT ON TABLE interview_plans IS 'Cached interview plan data from Ashby for UI metadata';

-- Job to Interview Plan mapping (many-to-many)
CREATE TABLE IF NOT EXISTS job_interview_plans (
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    interview_plan_id UUID NOT NULL REFERENCES interview_plans(interview_plan_id) ON DELETE CASCADE,
    is_default BOOLEAN DEFAULT false,
    PRIMARY KEY (job_id, interview_plan_id)
);

CREATE INDEX IF NOT EXISTS idx_job_interview_plans_job ON job_interview_plans(job_id);
CREATE INDEX IF NOT EXISTS idx_job_interview_plans_plan ON job_interview_plans(interview_plan_id);

COMMENT ON TABLE job_interview_plans IS 'Many-to-many relationship between jobs and interview plans';

-- Interview Stages cache
CREATE TABLE IF NOT EXISTS interview_stages (
    interview_stage_id UUID PRIMARY KEY,
    interview_plan_id UUID NOT NULL REFERENCES interview_plans(interview_plan_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    type TEXT,
    order_in_plan INTEGER NOT NULL,
    interview_stage_group_id UUID,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interview_stages_plan ON interview_stages(interview_plan_id, order_in_plan);

COMMENT ON TABLE interview_stages IS 'Cached interview stages from Ashby for UI metadata';

-- ============================================
-- Migration Tracking
-- ============================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

-- Record schema versions
INSERT INTO schema_migrations (version, name, description)
VALUES
    (1, 'initial_schema', 'Core webhook tables + feedback app tables'),
    (2, 'advancement_system', 'Add advancement automation tables and tracking fields')
ON CONFLICT (version) DO NOTHING;

COMMIT;

