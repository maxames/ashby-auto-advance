"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.admin import router as admin_router
from app.api.slack_interactions import router as slack_router
from app.api.webhooks import limiter
from app.api.webhooks import router as webhook_router
from app.core.config import settings
from app.core.database import db
from app.core.logging import logger, setup_logging
from app.services.metadata_sync import (
    sync_interview_plans,
    sync_interview_stages,
    sync_jobs,
)
from app.services.scheduler import (
    scheduler,
    setup_scheduler,
    shutdown_scheduler,
    start_scheduler,
)
from app.services.sync import sync_feedback_forms, sync_interviews, sync_slack_users

# Configure logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    logger.info("application_starting")
    await db.connect()

    # Run initial sync BEFORE starting scheduler
    try:
        await sync_feedback_forms()
        await sync_interviews()
        await sync_jobs()
        await sync_interview_plans()
        await sync_interview_stages()
        await sync_slack_users()
    except Exception:
        logger.exception("initial_sync_failed")

    # Now start scheduler with fresh data
    setup_scheduler()
    start_scheduler()

    logger.info("application_ready")

    yield

    # Shutdown
    logger.info("application_shutting_down")
    shutdown_scheduler()
    await db.disconnect()
    logger.info("application_stopped")


# Create FastAPI app
app = FastAPI(
    title="Ashby Auto-Advancement",
    description="Automated candidate advancement system for Ashby ATS",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_urls,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(webhook_router)
app.include_router(slack_router)
app.include_router(admin_router)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint.

    Verifies database connectivity and reports pool stats plus metadata sync status.

    Returns:
        dict: Health status with database, scheduler, pool, and metadata information

    Raises:
        HTTPException: 503 if database is unavailable
    """
    try:
        await db.fetchval("SELECT 1")

        # Get connection pool stats
        if not db.pool:
            raise RuntimeError("Database pool not initialized")

        pool_size = db.pool.get_size()
        pool_free = db.pool.get_idle_size()

        # Check metadata sync status
        metadata_status = await db.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM jobs) as jobs_count,
                (SELECT COUNT(*) FROM interview_plans) as plans_count,
                (SELECT COUNT(*) FROM interview_stages) as stages_count,
                (SELECT MAX(synced_at) FROM jobs) as last_sync
            """
        )

        return {
            "status": "healthy",
            "database": "connected",
            "scheduler": "running" if scheduler.running else "stopped",
            "pool": {
                "size": pool_size,
                "free": pool_free,
                "in_use": pool_size - pool_free,
            },
            "metadata": {
                "jobs": metadata_status["jobs_count"] if metadata_status else 0,
                "plans": metadata_status["plans_count"] if metadata_status else 0,
                "stages": metadata_status["stages_count"] if metadata_status else 0,
                "last_synced": (
                    metadata_status["last_sync"].isoformat()
                    if metadata_status and metadata_status["last_sync"]
                    else None
                ),
            },
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Database unavailable") from e


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Ashby Auto-Advancement System"}
