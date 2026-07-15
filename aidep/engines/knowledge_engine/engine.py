"""
Knowledge Engine — Phase 1

Manages the Knowledge Foundation:
  - Seed Repository
  - Prompt Library
  - Domain Library
  - Constraint Library
  - Taxonomy

Migrated from: next_gen_self_instruct/engines/seed_knowledge.py
Extended with: DB persistence via SeedRepository
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseKnowledgeEngine
from aidep.core.models import SeedTask, TaskCategory
from aidep.database.repositories.seed_repo import SeedRepository

logger = logging.getLogger(__name__)


class KnowledgeEngine(BaseKnowledgeEngine):
    """
    Loads seed tasks from JSONL files and/or the database.
    Stores all seeds in PostgreSQL via SeedRepository.
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self._in_memory_seeds: List[SeedTask] = []

    # ── Public interface ──────────────────────────────────────────────────────

    def load_seeds(self, path: str) -> List[SeedTask]:
        """
        Parse a JSONL seed file, persist each task to the DB,
        and return the list of SeedTask objects.
        """
        tasks = self._parse_jsonl(path)
        if self.session:
            repo = SeedRepository(self.session)
            for task in tasks:
                repo.create(task)
        else:
            self._in_memory_seeds.extend(tasks)

        logger.info("KnowledgeEngine: loaded %d seed tasks from %s", len(tasks), path)
        return tasks

    def get_all_seeds(self) -> List[SeedTask]:
        """Return all seeds from DB (or in-memory cache if no DB)."""
        if self.session:
            repo = SeedRepository(self.session)
            records = repo.get_all()
            return [self._orm_to_model(r) for r in records]
        return list(self._in_memory_seeds)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_jsonl(self, path: str) -> List[SeedTask]:
        """Parse a JSONL file and return a list of SeedTask objects.

        Handles multiple formats:
          - Original SELF-INSTRUCT format (with "instances" key)
          - AIDEP format (flat: instruction, input, output, domain, category)
          - Legacy next_gen_self_instruct format
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Seed file not found: {path}")

        tasks: List[SeedTask] = []
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSON on line %d", line_num)
                    continue

                task = self._parse_record(data, line_num)
                if task:
                    tasks.append(task)

        return tasks

    def _parse_record(self, data: dict, idx: int) -> Optional[SeedTask]:
        """Convert a raw JSONL dict into a SeedTask."""
        instruction = (
            data.get("instruction", "")
            or data.get("prompt", "")
            or ""
        ).strip()
        if not instruction:
            return None

        task_id = data.get("id") or data.get("task_id") or f"seed_{idx}"

        # Extract input/output — check nested "instances" first (SELF-INSTRUCT format)
        instances = data.get("instances", [])
        if instances and isinstance(instances, list) and len(instances) > 0:
            seed_input = instances[0].get("input", "").strip()
            seed_output = instances[0].get("output", "").strip()
        else:
            seed_input = (
                data.get("input", "")
                or data.get("metadata", {}).get("input", "")
                or ""
            )
            seed_output = (
                data.get("output", "")
                or data.get("metadata", {}).get("output", "")
                or ""
            )

        category_str = (
            data.get("category", "")
            or data.get("metadata", {}).get("category", "")
            or "other"
        ).lower()

        category = TaskCategory.OTHER
        for cat in TaskCategory:
            if cat.value == category_str:
                category = cat
                break

        domain = (
            data.get("domain")
            or data.get("metadata", {}).get("domain")
            or "General"
        )
        difficulty = int(
            data.get("difficulty")
            or data.get("metadata", {}).get("difficulty")
            or 3
        )

        return SeedTask(
            id=str(task_id),
            instruction=instruction,
            input=seed_input,
            output=seed_output,
            domain=str(domain),
            category=category,
            difficulty=difficulty,
            source="human",
            metadata={"original": data},
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _orm_to_model(record) -> SeedTask:
        return SeedTask(
            id=record.task_key,
            instruction=record.instruction,
            input=record.input or "",
            output=record.output or "",
            domain=record.domain,
            category=TaskCategory(record.category),
            difficulty=record.difficulty,
            source=record.source,
            metadata=record.extra_metadata or {},
        )

    def add_seed(self, seed: SeedTask) -> SeedTask:
        """Add a single seed task (from API call)."""
        if self.session:
            repo = SeedRepository(self.session)
            repo.create(seed)
        else:
            self._in_memory_seeds.append(seed)
        return seed
