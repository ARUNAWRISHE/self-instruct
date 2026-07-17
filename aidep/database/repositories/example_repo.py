"""Backward-compatible ExampleRepository facade.
ISSUE-07: The original monolithic repository is preserved as a thin facade
that delegates to the three focused repositories, so existing callers in
pipeline_services.py and engines continue to work without modification.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.models import QualityMetrics, TrainingExample, ValidationResult
from aidep.database.models import (
    QualityScoreModel,
    TrainingExampleModel,
    ValidationResultModel,
)
from aidep.database.repositories.quality_repo import QualityRepository
from aidep.database.repositories.training_example_repo import TrainingExampleRepository
from aidep.database.repositories.validation_repo import ValidationRepository


class ExampleRepository:
    """
    Facade that delegates to the three focused repositories.
    Keeps all existing call sites working with zero changes.
    """

    def __init__(self, session: Session):
        self.session = session
        self._example_repo = TrainingExampleRepository(session)
        self._validation_repo = ValidationRepository(session)
        self._quality_repo = QualityRepository(session)

    # ── Training Examples ─────────────────────────────────────────────────────

    def create_example(
        self, example: TrainingExample, instruction_db_id: Optional[int] = None
    ) -> TrainingExampleModel:
        return self._example_repo.create_example(example, instruction_db_id)

    def get_example(self, example_id: int) -> Optional[TrainingExampleModel]:
        return self._example_repo.get_example(example_id)

    def get_all_examples(self, status: Optional[str] = None) -> List[TrainingExampleModel]:
        return self._example_repo.get_all_examples(status)

    def update_example_status(self, example_id: int, status: str) -> None:
        return self._example_repo.update_example_status(example_id, status)

    # ── Validation Results ─────────────────────────────────────────────────────

    def save_validation(
        self, example_db_id: int, result: ValidationResult
    ) -> ValidationResultModel:
        return self._validation_repo.save_validation(example_db_id, result)

    def get_validation(self, example_db_id: int) -> Optional[ValidationResultModel]:
        return self._validation_repo.get_validation(example_db_id)

    # ── Quality Scores ─────────────────────────────────────────────────────────

    def save_quality(
        self, example_db_id: int, metrics: QualityMetrics
    ) -> QualityScoreModel:
        return self._quality_repo.save_quality(example_db_id, metrics)

    def get_quality(self, example_db_id: int) -> Optional[QualityScoreModel]:
        return self._quality_repo.get_quality(example_db_id)
