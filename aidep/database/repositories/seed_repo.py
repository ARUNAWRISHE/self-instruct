"""Repository for seed_tasks table operations."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.models import SeedTask
from aidep.database.models import SeedTaskModel


class SeedRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, seed: SeedTask) -> SeedTaskModel:
        """Persist a SeedTask. Skips duplicates (by task_key)."""
        existing = (
            self.session.query(SeedTaskModel)
            .filter(SeedTaskModel.task_key == seed.id)
            .first()
        )
        if existing:
            return existing

        record = SeedTaskModel(
            task_key=seed.id,
            instruction=seed.instruction,
            input=seed.input or "",
            output=seed.output or "",
            domain=seed.domain,
            category=seed.category.value,
            difficulty=seed.difficulty,
            source=seed.source,
            extra_metadata=seed.metadata,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_all(self) -> List[SeedTaskModel]:
        return self.session.query(SeedTaskModel).order_by(SeedTaskModel.id).all()

    def get_by_id(self, seed_id: int) -> Optional[SeedTaskModel]:
        return self.session.get(SeedTaskModel, seed_id)

    def get_by_key(self, task_key: str) -> Optional[SeedTaskModel]:
        return (
            self.session.query(SeedTaskModel)
            .filter(SeedTaskModel.task_key == task_key)
            .first()
        )

    def count(self) -> int:
        return self.session.query(SeedTaskModel).count()
