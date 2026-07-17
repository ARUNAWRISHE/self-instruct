"""Repository for quality_scores table.
ISSUE-07: Split from monolithic ExampleRepository into focused repos.
ISSUE-06: Migrated to SQLAlchemy 2.0 select() style.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.core.models import QualityMetrics
from aidep.database.models import QualityScoreModel


class QualityRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_quality(
        self, example_db_id: int, metrics: QualityMetrics
    ) -> QualityScoreModel:
        stmt = select(QualityScoreModel).where(
            QualityScoreModel.example_id == example_db_id
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
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
        stmt = select(QualityScoreModel).where(
            QualityScoreModel.example_id == example_db_id
        )
        return self.session.execute(stmt).scalar_one_or_none()
