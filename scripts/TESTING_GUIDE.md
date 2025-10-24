# Advancement Rules Testing Guide

**Note:** This guide covers `test_advancement_rules.py` for production rule management and testing. For webhook testing and development, see `scripts/manual_e2e.py` (documented in `tests/README.md`). For automated testing, see the test suite in `tests/`.

## Quick Start

The interactive testing script provides a comprehensive menu-driven interface for managing and testing advancement rules.

### Basic Usage

```bash
# Start interactive menu (localhost)
python scripts/test_advancement_rules.py

# Test against staging
python scripts/test_advancement_rules.py --url https://staging.onrender.com

# Load a specific config
python scripts/test_advancement_rules.py --config scripts/configs/tech_screen.json
```

### First-Time Setup

**Important:** This script requires **REAL UUIDs from Ashby** staging or production. Do not use synthetic UUIDs from `manual_e2e.py` - they will not work.

1. **Copy and configure an example config:**
   ```bash
   cd scripts/configs
   cp example_tech_screen.json my_tech_screen.json
   ```

2. **Get REAL UUIDs from Ashby** staging/production (see configs/README.md for detailed instructions):
   - Interview Plan ID (from Ashby → Settings → Interview Plans)
   - Interview Stage ID (from Ashby → Settings → Interview Plans → Stages)
   - Interview IDs (from Ashby → Settings → Interviews)
   - (Optional) Job ID (from Ashby → Jobs)

3. **Paste real UUIDs into your config file**
   - These must match actual data in your Ashby environment
   - Test against staging environment first

4. **Run the script:**
   ```bash
   python scripts/test_advancement_rules.py --config scripts/configs/my_tech_screen.json
   ```

## Testing Architecture

This project has a three-layer testing pyramid. Understanding which layer to use will save you time and prevent confusion.

### The Three Testing Layers

```
                    Production Testing
                  (Slow, Real Data, Real API)
                test_advancement_rules.py
                         /\
                        /  \
                       /    \
                      /      \
            Development Testing
          (Medium, Synthetic, Real App)
              manual_e2e.py
                   /\
                  /  \
                 /    \
                /      \
         Automated Testing
    (Fast, Synthetic, Mocked APIs)
          pytest tests/
```

### Layer 1: Automated Tests (Fastest)

**Location:** `tests/` directory
**Purpose:** Comprehensive automated testing with mocks
**Data:** Synthetic (generated UUIDs)
**APIs:** Mocked (no real Ashby API calls)
**Coverage:** 72% code coverage

**What it includes:**
- Unit tests (~100 tests) - Individual function testing
- Integration tests (~60 tests) - Service workflows with real database
- E2E tests (~10 tests) - Complete HTTP flows with mocked Ashby API
- Contract tests (~20 tests) - Payload validation

**When to use:**
- Development of new features
- Regression testing
- CI/CD pipeline
- Fast feedback loops

**Run with:**
```bash
# All tests
pytest tests/ -v

# Fast tests only
pytest tests/unit tests/contracts -v

# E2E with mocks
pytest tests/e2e -v
```

### Layer 2: Interactive Development Testing (Medium)

**Tool:** `scripts/manual_e2e.py`
**Purpose:** Test webhook ingestion and processing interactively
**Data:** Synthetic (randomly generated UUIDs)
**APIs:** Real local app (no Ashby API mocking)
**Coverage:** Webhook handling, database writes

**What it does:**
- Creates fake interview schedules via webhooks
- Tests webhook signature validation
- Validates database schema and writes
- Simulates different interview scenarios (panel, single, etc.)
- Can replay production webhooks from saved JSON

**When to use:**
- Developing webhook handling code
- Debugging webhook processing issues
- Testing webhook signature validation
- Replaying problematic production webhooks

