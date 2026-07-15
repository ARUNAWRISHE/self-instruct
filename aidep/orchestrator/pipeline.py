"""
AIDEP Orchestrator — Thin Workflow Coordinator

The orchestrator has NO business logic. Its only responsibilities are:
  1. Run each engine in the correct sequence
  2. Pass outputs between engines
  3. Manage workflow state and counts
  4. Handle per-example retries

Engine sequence:
  KnowledgeEngine → InstructionEngine → IntelligenceEngine →
  ExampleEngine → ValidationEngine → QualityEngine → DatasetEngine
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseOrchestrator
from aidep.core.llm import LLMClient
from aidep.core.models import (
    PipelineResult,
    SeedTask,
    TrainingExample,
)
from aidep.engines.dataset_engine.engine import DatasetEngine
from aidep.engines.example_engine.engine import ExampleEngine
from aidep.engines.intelligence_engine.engine import IntelligenceEngine
from aidep.engines.instruction_engine.engine import InstructionEngine
from aidep.engines.knowledge_engine.engine import KnowledgeEngine
from aidep.engines.quality_engine.engine import QualityEngine
from aidep.engines.validation_engine.engine import ValidationEngine

logger = logging.getLogger(__name__)


class AIDEPOrchestrator(BaseOrchestrator):
    """
    Sequences all 7 AIDEP engines to run the complete pipeline.

    All engines are stateless workers; the orchestrator wires their
    inputs/outputs together and tracks workflow state.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
        num_instructions: int = 10,
        similarity_threshold: float = 0.7,
        quality_threshold: float = 0.65,
        output_dir: str = "datasets",
    ):
        self.llm = llm_client
        self.session = session
        self.num_instructions = num_instructions
        self.output_dir = output_dir

        # ── Wire up all engines ───────────────────────────────────────────────
        self.knowledge_engine = KnowledgeEngine(session=session)
        self.instruction_engine = InstructionEngine(llm_client, session=session)
        self.intelligence_engine = IntelligenceEngine(llm_client, session=session)
        self.example_engine = ExampleEngine(llm_client, session=session)
        self.validation_engine = ValidationEngine(
            similarity_threshold=similarity_threshold, session=session
        )
        self.quality_engine = QualityEngine(
            quality_threshold=quality_threshold, session=session
        )
        self.dataset_engine = DatasetEngine(output_dir=output_dir, session=session)

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def run_pipeline(
        self,
        seeds: Optional[List[SeedTask]] = None,
        version: str = "1.0.0",
    ) -> PipelineResult:
        """
        Execute the full AIDEP pipeline end-to-end.

        Args:
            seeds: Optional list of SeedTask objects. If None, loads from DB.
            version: Dataset version string for export naming.

        Returns:
            PipelineResult with counts and export paths.
        """
        logger.info("=" * 60)
        logger.info("AIDEP Orchestrator: starting pipeline (version=%s)", version)
        logger.info("=" * 60)

        # ── Step 1: Load seeds ────────────────────────────────────────────────
        if seeds is None:
            seeds = self.knowledge_engine.get_all_seeds()

        if not seeds:
            logger.warning("Orchestrator: no seeds available. Pipeline aborted.")
            return PipelineResult()

        logger.info("Orchestrator: %d seeds in Knowledge Repository.", len(seeds))

        # ── Step 2: Generate instructions ─────────────────────────────────────
        logger.info(
            "Orchestrator: generating %d instruction candidates...",
            self.num_instructions,
        )
        instructions = self.instruction_engine.generate(seeds, self.num_instructions)
        logger.info("Orchestrator: %d candidates generated.", len(instructions))

        # ── Steps 3–6: Per-instruction pipeline ───────────────────────────────
        accepted_examples: List[TrainingExample] = []
        rejected_count = 0

        for idx, instruction in enumerate(instructions, 1):
            log_prefix = f"[{idx}/{len(instructions)}]"
            logger.info(
                "%s Processing: '%s...'",
                log_prefix,
                instruction.instruction[:60],
            )

            try:
                # Step 3: Intelligence — classify the instruction
                metadata = self.intelligence_engine.analyze(instruction)
                instruction.id = metadata.instruction_id  # sync back DB id

                # Step 4: Example — generate training pair
                example = self.example_engine.generate_example(instruction, metadata)

                # Step 5: Validation — check quality and uniqueness
                validation = self.validation_engine.validate(
                    example, accepted_examples
                )

                if not validation.is_valid:
                    logger.info(
                        "%s REJECTED (validation): %s",
                        log_prefix,
                        "; ".join(validation.reasons),
                    )
                    rejected_count += 1
                    continue

                # Step 6: Quality — score the example
                quality = self.quality_engine.score(example, metadata)
                example.quality = quality

                if quality.approval_status.value == "rejected":
                    logger.info(
                        "%s REJECTED (quality < threshold): overall=%.4f",
                        log_prefix,
                        quality.overall_score,
                    )
                    rejected_count += 1
                    continue

                logger.info(
                    "%s ACCEPTED: overall=%.4f, category=%s, difficulty=%s",
                    log_prefix,
                    quality.overall_score,
                    metadata.category.value,
                    metadata.difficulty.value,
                )
                accepted_examples.append(example)

            except Exception as exc:
                logger.error(
                    "%s Pipeline error for instruction '%s': %s",
                    log_prefix,
                    instruction.instruction[:40],
                    exc,
                    exc_info=True,
                )
                rejected_count += 1

        # ── Step 7: Export dataset ─────────────────────────────────────────────
        logger.info(
            "Orchestrator: exporting %d approved examples...",
            len(accepted_examples),
        )
        export_result = self.dataset_engine.export_full(accepted_examples, version)

        logger.info("=" * 60)
        logger.info("AIDEP Orchestrator: pipeline complete.")
        logger.info("  Total candidates : %d", len(instructions))
        logger.info("  Accepted         : %d", len(accepted_examples))
        logger.info("  Rejected         : %d", rejected_count)
        logger.info("  Exported to      : %s", export_result.export_path)
        logger.info("=" * 60)

        return PipelineResult(
            total_candidates=len(instructions),
            accepted_count=len(accepted_examples),
            rejected_count=rejected_count,
            total_dataset_size=len(accepted_examples),
            export_path=export_result.export_path,
            quality_report=export_result.quality_report,
            weaknesses=export_result.quality_report.get("weaknesses", []),
        )

    # ── Convenience single-step methods ───────────────────────────────────────

    def load_seeds_from_file(self, path: str) -> List[SeedTask]:
        """Load seeds from a JSONL file into the Knowledge Repository."""
        return self.knowledge_engine.load_seeds(path)

    def add_seed(self, seed: SeedTask) -> SeedTask:
        """Add a single seed to the Knowledge Repository."""
        return self.knowledge_engine.add_seed(seed)

    def get_all_seeds(self) -> List[SeedTask]:
        return self.knowledge_engine.get_all_seeds()
