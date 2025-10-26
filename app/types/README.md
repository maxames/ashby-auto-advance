# Type Definitions

## Purpose

This directory contains TypedDict definitions for runtime data structures:

- `ashby.py` - Ashby API response types (only fields we consume)
- `slack.py` - Slack API payload types
- `database.py` - Database record types (only tables we fetch as dicts)

## Conventions

- **TypedDict suffix**: All TypedDicts end with `TD`
- **NotRequired**: Use for nullable/optional database columns
- **total=False**: Use when most fields are optional
- **Incremental**: Add types only when actually needed

## When to Use TypedDict vs Pydantic

**Use TypedDict for:**
- Database records (`asyncpg.Record` → dict conversion)
- External API responses (Ashby, Slack)
- Internal data structures passed between layers
- Webhook payloads

**Use Pydantic (in `/app/schemas/`) for:**
- API request validation
- API response serialization
- OpenAPI documentation
- Data that needs validation/coercion

**Don't duplicate:** If a Pydantic model exists, don't create a TypedDict for the same shape.

## Database Types

`database.py` must track `database/schema.sql` manually. When adding types:

1. Check if a Pydantic model exists first
2. Only add types for records actually fetched and returned as dicts
3. Match field names exactly to schema.sql
4. Use `NotRequired` for nullable columns
5. Document which service functions use each type

Current types:
- `InterviewScheduleRecordTD` - advancement.py, admin.py
- `AdvancementRuleRecordTD` - rules.py
- `AdvancementRequirementRecordTD` - rules.py
- `AdvancementActionRecordTD` - rules.py
- `FeedbackSubmissionRecordTD` - advancement.py

## Ashby/Slack Types

Mirror only fields you actually consume. Don't try to model entire APIs.

