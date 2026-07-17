"""
Intelligence Engine — Phase 3

Analyzes each generated instruction to produce structured task metadata.
ISSUE-03: Prompt loaded from PromptLibraryService, not hardcoded.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseIntelligenceEngine
from aidep.core.llm import LLMClient
from aidep.core.models import (
    DifficultyLevel,
    GeneratedInstruction,
    InstructionMetadata,
    ReasoningLevel,
    TaskCategory,
)
from aidep.database.repositories.instruction_repo import InstructionRepository
from aidep.services.prompt_service import PromptLibraryService

logger = logging.getLogger(__name__)


class IntelligenceEngine(BaseIntelligenceEngine):
    """
    Classifies each instruction into a rich metadata structure using LLM analysis.
    ISSUE-03: Uses PromptLibraryService for all prompt text.
    Persists metadata to DB if a session is available.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
    ):
        self.llm = llm_client
        self.session = session
        self.prompt_library = PromptLibraryService(session=session)

    def analyze(
        self, instruction: GeneratedInstruction
    ) -> InstructionMetadata:
        """Classify the instruction and return structured InstructionMetadata."""
        template = self.prompt_library.get_prompt("task_intelligence")
        prompt = template.format(instruction=instruction.instruction)

        response = self.llm.generate(
            prompt, system_prompt="You are a precise semantic analyzer for AI tasks."
        )

        metadata = self._parse_response(response, instruction)

        # Persist to DB
        if self.session and instruction.id is not None:
            repo = InstructionRepository(self.session)
            repo.save_metadata(instruction.id, metadata)
            repo.update_instruction_status(instruction.id, "analyzed")

        logger.debug(
            "IntelligenceEngine: analyzed instruction (category=%s, difficulty=%s, complexity=%.2f)",
            metadata.category.value,
            metadata.difficulty.value,
            metadata.complexity,
        )
        return metadata

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_response(
        self, response: str, instruction: GeneratedInstruction
    ) -> InstructionMetadata:
        task_type = "Generation"
        category = TaskCategory.OTHER
        domain = instruction.domain or "General"
        subdomain = "General"
        difficulty = DifficultyLevel.MEDIUM
        reasoning_level = ReasoningLevel.MEDIUM
        expected_output_type = "Text"
        complexity = 0.3

        for line in response.split("\n"):
            line_str = line.strip()
            if not line_str or ":" not in line_str:
                continue
            key, _, val = line_str.partition(":")
            key = key.strip().lower()
            val = val.strip()

            if key == "task type":
                task_type = val
            elif key == "category":
                for cat in TaskCategory:
                    if cat.value in val.lower():
                        category = cat
                        break
            elif key == "domain":
                domain = val
            elif key == "subdomain":
                subdomain = val
            elif key == "difficulty":
                difficulty = self._parse_difficulty(val)
            elif key in ("reasoning level", "reasoning"):
                reasoning_level = self._parse_reasoning(val)
            elif key == "expected output type":
                expected_output_type = val
            elif key == "complexity":
                try:
                    match = re.search(r"\d+\.?\d*", val)
                    if match:
                        complexity = float(match.group())
                        complexity = max(0.0, min(1.0, complexity))
                except ValueError:
                    pass

        # Sensible defaults for category-output pairs
        if category == TaskCategory.CODING and expected_output_type == "Text":
            expected_output_type = "Code"
        if category == TaskCategory.CLASSIFICATION and expected_output_type == "Text":
            expected_output_type = "Label"

        return InstructionMetadata(
            instruction_id=instruction.id,
            task_type=task_type,
            category=category,
            domain=domain,
            subdomain=subdomain,
            difficulty=difficulty,
            reasoning_level=reasoning_level,
            expected_output_type=expected_output_type,
            complexity=complexity,
        )

    @staticmethod
    def _parse_difficulty(val: str) -> DifficultyLevel:
        normalized = val.strip().capitalize()
        mapping = {
            "Easy": DifficultyLevel.EASY,
            "Medium": DifficultyLevel.MEDIUM,
            "Hard": DifficultyLevel.HARD,
            "Expert": DifficultyLevel.EXPERT,
        }
        if normalized in mapping:
            return mapping[normalized]
        try:
            match = re.search(r"\d+", val)
            if match:
                n = int(match.group())
                if n <= 3:
                    return DifficultyLevel.EASY
                if n <= 6:
                    return DifficultyLevel.MEDIUM
                if n <= 8:
                    return DifficultyLevel.HARD
                return DifficultyLevel.EXPERT
        except ValueError:
            pass
        return DifficultyLevel.MEDIUM

    @staticmethod
    def _parse_reasoning(val: str) -> ReasoningLevel:
        normalized = val.strip().capitalize()
        mapping = {
            "Low": ReasoningLevel.LOW,
            "Medium": ReasoningLevel.MEDIUM,
            "High": ReasoningLevel.HIGH,
            "Expert": ReasoningLevel.EXPERT,
        }
        return mapping.get(normalized, ReasoningLevel.MEDIUM)
