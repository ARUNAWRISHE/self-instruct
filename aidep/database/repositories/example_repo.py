"""Repository for training_examples, validation_results, and quality_scores tables."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.models import QualityMetrics, TrainingExample, ValidationResult
from aidep.database.models import (
    QualityScoreModel,
    TrainingExampleModel,
    ValidationResultModel,
)


class ExampleRepository:
    def __init__(self, session: Session):
        self.session = session

    # ── Training Examples ─────────────────────────────────────────────────────

    def create_example(
        self, example: TrainingExample, instruction_db_id: Optional[int] = None
    ) -> TrainingExampleModel:
        record = TrainingExampleModel(
            instruction_id=instruction_db_id,
            instruction_text=example.instruction,
            input=example.input or "",
            output=example.output,
            context=example.context,
            constraints_json=example.constraints or [],
            status=example.status,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_example(self, example_id: int) -> Optional[TrainingExampleModel]:
        return self.session.get(TrainingExampleModel, example_id)

    def get_all_examples(self, status: Optional[str] = None) -> List[TrainingExampleModel]:
        q = self.session.query(TrainingExampleModel)
        if status:
            q = q.filter(TrainingExampleModel.status == status)
        return q.order_by(TrainingExampleModel.id).all()

    def update_example_status(self, example_id: int, status: str) -> None:
        record = self.session.get(TrainingExampleModel, example_id)
        if record:
            record.status = status
            self.session.flush()

    # ── Validation Results ─────────────────────────────────────────────────────

    def save_validation(
        self, example_db_id: int, result: ValidationResult
    ) -> ValidationResultModel:
        existing = (
            self.session.query(ValidationResultModel)
            .filter(ValidationResultModel.example_id == example_db_id)
            .first()
        )
        if existing:
            existing.is_valid = result.is_valid
            existing.reasons_json = result.reasons
            existing.duplicates_json = result.duplicates
            self.session.flush()
            return existing

        record = ValidationResultModel(
            example_id=example_db_id,
            is_valid=result.is_valid,
            reasons_json=result.reasons,
            duplicates_json=result.duplicates,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_validation(self, example_db_id: int) -> Optional[ValidationResultModel]:
        return (
            self.session.query(ValidationResultModel)
            .filter(ValidationResultModel.example_id == example_db_id)
            .first()
        )

    # ── Quality Scores ─────────────────────────────────────────────────────────

    def save_quality(
        self, example_db_id: int, metrics: QualityMetrics
    ) -> QualityScoreModel:
        existing = (
            self.session.query(QualityScoreModel)
            .filter(QualityScoreModel.example_id == example_db_id)
            .first()
        )
        if existing:
            for field in [
                "semantic_score", "factual_score", "reasoning_score",
                "diversity_score", "consistency_score", "confidence_score",
                "toxicity_score", "hallucination_score", "overall_score",
            ]:
                setattr(existing, field, getattr(metrics, field))
            existing.approval_status = metrics.approval_status.value
            self.session.flush()
            return existing

        record = QualityScoreModel(
            example_id=example_db_id,
            semantic_score=metrics.semantic_score,
            factual_score=metrics.factual_score,
            reasoning_score=metrics.reasoning_score,
            diversity_score=metrics.diversity_score,
            consistency_score=metrics.consistency_score,
            confidence_score=metrics.confidence_score,
            toxicity_score=metrics.toxicity_score,
            hallucination_score=metrics.hallucination_score,
            overall_score=metrics.overall_score,
            approval_status=metrics.approval_status.value,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_quality(self, example_db_id: int) -> Optional[QualityScoreModel]:
        return (
            self.session.query(QualityScoreModel)
            .filter(QualityScoreModel.example_id == example_db_id)
            .first()
        )
