"""Repository for validation_results table.
ISSUE-07: Split from monolithic ExampleRepository into focused repos.
ISSUE-06: Migrated to SQLAlchemy 2.0 select() style.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.core.models import ValidationResult
from aidep.database.models import ValidationResultModel


class ValidationRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_validation(
        self, example_db_id: int, result: ValidationResult
    ) -> ValidationResultModel:
        stmt = select(ValidationResultModel).where(
            ValidationResultModel.example_id == example_db_id
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
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
        stmt = select(ValidationResultModel).where(
            ValidationResultModel.example_id == example_db_id
        )
        return self.session.execute(stmt).scalar_one_or_none()
