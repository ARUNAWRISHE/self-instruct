"""Repository for the datasets table.
ISSUE-06: Migrated to SQLAlchemy 2.0 select() style.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.database.models import DatasetModel


class DatasetRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        version: str,
        export_path: str,
        total_examples: int,
        approved_count: int,
        rejected_count: int,
        quality_report: Optional[dict] = None,
    ) -> DatasetModel:
        record = DatasetModel(
            name=name,
            version=version,
            export_path=export_path,
            total_examples=total_examples,
            approved_count=approved_count,
            rejected_count=rejected_count,
            quality_report_json=quality_report or {},
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_all(self) -> List[DatasetModel]:
        stmt = (
            select(DatasetModel)
            .order_by(DatasetModel.created_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_latest(self) -> Optional[DatasetModel]:
        stmt = (
            select(DatasetModel)
            .order_by(DatasetModel.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_id(self, dataset_id: int) -> Optional[DatasetModel]:
        return self.session.get(DatasetModel, dataset_id)
