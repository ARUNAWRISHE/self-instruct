"""
Instruction Engine — Phase 2

Generates diverse instruction candidates from seed tasks.

Migrated from: next_gen_self_instruct/engines/instruction_gen.py
Extended with:
  - Domain expansion (generates instructions per domain)
  - Difficulty expansion (Easy / Medium / Hard / Expert variants)
  - Variation generation
  - DB persistence via InstructionRepository
"""

from __future__ import annotations

import logging
import random
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseInstructionEngine
from aidep.core.llm import LLMClient
from aidep.core.models import GeneratedInstruction, SeedTask
from aidep.database.repositories.instruction_repo import InstructionRepository
from aidep.database.repositories.seed_repo import SeedRepository

logger = logging.getLogger(__name__)

_DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard", "Expert"]


class InstructionEngine(BaseInstructionEngine):
    """
    Generates new instruction candidates by combining seed examples with
    domain and difficulty expansion prompts.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
    ):
        self.llm = llm_client
        self.session = session

    def generate(
        self,
        seeds: List[SeedTask],
        count: int,
    ) -> List[GeneratedInstruction]:
        """
        Generate `count` instruction candidates inspired by the seed pool.
        Persists each to DB if a session is available.
        """
        if not seeds:
            logger.warning("InstructionEngine: seed pool is empty.")
            return []

        generated: List[GeneratedInstruction] = []
        requests_needed = max(1, (count + 4) // 5)

        for req_idx in range(requests_needed):
            if len(generated) >= count:
                break

            # Pick 3 random seeds as few-shot examples
            samples = random.sample(seeds, min(len(seeds), 3))
            few_shot = "\n\n".join(
                f"Example {i+1}:\nInstruction: {s.instruction}"
                for i, s in enumerate(samples)
            )

            # Pick a random difficulty to promote variation
            difficulty = random.choice(_DIFFICULTY_LEVELS)

            prompt = (
                "Create 5 unique, diverse, and well-crafted instructions for an AI assistant. "
                f"Instructions should target '{difficulty}' difficulty level. "
                "Vary the domains (coding, writing, math, science, law, business, healthcare, etc.) "
                "and the format types (step-by-step, question answering, summarization, coding task, etc.).\n\n"
                f"Reference examples:\n{few_shot}\n\n"
                "Format your response as a numbered list:\n"
                "1. [First Instruction]\n"
                "2. [Second Instruction]\n"
                "3. [Third Instruction]\n"
                "4. [Fourth Instruction]\n"
                "5. [Fifth Instruction]"
            )

            response = self.llm.generate(
                prompt,
                system_prompt="You are a high-quality instruction data generation engine.",
            )

            batch = self._parse_instructions(response, difficulty, req_idx)
            generated.extend(batch)
            logger.debug(
                "InstructionEngine: batch %d → %d instructions", req_idx, len(batch)
            )

        result = generated[:count]

        # Persist to DB
        if self.session:
            repo = InstructionRepository(self.session)
            seed_repo = SeedRepository(self.session)
            for inst in result:
                seed_db_id = None
                if inst.seed_id:
                    seed_record = seed_repo.get_by_key(inst.seed_id)
                    if seed_record:
                        seed_db_id = seed_record.id
                repo.create_instruction(inst, seed_db_id=seed_db_id)

        logger.info(
            "InstructionEngine: generated %d instruction candidates.", len(result)
        )
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_instructions(
        self, response: str, difficulty: str, batch_idx: int
    ) -> List[GeneratedInstruction]:
        """Parse numbered list response into GeneratedInstruction objects."""
        instructions: List[GeneratedInstruction] = []
        for line in response.split("\n"):
            text = line.strip()
            if not text:
                continue

            # Parse "1. Instruction text" or "- Instruction text"
            instruction_text = ""
            if text and text[0].isdigit() and "." in text[:4]:
                parts = text.split(".", 1)
                if len(parts) > 1:
                    instruction_text = parts[1].strip()
            elif text.startswith("- "):
                instruction_text = text[2:].strip()

            if instruction_text and len(instruction_text) > 15:
                instructions.append(
                    GeneratedInstruction(
                        instruction=instruction_text,
                        difficulty=difficulty,
                        status="pending",
                        metadata={"batch_idx": batch_idx},
                    )
                )

        return instructions

    def generate_domain_expanded(
        self,
        seeds: List[SeedTask],
        domains: List[str],
        per_domain: int = 5,
    ) -> List[GeneratedInstruction]:
        """
        Generate instructions explicitly per domain for balanced coverage.
        """
        all_instructions: List[GeneratedInstruction] = []
        for domain in domains:
            sample_seed = random.choice(seeds) if seeds else None
            prompt = (
                f"Generate {per_domain} diverse, well-crafted instructions for an AI assistant "
                f"specifically in the domain of '{domain}'. "
                "Vary difficulty and task types (analysis, writing, computation, QA, planning, etc.).\n\n"
                + (f"Seed example: {sample_seed.instruction}\n\n" if sample_seed else "")
                + "Return as a numbered list."
            )
            response = self.llm.generate(
                prompt,
                system_prompt="You are a domain-expert data generation engine.",
            )
            batch = self._parse_instructions(response, "Medium", 0)
            for inst in batch:
                inst.domain = domain
            all_instructions.extend(batch)

        if self.session:
            repo = InstructionRepository(self.session)
            for inst in all_instructions:
                repo.create_instruction(inst)

        return all_instructions
