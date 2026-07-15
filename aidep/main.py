"""
AIDEP — Autonomous Instruction Data Engineering Platform
FastAPI Application Factory
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aidep.api.routes.seed import router as seed_router
from aidep.api.routes.instructions import router as instructions_router
from aidep.api.routes.pipeline import (
    examples_router,
    validation_router,
    quality_router,
    dataset_router,
    pipeline_router,
)
from aidep.core.config import get_settings
from aidep.database.base import init_db

logger = logging.getLogger(__name__)

# ── Configure logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — run setup on startup, teardown on shutdown."""
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("  AIDEP — Autonomous Instruction Data Engineering Platform")
    logger.info("  Version : %s", settings.app_version)
    logger.info("  Env     : %s", settings.app_env)
    logger.info("  LLM     : %s", settings.llm_model)
    logger.info("=" * 60)

    # Initialise database (creates tables if not present)
    try:
        init_db(database_url=settings.database_url, echo=settings.db_echo)
        logger.info("Database initialised: %s", settings.database_url)
    except Exception as exc:
        logger.warning(
            "Database connection failed (%s). "
            "API will start but DB endpoints will return errors. "
            "Start PostgreSQL or update DATABASE_URL.",
            exc,
        )

    # Create output directories
    for d in [settings.output_dir, settings.intermediate_dir, settings.archives_dir]:
        os.makedirs(d, exist_ok=True)

    logger.info("AIDEP ready. Visit http://localhost:8000/docs")
    yield

    logger.info("AIDEP shutting down.")


# ── FastAPI app factory ────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AIDEP — Autonomous Instruction Data Engineering Platform",
        description=(
            "A platform that autonomously transforms human seed knowledge into "
            "structured, validated, and reusable instruction datasets for LLM alignment.\n\n"
            "## Pipeline\n"
            "```\n"
            "Seed Tasks → Instruction Generation → Task Intelligence → "
            "Training Examples → Validation → Quality Scoring → dataset.jsonl\n"
            "```\n\n"
            "## Quick Start\n"
            "1. `POST /seed` — Upload seed tasks\n"
            "2. `POST /pipeline/run` — Run the full pipeline\n"
            "3. `POST /dataset/export` — Download dataset.jsonl\n"
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register routers ──────────────────────────────────────────────────────
    app.include_router(seed_router)
    app.include_router(instructions_router)
    app.include_router(examples_router)
    app.include_router(validation_router)
    app.include_router(quality_router)
    app.include_router(dataset_router)
    app.include_router(pipeline_router)

    # ── Root health check ─────────────────────────────────────────────────────
    @app.get("/", tags=["Health"], summary="Platform health check")
    def root():
        return {
            "platform": "AIDEP",
            "version": settings.app_version,
            "status": "operational",
            "llm_model": settings.llm_model,
            "docs": "/docs",
        }

    @app.get("/health", tags=["Health"], summary="Detailed health status")
    def health():
        from aidep.database.base import get_engine
        db_status = "unknown"
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:
            db_status = f"error: {exc}"

        return JSONResponse(
            content={
                "status": "ok",
                "database": db_status,
                "llm_model": settings.llm_model,
                "version": settings.app_version,
            }
        )

    return app


app = create_app()


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "aidep.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
