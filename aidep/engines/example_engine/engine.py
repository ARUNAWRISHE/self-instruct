"""
Example Engine — Phase 4

Converts an analyzed instruction into a complete training example.
ISSUE-03: Prompt loaded from PromptLibraryService, not hardcoded.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseExampleEngine
from aidep.core.llm import LLMClient
from aidep.core.models import (
    ApprovalStatus,
    GeneratedInstruction,
    InstructionMetadata,
    QualityMetrics,
    TrainingExample,
)
from aidep.database.repositories.example_repo import ExampleRepository
from aidep.services.prompt_service import PromptLibraryService

logger = logging.getLogger(__name__)


class ExampleEngine(BaseExampleEngine):
    """
    Generates input/output training pairs for each instruction.
    ISSUE-03: Uses PromptLibraryService for all prompt text.
    Stores the result in the training_examples table.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
    ):
        self.llm = llm_client
        self.session = session
        self.prompt_library = PromptLibraryService(session=session)

    def generate_example(
        self,
        instruction: GeneratedInstruction,
        metadata: InstructionMetadata,
    ) -> TrainingExample:
        """
        Generate a training example (input + output + constraints)
        for the given instruction.
        """
        template = self.prompt_library.get_prompt("example_generation")
        prompt = template.format(
            instruction=instruction.instruction,
            task_type=metadata.task_type,
            domain=metadata.domain,
            difficulty=metadata.difficulty.value,
            expected_output_type=metadata.expected_output_type,
        )

        response = self.llm.generate(
            prompt,
            system_prompt="You are a high-quality training-example generator for AI alignment datasets.",
        )

        constraints, input_val, output_val = self._parse_response(response)

        example = TrainingExample(
            instruction_id=instruction.id,
            instruction=instruction.instruction,
            input=input_val,
            output=output_val,
            context=None,
            constraints=constraints,
            task_metadata=metadata,
            quality=QualityMetrics(approval_status=ApprovalStatus.PENDING),
            status="pending",
        )

        # Persist to DB
        if self.session and instruction.id is not None:
            repo = ExampleRepository(self.session)
            record = repo.create_example(example, instruction_db_id=instruction.id)
            example.id = record.id

        logger.debug(
            "ExampleEngine: generated example for instruction_id=%s "
            "(output_len=%d, constraints=%d)",
            instruction.id,
            len(output_val),
            len(constraints),
        )
        return example

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_response(
        self, response: str
    ) -> tuple[list[str], str, str]:
        """Parse Constraints / Input / Output from the LLM response."""
        constraints: list[str] = []
        input_val = ""
        output_val = ""

        lines = response.split("\n")
        current_field: Optional[str] = None
        current_text: list[str] = []

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if lower.startswith("constraints:"):
                current_field = "constraints"
                val = stripped[len("constraints:"):].strip()
                if val.lower() != "none" and val:
                    constraints = [c.strip() for c in val.split(",") if c.strip()]
                current_text = []

            elif lower.startswith("input:"):
                if current_field == "constraints":
                    pass
                current_field = "input"
                val = stripped[len("input:"):].strip()
                current_text = [val] if val.lower() not in ("none", "") else []

            elif lower.startswith("output:"):
                if current_field == "input":
                    input_val = "\n".join(current_text).strip()
                current_field = "output"
                val = stripped[len("output:"):].strip()
                current_text = [val]

            else:
                if current_field:
                    current_text.append(line)

        # Flush remaining
        if current_field == "output":
            output_val = "\n".join(current_text).strip()
        elif current_field == "input":
            input_val = "\n".join(current_text).strip()

        # Fallback: use the entire response as output if nothing parsed
        if not output_val:
            output_val = response.strip()

        return constraints, input_val, output_val
