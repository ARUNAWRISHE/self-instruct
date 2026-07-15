"""
Intelligence Engine — Phase 3

Analyzes each generated instruction to produce structured task metadata:
  - Task Type
  - Domain / Subdomain
  - Difficulty
  - Reasoning Level
  - Expected Output Format
  - Complexity Score

Migrated from: next_gen_self_instruct/engines/task_intelligence.py
Extended with: DB persistence via InstructionRepository
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

logger = logging.getLogger(__name__)


class IntelligenceEngine(BaseIntelligenceEngine):
    """
    Classifies each instruction into a rich metadata structure using LLM analysis.
    Persists metadata to DB if a session is available.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
    ):
        self.llm = llm_client
        self.session = session

    def analyze(
        self, instruction: GeneratedInstruction
    ) -> InstructionMetadata:
        """Classify the instruction and return structured InstructionMetadata."""
        prompt = (
            f"Analyze the following AI task instruction:\n"
            f"Instruction: {instruction.instruction}\n\n"
            "Identify these attributes:\n"
            "1. Task Type: one of — Generation, Classification, Summarization, "
            "Translation, Question Answering, Information Extraction, Reasoning, "
            "Coding, Planning, Dialogue.\n"
            "2. Category: one of — coding, classification, reasoning, translation, "
            "summarization, generation, planning, dialogue, other.\n"
            "3. Domain: specific area of knowledge (e.g. Science, Mathematics, Law, "
            "Software Engineering, Healthcare, Finance, Literature, General).\n"
            "4. Subdomain: a sub-category of the domain.\n"
            "5. Difficulty: one of — Easy, Medium, Hard, Expert.\n"
            "6. Reasoning Level: one of — Low, Medium, High, Expert.\n"
            "7. Expected Output Type: format of the response (e.g. Code, JSON, "
            "Markdown, Text, Table, Boolean, Label, Number).\n"
            "8. Complexity: a float from 0.0 to 1.0 estimating structural complexity.\n\n"
            "Respond EXACTLY in this format (one attribute per line):\n"
            "Task Type: [value]\n"
            "Category: [value]\n"
            "Domain: [value]\n"
            "Subdomain: [value]\n"
            "Difficulty: [value]\n"
            "Reasoning Level: [value]\n"
            "Expected Output Type: [value]\n"
            "Complexity: [value]"
        )

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
        # Try numeric fallback (from legacy data)
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
