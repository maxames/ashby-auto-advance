-- ============================================
-- Ashby Auto-Advancement System - Schema Migration
-- Version: 2.0
-- Description: Add advancement automation tables and fields
-- ============================================
-- Setup: psql $DATABASE_URL -f database/add_advancement_tables.sql
-- ============================================

BEGIN;

-- ============================================
-- Modify Existing Tables
-- ============================================

-- Add advancement tracking fields to interview_schedules
ALTER TABLE interview_schedules
ADD COLUMN IF NOT EXISTS job_id UUID,
ADD COLUMN IF NOT EXISTS interview_plan_id UUID,
ADD COLUMN IF NOT EXISTS last_evaluated_for_advancement_at TIMESTAMPTZ;

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_interview_schedules_job
ON interview_schedules(job_id)
WHERE job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_interview_schedules_evaluation
ON interview_schedules(status, last_evaluated_for_advancement_at);

-- ============================================
-- Advancement Rules System
-- ============================================

-- Primary configuration table for advancement rules
CREATE TABLE IF NOT EXISTS advancement_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID,  -- Nullable: if NULL, applies to all jobs
    interview_plan_id UUID NOT NULL,
    interview_stage_id UUID NOT NULL,
    target_stage_id UUID,  -- Nullable: if NULL, advance to next sequential stage
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

-- Specifies which interviews and scores must pass for a rule
CREATE TABLE IF NOT EXISTS advancement_rule_requirements (
    requirement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES advancement_rules ON DELETE CASCADE,
    interview_id UUID NOT NULL,  -- Which interview definition
    score_field_path TEXT NOT NULL,  -- e.g., "overall_score", "technical_skills"
    operator TEXT NOT NULL,  -- e.g., ">=", "==", "<=", ">", "<"
    threshold_value TEXT NOT NULL,  -- Stored as text, cast during evaluation
    is_required BOOLEAN DEFAULT true,  -- False = optional interview
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE advancement_rule_requirements IS 'Defines scoring requirements for advancement rules';
COMMENT ON COLUMN advancement_rule_requirements.score_field_path IS 'JSON path to score field in feedback submission';
COMMENT ON COLUMN advancement_rule_requirements.is_required IS 'If false, interview is optional for advancement';

CREATE INDEX IF NOT EXISTS idx_advancement_rule_requirements_rule
ON advancement_rule_requirements(rule_id);

-- Defines what happens when a rule passes (or fails)
CREATE TABLE IF NOT EXISTS advancement_rule_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES advancement_rules ON DELETE CASCADE,
    action_type TEXT NOT NULL,  -- e.g., "advance_stage", "send_rejection_notification"
    action_config JSONB,  -- Flexible config per action type
    execution_order INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE advancement_rule_actions IS 'Actions to execute when rule conditions are met';
COMMENT ON COLUMN advancement_rule_actions.action_config IS 'JSON configuration for action (e.g., archive_reason_id)';

CREATE INDEX IF NOT EXISTS idx_advancement_rule_actions_rule
ON advancement_rule_actions(rule_id, execution_order);

-- ============================================
-- Feedback Storage
-- ============================================

-- Stores feedback fetched from Ashby API
CREATE TABLE IF NOT EXISTS feedback_submissions (
    feedback_id UUID PRIMARY KEY,  -- From Ashby API
    application_id UUID NOT NULL,
    event_id UUID NOT NULL REFERENCES interview_events ON DELETE CASCADE,
    interviewer_id UUID NOT NULL,
    interview_id UUID NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    submitted_values JSONB NOT NULL,  -- Full scorecard data
    processed_for_advancement_at TIMESTAMPTZ,  -- NULL = not yet evaluated
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

-- ============================================
-- Advancement Audit Trail
-- ============================================

-- Audit trail of all advancement decisions and executions
CREATE TABLE IF NOT EXISTS advancement_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id UUID NOT NULL REFERENCES interview_schedules ON DELETE CASCADE,
    application_id UUID NOT NULL,
    rule_id UUID REFERENCES advancement_rules,  -- Nullable if no rule matched
    from_stage_id UUID,
    to_stage_id UUID,
    execution_status TEXT NOT NULL,  -- "success", "failed", "dry_run", "rejected"
    failure_reason TEXT,  -- Populated on failure
    evaluation_results JSONB,  -- Detailed results of rule evaluation
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    executed_by TEXT DEFAULT 'system'  -- e.g., "system", "admin_api", "backfill"
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
-- Migration Tracking
-- ============================================

INSERT INTO schema_migrations (version, name, description)
VALUES (2, 'add_advancement_tables', 'Add advancement automation tables and tracking fields')
ON CONFLICT (version) DO NOTHING;

COMMIT;

