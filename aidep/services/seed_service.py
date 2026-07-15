"""
Services layer — business logic called by API routes.
Each service wraps one or more engines and a repository.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.models import SeedTask, TaskCategory
from aidep.database.repositories.seed_repo import SeedRepository
from aidep.engines.knowledge_engine.engine import KnowledgeEngine
from aidep.schemas.seed import (
    SeedTaskCreateRequest,
    SeedTaskListResponse,
    SeedTaskResponse,
)


class SeedService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = SeedRepository(session)
        self.engine = KnowledgeEngine(session=session)

    def create_seed(self, req: SeedTaskCreateRequest) -> SeedTaskResponse:
        task = SeedTask(
            id=str(uuid.uuid4()),
            instruction=req.instruction,
            input=req.input,
            output=req.output,
            domain=req.domain,
            category=req.category,
            difficulty=req.difficulty,
            source=req.source,
            metadata=req.metadata,
        )
        record = self.repo.create(task)
        return self._to_response(record)

    def create_bulk(self, requests: List[SeedTaskCreateRequest]) -> List[SeedTaskResponse]:
        responses = []
        for req in requests:
            responses.append(self.create_seed(req))
        return responses

    def list_seeds(self) -> SeedTaskListResponse:
        records = self.repo.get_all()
        seeds = [self._to_response(r) for r in records]
        return SeedTaskListResponse(total=len(seeds), seeds=seeds)

    def load_from_file(self, path: str) -> int:
        tasks = self.engine.load_seeds(path)
        return len(tasks)

    @staticmethod
    def _to_response(record) -> SeedTaskResponse:
        return SeedTaskResponse(
            id=record.id,
            task_key=record.task_key,
            instruction=record.instruction,
            input=record.input or "",
            output=record.output or "",
            domain=record.domain,
            category=record.category,
            difficulty=record.difficulty,
            source=record.source,
            created_at=record.created_at.isoformat(),
        )
