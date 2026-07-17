"""
PromptLibraryService — ISSUE-03

Central store for all LLM prompt templates.
Engines call get_prompt(prompt_type) instead of holding hardcoded strings.
This enables hot-swap and A/B testing without code changes.

Prompt types used:
  - "instruction_generation"
  - "domain_instruction_generation"
  - "task_intelligence"
  - "example_generation"
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from aidep.database.models import PromptTemplateModel

logger = logging.getLogger(__name__)

# ── Default prompt library (written to DB on first use) ───────────────────────

_DEFAULT_PROMPTS: dict[str, dict] = {
    "instruction_generation": {
        "prompt_type": "instruction_generation",
        "template_text": (
            "Create 5 unique, diverse, and well-crafted instructions for an AI assistant. "
            "Instructions should target '{difficulty}' difficulty level. "
            "Vary the domains (coding, writing, math, science, law, business, healthcare, etc.) "
            "and the format types (step-by-step, question answering, summarization, coding task, etc.).\n\n"
            "Reference examples:\n{few_shot}\n\n"
            "Format your response as a numbered list:\n"
            "1. [First Instruction]\n"
            "2. [Second Instruction]\n"
            "3. [Third Instruction]\n"
            "4. [Fourth Instruction]\n"
            "5. [Fifth Instruction]"
        ),
        "version": "1.0",
    },
    "domain_instruction_generation": {
        "prompt_type": "domain_instruction_generation",
        "template_text": (
            "Generate {count} diverse, well-crafted instructions for an AI assistant "
            "specifically in the domain of '{domain}'. "
            "Vary difficulty and task types (analysis, writing, computation, QA, planning, etc.).\n\n"
            "{seed_example}"
            "Return as a numbered list."
        ),
        "version": "1.0",
    },
    "task_intelligence": {
        "prompt_type": "task_intelligence",
        "template_text": (
            "Analyze the following AI task instruction:\n"
            "Instruction: {instruction}\n\n"
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
        ),
        "version": "1.0",
    },
    "example_generation": {
        "prompt_type": "example_generation",
        "template_text": (
            "Generate a realistic input (if needed) and a correct, high-quality output "
            "for the following AI task instruction:\n\n"
            "Instruction: {instruction}\n"
            "Task Type: {task_type}\n"
            "Domain: {domain}\n"
            "Difficulty: {difficulty}\n"
            "Expected Output Type: {expected_output_type}\n\n"
            "Rules:\n"
            "- If the instruction is self-contained (e.g. 'Write a story'), set Input to None.\n"
            "- The output must be complete, accurate, and well-formatted.\n"
            "- List any explicit constraints (format, tone, length, etc.) as a comma-separated list, or None.\n\n"
            "Respond EXACTLY in this format:\n"
            "Constraints: [comma-separated list or None]\n"
            "Input: [the input, or None]\n"
            "Output: [the complete, correct response]"
        ),
        "version": "1.0",
    },
}


class PromptLibraryService:
    """
    Retrieves prompt templates by type.

    Strategy:
      1. Check DB for the prompt (allows runtime hot-swap).
      2. Fall back to in-memory defaults if DB is unavailable or template not found.
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session

    def get_prompt(self, prompt_type: str) -> str:
        """Return the template text for the given prompt type."""
        if self.session:
            try:
                from sqlalchemy import select  # noqa: PLC0415
                stmt = select(PromptTemplateModel).where(
                    PromptTemplateModel.prompt_type == prompt_type
                )
                record = self.session.execute(stmt).scalar_one_or_none()
                if record:
                    return record.template_text
            except Exception as exc:
                logger.warning("PromptLibrary: DB lookup failed (%s). Using default.", exc)

        # Fallback to in-memory defaults
        default = _DEFAULT_PROMPTS.get(prompt_type)
        if default:
            return default["template_text"]

        raise ValueError(f"PromptLibraryService: unknown prompt type '{prompt_type}'")

    def seed_db_from_defaults(self) -> int:
        """
        Populate prompt_templates table with defaults if not already present.
        Returns number of records inserted.
        Call this once at application startup.
        """
        if not self.session:
            return 0

        inserted = 0
        for name, data in _DEFAULT_PROMPTS.items():
            from sqlalchemy import select  # noqa: PLC0415
            stmt = select(PromptTemplateModel).where(
                PromptTemplateModel.name == name
            )
            existing = self.session.execute(stmt).scalar_one_or_none()
            if not existing:
                record = PromptTemplateModel(
                    name=name,
                    prompt_type=data["prompt_type"],
                    template_text=data["template_text"],
                    version=data["version"],
                )
                self.session.add(record)
                inserted += 1

        if inserted:
            self.session.flush()
            logger.info("PromptLibrary: seeded %d default prompt templates.", inserted)

        return inserted
