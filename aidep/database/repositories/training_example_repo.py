"""Repository for training_examples table.
ISSUE-07: Split from monolithic ExampleRepository into focused repos.
ISSUE-06: Migrated to SQLAlchemy 2.0 select() style.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.core.models import TrainingExample
from aidep.database.models import TrainingExampleModel


class TrainingExampleRepository:
    def __init__(self, session: Session):
        self.session = session

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
        stmt = select(TrainingExampleModel)
        if status:
            stmt = stmt.where(TrainingExampleModel.status == status)
        stmt = stmt.order_by(TrainingExampleModel.id)
        return list(self.session.execute(stmt).scalars().all())

    def update_example_status(self, example_id: int, status: str) -> None:
        record = self.session.get(TrainingExampleModel, example_id)
        if record:
            record.status = status
            self.session.flush()
