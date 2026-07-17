"""
FastAPI dependency injection.
Provides shared session, LLM client, and service instances to route handlers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from aidep.core.config import Settings, get_settings
from aidep.core.llm import LLMClient
from aidep.database.base import get_session


# ── Core dependencies ─────────────────────────────────────────────────────────

def get_db(settings: Settings = Depends(get_settings)) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session per request."""
    yield from get_session()


@lru_cache(maxsize=1)
def _get_llm_singleton(model: str, temperature: float, max_tokens: int, timeout: int) -> LLMClient:
    """ISSUE-08: Module-level LLMClient singleton — created once per process."""
    from aidep.core.config import get_settings as _gs
    s = _gs()
    return LLMClient.from_settings(s)


def get_llm(settings: Settings = Depends(get_settings)) -> LLMClient:
    """Return the cached singleton LLMClient."""
    return _get_llm_singleton(
        settings.llm_model,
        settings.llm_temperature,
        settings.llm_max_tokens,
        settings.llm_timeout,
    )


# ── ISSUE-13: Optional API key authentication ──────────────────────────────────

def get_api_key(
    settings: Settings = Depends(get_settings),
    x_api_key: Optional[str] = Header(default=None),
) -> None:
    """
    If api_key is set in config, require it via X-Api-Key header.
    If api_key is blank/unset, auth is disabled (PoC default).
    """
    configured_key = getattr(settings, "api_key", None)
    if configured_key:  # Only enforce if key is configured
        if x_api_key != configured_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Api-Key header.",
            )


# ── Service dependencies ───────────────────────────────────────────────────────

def get_seed_service(
    session: Session = Depends(get_db),
):
    from aidep.services.seed_service import SeedService
    return SeedService(session)


def get_instruction_service(
    session: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    from aidep.services.pipeline_services import InstructionService
    return InstructionService(session, llm)


def get_example_service(
    session: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    from aidep.services.pipeline_services import ExampleService
    return ExampleService(session, llm)


def get_validation_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from aidep.services.pipeline_services import ValidationService
    return ValidationService(session, similarity_threshold=settings.validation_similarity_threshold)


def get_quality_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from aidep.services.pipeline_services import QualityService
    return QualityService(session, quality_threshold=settings.quality_threshold)


def get_dataset_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from aidep.services.pipeline_services import DatasetService
    return DatasetService(session, output_dir=settings.output_dir)


def get_pipeline_service(
    session: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
    settings: Settings = Depends(get_settings),
):
    """ISSUE-15: Provides PipelineService so the route does not wire the orchestrator."""
    from aidep.services.pipeline_service import PipelineService
    return PipelineService(session=session, llm_client=llm, settings=settings)