**Limitations:**
- Cannot test advancement rules (data doesn't exist in Ashby)
- Cannot test Ashby API integrations
- Good for webhook ingestion only

**Run with:**
```bash
# Interactive menu
python scripts/manual_e2e.py

# Specific scenario
python scripts/manual_e2e.py --scenario panel

# Replay production webhook
python scripts/manual_e2e.py --replay webhook.json
```

### Layer 3: Production Testing & Management (Slowest)

**Tool:** `scripts/test_advancement_rules.py` (this guide)
**Purpose:** Manage rules and test against real data
**Data:** Real (actual candidates from Ashby)
**APIs:** Real Ashby API calls
**Coverage:** End-to-end production workflows

**What it does:**
- Full CRUD operations on advancement rules
- Tests rules against real completed interviews
- Monitors rule performance and execution history
- Views statistics and dry-run results
- Debugs real candidate advancement failures

**When to use:**
- Creating production advancement rules
- Testing rules against real staging data
- Monitoring production rule performance
- Debugging why real candidates didn't advance
- Production operations and troubleshooting

**Limitations:**
- Requires real Ashby environment (staging/production)
- Won't work with synthetic data from manual_e2e.py
- Slower due to real API calls

**Run with:**
```bash
# Interactive menu (default: localhost)
python scripts/test_advancement_rules.py

# Test against staging
python scripts/test_advancement_rules.py --url https://staging.onrender.com

# Load config with real UUIDs
python scripts/test_advancement_rules.py --config scripts/configs/my_real_config.json
```

### Which Tool Should I Use?

**Decision Guide:**

| What are you doing? | Use this tool |
|---------------------|---------------|
| Writing new code | Automated tests (`pytest`) |
| Testing webhook handling | `manual_e2e.py` |
| Creating production rules | `test_advancement_rules.py` |
| Debugging a real candidate issue | `test_advancement_rules.py` |
| Running CI/CD | Automated tests |
| Monitoring production | `test_advancement_rules.py` |
| Replaying a webhook | `manual_e2e.py --replay` |

## Understanding the Testing Scripts

This section clarifies the relationship between the two interactive testing scripts and why they don't work together end-to-end.

### Two Different Interactive Tools

The project includes TWO interactive testing scripts with completely different purposes:

| Feature | manual_e2e.py | test_advancement_rules.py |
|---------|---------------|---------------------------|
| **Purpose** | Test webhook ingestion | Manage advancement rules |
| **Data type** | Synthetic (fake UUIDs) | Real (from Ashby) |
| **Creates data** | Yes (schedules in DB) | No (uses existing) |
| **Tests rules** | No | Yes |
| **Requires Ashby API** | No | Yes |
| **Menu options** | 4 scenarios | 17 features |
| **Use in production** | No (dev only) | Yes (production ops) |

### Critical Difference: Synthetic vs Real Data

**`manual_e2e.py` creates fake data:**
- Generates random UUIDs (`uuid4()`)
- Creates schedules/events in your local database
- Data does NOT exist in Ashby systems
- Good for testing webhook processing code

**`test_advancement_rules.py` requires real data:**
- Uses actual candidate/job/interview UUIDs from Ashby
- Makes real API calls to Ashby
- Requires data to exist in Ashby staging/production
- Good for testing business logic with real scenarios

### Why They Don't Work Together End-to-End

**This is a common source of confusion!**

You might think:
1. Run `manual_e2e.py` to create test interviews
2. Use `test_advancement_rules.py` to test rules against those interviews

**This WILL NOT WORK because:**

When `test_advancement_rules.py` evaluates a rule, it needs to:
- Fetch candidate information from Ashby API (`GET /candidate.info`)
- Fetch job details from Ashby API (`GET /job.info`)
- Advance the candidate via Ashby API (`POST /application.moveToInterviewStage`)

Since the data created by `manual_e2e.py` doesn't exist in Ashby, you'll get:
- `404 Not Found` errors from Ashby API
- "Candidate not found" failures
- API call failures

**The automated test suite already covers this!** The `tests/e2e/` tests do complete webhook → advancement flows with mocked Ashby API responses. You don't need manual_e2e.py for this.

### Recommended Workflows

**Development Workflow (Local Testing):**
```bash
# 1. Test webhook handling with synthetic data
python scripts/manual_e2e.py --scenario panel

# 2. Manage rules (CRUD operations only - don't test against synthetic data)
python scripts/test_advancement_rules.py
# → Use menu options 1-7 (config and rule management)
# → DON'T use menu option 8 with manual_e2e schedule_ids

# 3. Run automated tests for complete flows
pytest tests/e2e/test_http_advancement_flow.py -v
```

**Staging Workflow (Real Data Testing):**
```bash
# 1. Get real UUIDs from Ashby staging
# → Go to Ashby staging environment
# → Copy interview_plan_id, interview_stage_id, interview_ids

# 2. Create config with real IDs
cd scripts/configs
cp example_tech_screen.json staging_tech_screen.json
# → Edit file with real UUIDs

# 3. Test rules against real completed interviews
python scripts/test_advancement_rules.py --url https://staging.onrender.com \
  --config scripts/configs/staging_tech_screen.json

# → Use menu option 4 to create rule
# → Use menu option 8 to test against REAL schedule_id from Ashby
# → Use menu option 11 to monitor results
```

**Production Workflow (Monitoring):**
```bash
# Use test_advancement_rules.py to monitor live rules
python scripts/test_advancement_rules.py --url https://production.onrender.com

# → Menu option 11: View statistics dashboard
# → Menu option 12: Check recent executions
# → Menu option 13: View dry-run results
# → Menu option 8: Debug specific candidate issues
```

## Features

### Configuration Management (Menu 1-3)

**1. Select/Load config file**
- Browse available config files in `scripts/configs/`
- Load a config to use for rule creation
- Validates required fields

**2. View current config**
- Shows all loaded config details
- Displays interviews and score fields

**3. Edit config values**
- Modify UUIDs interactively
- Save changes to file

### Rule Management (Menu 4-7)

**4. Create new rule (wizard)**
- Step-by-step guided rule creation
- Uses loaded config for UUIDs
- Preview before creating
- Creates rule via API

**5. List all rules**
- Shows all active rules
- Displays key information (scope, requirements, creation date)
- Option to view details of specific rule

**6. View rule details**
- Full details of a specific rule
- Shows all requirements and actions
- Displays field paths and thresholds

**7. Delete rule**
- Soft-delete with confirmation
- Shows rule details before deletion
- Requires typing "yes" to confirm

### Testing & Evaluation (Menu 8-10)

**8. Test rule against candidate**
- Manually trigger evaluation for a schedule or application
- Shows whether candidate is ready for advancement
- Displays blocking reasons
- Shows detailed evaluation results

**9. Test all rules (batch)**
- Finds recent completed schedules
- Tests each against active rules
- Summary of ready vs blocked candidates

**10. View evaluation results**
- Query past evaluation results from database
- Shows execution history for a schedule
- Displays evaluation details and failure reasons

### Monitoring (Menu 11-14)

**11. View statistics dashboard**
- Active rules count
- Pending evaluations
- Execution counts by status
- Recent failures

**12. Check recent executions**
- Table of recent advancement executions
- Filterable by limit
- Shows status and timestamps

**13. View dry-run results**
- Shows what would have happened
- Includes stage transitions
- Useful for testing rules safely

**14. Compare dry-run vs production**
- Finds schedules with both dry-run and real executions
- Helps verify rule accuracy

### Utilities (Menu 15-17)

**15. Health check**
- Verify server connection
- Check database status
- Check scheduler status

**16. Switch environment**
- Presets for localhost, staging, production
- Custom URL option
- Validates connection before switching

**17. Check server dry-run status**
- Infers dry-run mode from recent executions
- Helps verify server configuration

## Workflows

### Creating Your First Rule

**Prerequisites:** Get REAL UUIDs from Ashby staging environment first (see First-Time Setup).

1. **Prepare:** Get real UUIDs from Ashby staging
   - Interview Plan ID
   - Interview Stage ID
   - Interview IDs

2. **Load a config:** Menu option 1
   - Select existing config or create new one

3. **Edit UUIDs if needed:** Menu option 3
   - Paste real UUIDs from Ashby

4. **Create rule with wizard:** Menu option 4
   - Choose global or job-specific
   - Select interviews to include
   - Set score thresholds
   - Preview and confirm

5. **View created rule:** Menu option 6
   - Verify requirements and actions

6. **Test against a real staging candidate:** Menu option 8
   - Use a REAL schedule_id from Ashby staging
   - Do NOT use schedule_ids from manual_e2e.py

### Testing Rules Safely

**Note:** Use real staging environment for testing, not synthetic data.

1. **Enable dry-run mode on server:**
   ```bash
   export ADVANCEMENT_DRY_RUN_MODE=true
   ```

2. **Create test rule:** Menu option 4
   - Use real UUIDs from staging

3. **Test against real staging candidates:** Menu option 8 or 9
   - Find completed interviews in Ashby staging
   - Get real schedule_ids

4. **View dry-run results:** Menu option 13
   - Verify what would happen

5. **Verify results look correct**
   - Check evaluation logic
   - Validate thresholds

6. **Disable dry-run mode:**
   ```bash
   export ADVANCEMENT_DRY_RUN_MODE=false
   ```

### Monitoring Production Rules

**Primary use case for this tool in production.**

1. **Check statistics:** Menu option 11
   - See success rates
   - Identify failures

2. **Review recent executions:** Menu option 12
   - Spot patterns
   - Find anomalies

3. **Investigate failures:**
   - Note failed execution IDs
   - Use menu option 10 to get details
   - Check evaluation results JSON

### Debugging Failed Evaluations

1. **Get schedule_id or application_id from Ashby**

2. **Trigger manual evaluation:** Menu option 8
   - Shows blocking reason
   - Displays evaluation details

3. **Common blocking reasons:**
   - `no_matching_rule` - No rule configured for this plan/stage
   - `no_feedback_submitted` - Missing feedback
   - `feedback_too_recent_30min_wait` - Within wait period
   - `requirements_not_met` - Scores don't pass thresholds

4. **View past evaluation attempts:** Menu option 10

## Environment Variables

```bash
# Base URL for testing (default: http://localhost:8000)
export TEST_BASE_URL=https://staging.onrender.com

# Database connection for direct queries
export DATABASE_URL=postgresql://user:pass@host/db

# Server-side dry-run mode (set on server, not client)
export ADVANCEMENT_DRY_RUN_MODE=true
```

## Tips & Best Practices

1. **Always use dry-run mode first** when testing new rules
2. **Keep configs in version control** for different environments
3. **Document your score field names** to avoid confusion
4. **Test with real completed schedules** from your staging environment
5. **Monitor statistics regularly** to catch issues early
6. **Start with job-specific rules** before creating global rules
7. **Use the wizard** for rule creation - it validates as you go
8. **Use staging environment** for testing, never production for experiments
9. **Don't mix synthetic and real data** - they serve different purposes

## Common Confusion & FAQs

### Why can't I test rules against manual_e2e data?

**The Problem:**

When you run `manual_e2e.py`, it creates interview schedules with randomly generated UUIDs. These schedules are saved to your **local database only** - they don't exist in Ashby's systems.

When `test_advancement_rules.py` evaluates a rule, it needs to make real Ashby API calls:
- `GET /candidate.info` - Fetch candidate information
- `GET /job.info` - Fetch job details
- `POST /application.moveToInterviewStage` - Advance the candidate

**What happens if you try:**

```bash
# Step 1: Create synthetic interview
python scripts/manual_e2e.py --scenario panel
# → Creates schedule_id: 12345678-90ab-cdef-... (fake UUID)
# → Saved to local database only

# Step 2: Try to test rule against it
python scripts/test_advancement_rules.py
# → Menu option 8: Test rule against candidate
# → Enter schedule_id: 12345678-90ab-cdef-...
# → ERROR: 404 Not Found from Ashby API
# → ERROR: Candidate not found
# → ERROR: Job not found
```

**The Solution:**

Use **real schedule_ids from Ashby staging environment**:

1. Log into Ashby staging
2. Find a completed interview
3. Copy the real schedule_id from the URL or API
4. Use that ID with `test_advancement_rules.py`

**Or use automated tests** (which already mock the Ashby API):

```bash
pytest tests/e2e/test_http_advancement_flow.py -v
```

### Which script should I use?

**Decision tree:**

```
Are you testing webhook handling/ingestion?
├─ YES → Use manual_e2e.py
└─ NO  → Are you managing production rules or testing against real data?
          ├─ YES → Use test_advancement_rules.py
          └─ NO  → Are you developing new features?
                   ├─ YES → Use pytest automated tests
                   └─ NO  → Re-read the Testing Architecture section!
```

**Quick reference:**

| I want to... | Use this |
|--------------|----------|
| Test if webhooks are being received | `manual_e2e.py` |
| Create a production advancement rule | `test_advancement_rules.py` |
| Debug why a real candidate didn't advance | `test_advancement_rules.py` |
| Develop new service code | `pytest tests/unit/` |
| Test complete flow with mocks | `pytest tests/e2e/` |
| Replay a production webhook | `manual_e2e.py --replay` |
| Monitor production rules | `test_advancement_rules.py` |

### How do I get real data for testing?

**Method 1: From Ashby Staging UI**

1. Log into Ashby staging environment
2. Navigate to **Applications**
3. Filter by completed interviews
4. Click on an application
5. View the **Interview Schedule** section
6. Copy the schedule UUID from the URL or details

**Method 2: From Database (if you have access)**

```sql
-- Find recent completed schedules
SELECT schedule_id, application_id, status, updated_at
FROM interview_schedules
WHERE status = 'Complete'
  AND updated_at > NOW() - INTERVAL '7 days'
ORDER BY updated_at DESC
LIMIT 10;
```

**Method 3: From Ashby API**

```bash
# List applications
curl -X POST https://api.ashbyhq.com/application.list \
  -H "Authorization: Basic YOUR_API_KEY" \
  -d '{"limit": 10}'

# Get application details (includes schedule_id)
curl -X POST https://api.ashbyhq.com/application.info \
  -H "Authorization: Basic YOUR_API_KEY" \
  -d '{"applicationId": "APP_UUID"}'
```

### Can I use both scripts together?

**Short answer: No, not end-to-end.**

They serve different purposes and work with different types of data:

- `manual_e2e.py` = Development tool for webhook testing (synthetic data)
- `test_advancement_rules.py` = Operations tool for rule management (real data)

**But you can use them in the same session for different tasks:**

```bash
# Good workflow:
# 1. Test webhook handling with synthetic data
python scripts/manual_e2e.py --scenario panel

# 2. Separately, manage rules with real data
python scripts/test_advancement_rules.py --url https://staging.onrender.com

# Bad workflow:
# 1. Create synthetic interview
python scripts/manual_e2e.py --scenario panel
# 2. Try to test rules against it (WILL FAIL!)
python scripts/test_advancement_rules.py
# → Menu 8 → Enter synthetic schedule_id → ERROR
```

### What about the automated test suite?

**The automated tests (`pytest tests/`) already cover synthetic end-to-end testing!**

The tests use:
- Synthetic data (generated UUIDs via factories)
- Real database operations
- **Mocked Ashby API responses** (no real API calls)

This gives you the best of both worlds:
- Complete flow testing (webhook → database → advancement)
- Fast and reliable (no network dependencies)
- Can run in CI/CD

**Example of what's already tested:**

```python
# tests/e2e/test_http_advancement_flow.py
async def test_complete_http_advancement_flow():
    """Full flow: webhook → feedback sync → advancement via HTTP."""
    # 1. Send webhook with synthetic data
    # 2. Create rule
    # 3. Add passing feedback
    # 4. Trigger advancement (with mocked Ashby API)
    # 5. Verify success
```

You don't need `manual_e2e.py` for this - the automated tests are better for development.

### When should I use manual_e2e.py then?

Use it for:
- Testing webhook signature validation
- Debugging webhook parsing/handling
- Validating database schema changes
- Replaying problematic production webhooks
- Interactive webhook testing during development

Don't use it for:
- Testing advancement rules
- Testing against Ashby API integrations
- End-to-end flow testing (use automated tests)

## Troubleshooting

### "Failed to connect to server"
- Check URL is correct
- Ensure server is running
- Verify network connectivity

### "No config files found"
- Check you're in the right directory
- Create config files in `scripts/configs/`

### "Rule not found"
- Verify rule_id is correct
- Check if rule was deleted (is_active=false)
- Use menu option 5 to list all rules

### "Database connection failed"
- Ensure DATABASE_URL environment variable is set
- Check database is accessible
- Verify credentials are correct

### "Invalid UUID"
- Ensure UUIDs are in correct format (8-4-4-4-12)
- Copy UUIDs directly from Ashby URLs
- Check for extra spaces or quotes

## Advanced Usage

### Direct Database Queries

The script can execute read-only database queries for advanced monitoring:

```python
# Example: Custom query in show_recent_executions()
query = """
    SELECT * FROM advancement_executions
    WHERE execution_status = 'failed'
      AND executed_at > NOW() - INTERVAL '24 hours'
"""
```

### Extending the Script

The script is modular and easy to extend:

- Add new menu options in `show_menu()`
- Implement new functions following existing patterns
- Use helper classes (ConfigManager, RuleAPIClient, TableFormatter)

### API Endpoints Used

The script uses these admin API endpoints:

- `GET /health` - Health check
- `POST /admin/create-advancement-rule` - Create rule
- `GET /admin/rules` - List rules
- `GET /admin/rules/{rule_id}` - Get rule details
- `DELETE /admin/rules/{rule_id}` - Delete rule
- `POST /admin/trigger-advancement-evaluation` - Trigger evaluation
- `GET /admin/stats` - Get statistics

## Integration with Other Testing Tools

Understanding how this script fits into the broader testing ecosystem.

### Relationship with manual_e2e.py

**Location:** `scripts/manual_e2e.py`
**Documentation:** See `tests/README.md` under "Manual Testing"
**Purpose:** Interactive webhook testing with synthetic data

**When to use it:**
- Developing webhook handling code
- Testing webhook signature validation
- Debugging webhook processing issues
- Replaying production webhooks from saved JSON files

**Key limitation:** Does NOT integrate with `test_advancement_rules.py` because it creates synthetic data that doesn't exist in Ashby.

**Example workflow:**
```bash
# Test webhook handling
python scripts/manual_e2e.py --scenario panel

# Or replay a production webhook
python scripts/manual_e2e.py --replay production_webhook.json
```

See the "Understanding the Testing Scripts" section above for detailed comparison.

### Relationship with Automated Test Suite

**Location:** `tests/` directory
**Documentation:** See `tests/README.md`
**Purpose:** Automated testing with mocks for CI/CD

**Test types available:**
- **Unit tests** (`tests/unit/`) - Fast, focused function testing
- **Integration tests** (`tests/integration/`) - Service workflows with real database
- **E2E tests** (`tests/e2e/`) - Complete HTTP flows with mocked Ashby API
- **Contract tests** (`tests/contracts/`) - Payload validation

**When to use automated tests instead of interactive scripts:**
- Writing new code (TDD workflow)
- Running in CI/CD pipeline
- Regression testing
- Fast feedback during development

**Example:**
```bash
# Run all tests
pytest tests/ -v

# Run only E2E tests (complete flows with mocks)
pytest tests/e2e/ -v

# Run specific advancement flow test
pytest tests/e2e/test_http_advancement_flow.py::test_complete_http_advancement_flow -v
```

**Key insight:** The automated test suite already covers synthetic end-to-end testing (webhook → database → advancement) with mocked Ashby APIs. You don't need `manual_e2e.py` for this - the automated tests are better for development.

### When to Use Which Tool

**Use automated tests (`pytest`) when:**
- Developing new features
- Running in CI/CD
- Need fast, reliable feedback
- Testing complete flows with mocks
- Regression testing

**Use manual_e2e.py when:**
- Testing webhook handling interactively
- Replaying production webhooks
- Debugging webhook signature issues
- Validating database schema changes

**Use test_advancement_rules.py when:**
- Creating production rules
- Testing against real staging/production data
- Monitoring production rule performance
- Debugging real candidate issues
- Managing rules operationally

### Complete Testing Workflow

**During Development:**
```bash
# 1. Write code with tests
pytest tests/unit/test_my_new_feature.py -v

# 2. Test integration
pytest tests/integration/ -v

# 3. Test HTTP layer
pytest tests/e2e/ -v

# 4. If needed, manually test webhooks
python scripts/manual_e2e.py --scenario panel
```

**Before Production Deploy:**
```bash
# 1. Run full test suite
pytest tests/ --cov=app

# 2. Test against staging with real data
python scripts/test_advancement_rules.py --url https://staging.onrender.com

# 3. Create rules in dry-run mode
# → Use menu option 4 to create rules
# → Use menu option 13 to verify dry-run results

# 4. Monitor for issues
# → Use menu option 11 for statistics
```

**In Production:**
```bash
# Monitor and manage rules
python scripts/test_advancement_rules.py --url https://production.onrender.com

# → Menu 11: Statistics dashboard
# → Menu 12: Recent executions
# → Menu 8: Debug specific candidates
```

## Support

For detailed documentation on advancement rules:
- See `docs/ADVANCEMENT_RULES.md`
- Check `scripts/configs/README.md` for config format
- Review example configs in `scripts/configs/`

For issues with the script:
- Check this guide for troubleshooting steps
- Review the script's inline documentation
- Examine error messages carefully

