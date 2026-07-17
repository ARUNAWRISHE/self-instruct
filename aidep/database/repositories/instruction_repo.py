"""Repository for generated_instructions and instruction_metadata tables.
ISSUE-06: Migrated to SQLAlchemy 2.0 select() style.
ISSUE-17: create_instruction() returns the ORM record with its DB id directly,
          eliminating the fragile tail-slice pattern in InstructionService.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidep.core.models import GeneratedInstruction, InstructionMetadata
from aidep.database.models import GeneratedInstructionModel, InstructionMetadataModel


class InstructionRepository:
    def __init__(self, session: Session):
        self.session = session

    # ── Instructions ──────────────────────────────────────────────────────────

    def create_instruction(
        self, instruction: GeneratedInstruction, seed_db_id: Optional[int] = None
    ) -> GeneratedInstructionModel:
        """ISSUE-17: Returns the ORM record with populated id immediately after flush."""
        record = GeneratedInstructionModel(
            instruction=instruction.instruction,
            seed_id=seed_db_id,
            domain=instruction.domain,
            difficulty=instruction.difficulty,
            status=instruction.status,
            extra_metadata=instruction.metadata,
        )
        self.session.add(record)
        self.session.flush()  # record.id is populated after flush
        return record

    def get_instruction(self, instruction_id: int) -> Optional[GeneratedInstructionModel]:
        return self.session.get(GeneratedInstructionModel, instruction_id)

    def get_all_instructions(self, status: Optional[str] = None) -> List[GeneratedInstructionModel]:
        stmt = select(GeneratedInstructionModel)
        if status:
            stmt = stmt.where(GeneratedInstructionModel.status == status)
        stmt = stmt.order_by(GeneratedInstructionModel.id)
        return list(self.session.execute(stmt).scalars().all())

    def update_instruction_status(self, instruction_id: int, status: str) -> None:
        record = self.session.get(GeneratedInstructionModel, instruction_id)
        if record:
            record.status = status
            self.session.flush()

    # ── Metadata ──────────────────────────────────────────────────────────────

    def save_metadata(
        self, instruction_db_id: int, meta: InstructionMetadata
    ) -> InstructionMetadataModel:
        stmt = select(InstructionMetadataModel).where(
            InstructionMetadataModel.instruction_id == instruction_db_id
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            existing.task_type = meta.task_type
            existing.category = meta.category.value
            existing.domain = meta.domain
            existing.subdomain = meta.subdomain
            existing.difficulty = meta.difficulty.value
            existing.reasoning_level = meta.reasoning_level.value
            existing.expected_output_type = meta.expected_output_type
            existing.complexity = meta.complexity
            self.session.flush()
            return existing

        record = InstructionMetadataModel(
            instruction_id=instruction_db_id,
            task_type=meta.task_type,
            category=meta.category.value,
            domain=meta.domain,
            subdomain=meta.subdomain,
            difficulty=meta.difficulty.value,
            reasoning_level=meta.reasoning_level.value,
            expected_output_type=meta.expected_output_type,
            complexity=meta.complexity,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_metadata(self, instruction_db_id: int) -> Optional[InstructionMetadataModel]:
        stmt = select(InstructionMetadataModel).where(
            InstructionMetadataModel.instruction_id == instruction_db_id
        )
        return self.session.execute(stmt).scalar_one_or_none()
