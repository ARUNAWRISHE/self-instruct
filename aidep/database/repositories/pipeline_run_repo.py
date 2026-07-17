"""Repository for pipeline_runs table. ISSUE-02."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.database.models import PipelineRunModel


class PipelineRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, version: str = "1.0.0") -> PipelineRunModel:
        """Create a new pipeline run record with status=running."""
        record = PipelineRunModel(version=version, status="running")
        self.session.add(record)
        self.session.flush()
        return record

    def complete(
        self,
        run_id: int,
        seed_count: int,
        instruction_count: int,
        accepted_count: int,
        rejected_count: int,
        dataset_path: str = "",
        error_log: Optional[List[str]] = None,
    ) -> Optional[PipelineRunModel]:
        """Mark a run as completed and record final statistics."""
        record = self.session.get(PipelineRunModel, run_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record.status = "completed"
        record.completed_at = now
        record.duration_seconds = (now - record.started_at).total_seconds()
        record.seed_count = seed_count
        record.instruction_count = instruction_count
        record.accepted_count = accepted_count
        record.rejected_count = rejected_count
        record.dataset_path = dataset_path
        record.error_log = error_log or []
        self.session.flush()
        return record

    def fail(self, run_id: int, error_log: Optional[List[str]] = None) -> Optional[PipelineRunModel]:
        """Mark a run as failed."""
        record = self.session.get(PipelineRunModel, run_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record.status = "failed"
        record.completed_at = now
        record.duration_seconds = (now - record.started_at).total_seconds()
        record.error_log = error_log or []
        self.session.flush()
        return record

    def get_all(self, limit: int = 50) -> List[PipelineRunModel]:
        """Return recent pipeline runs, newest first."""
        stmt = (
            select(PipelineRunModel)
            .order_by(PipelineRunModel.started_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_id(self, run_id: int) -> Optional[PipelineRunModel]:
        return self.session.get(PipelineRunModel, run_id)
