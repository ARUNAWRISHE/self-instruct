"""Repository for the datasets table."""

from __future__ import annotations

from typing import List, Optional

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
        return (
            self.session.query(DatasetModel)
            .order_by(DatasetModel.created_at.desc())
            .all()
        )

    def get_latest(self) -> Optional[DatasetModel]:
        return (
            self.session.query(DatasetModel)
            .order_by(DatasetModel.created_at.desc())
            .first()
        )

    def get_by_id(self, dataset_id: int) -> Optional[DatasetModel]:
        return self.session.get(DatasetModel, dataset_id)
