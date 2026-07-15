"""
FastAPI dependency injection.
Provides shared session, LLM client, and service instances to route handlers.
"""

from __future__ import annotations

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from aidep.core.config import Settings, get_settings
from aidep.core.llm import LLMClient
from aidep.database.base import get_session


# ── Core dependencies ─────────────────────────────────────────────────────────

def get_db(settings: Settings = Depends(get_settings)) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session per request."""
    yield from get_session()


def get_llm(settings: Settings = Depends(get_settings)) -> LLMClient:
    """Return a cached LLMClient instance."""
    return LLMClient.from_settings(settings)


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
