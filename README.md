# Ashby Auto-Advancement

> Automated candidate advancement system for Ashby ATS

[![CI](https://github.com/maxames/ashby-auto-advance/workflows/CI/badge.svg)](https://github.com/maxames/ashby-auto-advance/actions)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A FastAPI application that automatically advances candidates through interview stages based on configurable rules. Polls feedback from Ashby API, evaluates scores against thresholds, and moves candidates forward or notifies recruiters of rejections.

## Features

- Webhook Integration: Real-time ingestion of interview schedule updates from Ashby
- Automated Feedback Polling: Syncs feedback submissions from Ashby API every 30 minutes
- Rule-Based Evaluation Engine: Configurable score thresholds and advancement criteria
- Automatic Stage Advancement: Moves candidates forward when all requirements pass
- Rejection Notifications: Sends Slack alerts to recruiters when candidates fail criteria
- Dry-Run Mode: Test rules safely without making actual changes
- Full Audit Trail: Complete history of all advancement decisions in database
- Idempotent Processing: Safe handling of duplicate webhooks and submissions
- Comprehensive Logging: Structured logging with `structlog` for observability
- Rate Limiting: Built-in protection against webhook spam
- Clean Architecture: Clear separation of concerns for easy maintenance

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Slack workspace with admin access
- Ashby ATS account with API access

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/maxames/ashby-auto-advance.git
   cd ashby-auto-advance
   ```

2. Create virtual environment
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

4. Set up database
   ```bash
   createdb ashby_auto_advance
   psql $DATABASE_URL -f database/schema.sql
   ```

5. Configure environment
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and secrets
   ```

6. Run the application
   ```bash
   uvicorn app.main:app --reload
   ```

The application will be available at `http://localhost:8000`. Visit `/docs` for interactive API documentation.

## Docker Setup

For the easiest setup, use Docker Compose:

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
nano .env

# Start services
docker-compose up -d

# View logs
docker-compose logs -f app
```

This starts the application and PostgreSQL database with automatic schema initialization.

## Architecture

The application follows clean architecture principles with clear separation of concerns:

```
app/
├── api/          # HTTP handlers (FastAPI routes)
├── clients/      # External API clients (Ashby, Slack)
├── services/     # Business logic and orchestration
├── core/         # Infrastructure (database, config, logging)
├── schemas/      # Pydantic schemas for API validation
├── types/        # TypedDict definitions for external APIs
└── utils/        # Generic helpers (security, time)
```

**Data Flow:**
1. Webhook Ingestion: Ashby → API → Services → Database (with job_id/interview_plan_id fetch)
2. Feedback Polling: Scheduler → Services → Ashby API → Database (every 30 min)
3. Advancement Evaluation: Scheduler → Rules Engine → Stage Advancement → Ashby API (every 30 min)
4. Rejection Workflow: Evaluation → Slack Notification → Recruiter Action → Archive Candidate

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and separation of concerns
- [API Reference](docs/API.md) - Endpoint documentation with examples
- [Deployment Guide](docs/DEPLOYMENT.md) - Deploy to Render, Railway, Fly.io, or manual
- [Advancement Rules](docs/ADVANCEMENT_RULES.md) - Rule configuration and examples

## Configuration

All configuration is managed through environment variables. See [.env.example](.env.example) for required variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `ASHBY_API_KEY` | Ashby API key for authentication | Yes |
| `ASHBY_WEBHOOK_SECRET` | Secret for webhook signature verification | Yes |
| `SLACK_BOT_TOKEN` | Slack bot token (xoxb-...) | Yes |
| `SLACK_SIGNING_SECRET` | Slack signing secret for request verification | Yes |
| `DEFAULT_ARCHIVE_REASON_ID` | Archive reason UUID from Ashby for rejections | Yes |
| `FRONTEND_URL` | Frontend URL(s) for CORS (comma-separated) | No (default: http://localhost:5173) |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No (default: INFO) |
| `ADVANCEMENT_DRY_RUN_MODE` | Test mode without real advancements | No (default: false) |
| `ADVANCEMENT_FEEDBACK_TIMEOUT_DAYS` | Days before schedule times out | No (default: 7) |
| `ADVANCEMENT_FEEDBACK_MIN_WAIT_MINUTES` | Wait period after feedback submission | No (default: 30) |
| `ADMIN_SLACK_CHANNEL_ID` | Channel ID for error alerts and rejection notifications | No |
| `EXPOSE_ERROR_DETAILS` | Include error details in API responses (set false in production) | No (default: true) |

## Testing

Run the test suite:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test categories
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests only
pytest tests/contracts/      # Contract tests only
```

Test coverage includes:
- Unit tests for security, time utilities, and field builders
- Integration tests for webhook processing, feedback flow, and reminders
- Contract tests validating Ashby/Slack payload structures

## Development

Set up the development environment:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run linter
ruff check app/

# Run type checker
pyright app/

# Run formatter
ruff format app/
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Security

For security concerns, please see [SECURITY.md](SECURITY.md).

## How It Works

1. **Setup**: Configure Ashby webhook to send interview schedule updates to your deployment
2. **Ingestion**: Application receives webhooks and fetches job_id + interview_plan_id from Ashby API
3. **Feedback Polling**: Background scheduler polls Ashby API every 30 minutes for new feedback submissions
4. **Rule Matching**: System finds advancement rule based on job + interview plan + stage
5. **Evaluation**: Checks if all interviewers submitted feedback and all scores pass thresholds
6. **Advancement**:
   - If all requirements pass: Automatically advances candidate to next stage via Ashby API
   - If requirements fail: Sends Slack notification to recruiter with rejection button
7. **Audit Trail**: All decisions and executions recorded in `advancement_executions` table

## Monitoring

The application provides several monitoring endpoints:

- `GET /health` - Health check with database connectivity and connection pool stats
- `GET /admin/stats` - Advancement metrics (executions, failures, pending evaluations, active rules)
- Structured logging for observability (JSON format in production)

## Roadmap

- [ ] Rule UI builder for non-technical users
- [ ] Machine learning for threshold optimization
- [ ] Multi-stage advancement chains
- [ ] Slack approval workflow for edge cases
- [ ] Analytics dashboard for advancement metrics

## Support

For questions or issues:
- Open a GitHub issue
- Check the [documentation](docs/)
- Review the [deployment guide](docs/DEPLOYMENT.md)

---

Built using FastAPI, asyncpg, and the Slack SDK
