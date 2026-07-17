"""
AIDEP Orchestrator — Thin Workflow Coordinator

ISSUE-01: Uses PipelineContext to carry all run state as a single snapshot.
ISSUE-02: Records start/complete/fail in pipeline_runs table.
ISSUE-16: Per-stage timing logged using time.perf_counter().

The orchestrator has NO business logic. Its only responsibilities are:
  1. Run each engine in the correct sequence
  2. Pass outputs between engines via PipelineContext
  3. Persist run metadata via PipelineRunRepository

Engine sequence:
  KnowledgeEngine → InstructionEngine → IntelligenceEngine →
  ExampleEngine → ValidationEngine → QualityEngine → DatasetEngine
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseOrchestrator
from aidep.core.llm import LLMClient
from aidep.core.models import (
    PipelineContext,
    PipelineResult,
    SeedTask,
    TrainingExample,
)
from aidep.database.repositories.pipeline_run_repo import PipelineRunRepository
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
    ISSUE-01: Carries state via PipelineContext.
    ISSUE-02: Tracks every run in pipeline_runs table.
    ISSUE-16: Logs per-stage timing.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        session: Optional[Session] = None,
        num_instructions: int = 10,
        similarity_threshold: float = 0.7,
        quality_threshold: float = 0.65,
        output_dir: str = "datasets",
        quality_weights: Optional[Dict[str, float]] = None,
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
            quality_threshold=quality_threshold,
            session=session,
            weights=quality_weights,
        )
        self.dataset_engine = DatasetEngine(output_dir=output_dir, session=session)

    # ── Timing helper ─────────────────────────────────────────────────────────

    def _time_stage(self, ctx: PipelineContext, name: str, start: float) -> None:
        """ISSUE-16: Record elapsed time for a stage and log it."""
        elapsed = time.perf_counter() - start
        ctx.stage_timings[name] = round(elapsed, 3)
        logger.info("Orchestrator: [%s] completed in %.2fs.", name, elapsed)

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def run_pipeline(
        self,
        seeds: Optional[List[SeedTask]] = None,
        version: str = "1.0.0",
    ) -> PipelineResult:
        """
        Execute the full AIDEP pipeline end-to-end.
        ISSUE-01: All state flows through PipelineContext.
        ISSUE-02: Run tracked in DB from start to finish.
        """
        # ISSUE-01: Create context for this run
        ctx = PipelineContext(
            version=version,
            started_at=datetime.now(timezone.utc),
        )

        # ISSUE-02: Record run start
        run_repo = PipelineRunRepository(self.session) if self.session else None
        if run_repo:
            run_record = run_repo.create(version=version)
            ctx.run_id = run_record.id
            logger.info("Orchestrator: pipeline_run id=%d started.", ctx.run_id)

        logger.info("=" * 60)
        logger.info("AIDEP Orchestrator: starting pipeline (version=%s)", version)
        logger.info("=" * 60)

        try:
            # ── Step 1: Load seeds ────────────────────────────────────────────
            t0 = time.perf_counter()
            if seeds is None:
                seeds = self.knowledge_engine.get_all_seeds()
            ctx.seeds = seeds
            self._time_stage(ctx, "Step 1: Knowledge", t0)

            if not ctx.seeds:
                logger.warning("Orchestrator: no seeds available. Pipeline aborted.")
                ctx.error_log.append("No seeds available — pipeline aborted.")
                if run_repo:
                    run_repo.fail(ctx.run_id, error_log=ctx.error_log)
                return PipelineResult()

            logger.info("Orchestrator: %d seeds in Knowledge Repository.", len(ctx.seeds))

            # ── Step 2: Generate instructions ─────────────────────────────────
            t0 = time.perf_counter()
            logger.info(
                "Orchestrator: generating %d instruction candidates...",
                self.num_instructions,
            )
            ctx.instructions = self.instruction_engine.generate(
                ctx.seeds, self.num_instructions
            )
            self._time_stage(ctx, "Step 2: InstructionGeneration", t0)
            logger.info("Orchestrator: %d candidates generated.", len(ctx.instructions))

            # ── Steps 3–6: Per-instruction pipeline ───────────────────────────
            t0 = time.perf_counter()
            accepted_examples: List[TrainingExample] = []
            rejected_count = 0

            for idx, instruction in enumerate(ctx.instructions, 1):
                log_prefix = f"[{idx}/{len(ctx.instructions)}]"
                logger.info(
                    "%s Processing: '%s...'",
                    log_prefix,
                    instruction.instruction[:60],
                )

                try:
                    # Step 3: Intelligence — classify the instruction
                    metadata = self.intelligence_engine.analyze(instruction)
                    instruction.id = metadata.instruction_id

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
                    ctx.error_log.append(
                        f"[{idx}] {instruction.instruction[:40]}: {exc}"
                    )
                    rejected_count += 1

            ctx.accepted_examples = accepted_examples
            ctx.rejected_count = rejected_count
            self._time_stage(ctx, "Steps 3-6: ProcessingLoop", t0)

            # ── Step 7: Export dataset ─────────────────────────────────────────
            t0 = time.perf_counter()
            logger.info(
                "Orchestrator: exporting %d approved examples...",
                len(ctx.accepted_examples),
            )
            export_result = self.dataset_engine.export_full(
                ctx.accepted_examples, version
            )
            ctx.export_path = export_result.export_path
            ctx.quality_report = export_result.quality_report
            ctx.weaknesses = export_result.quality_report.get("weaknesses", [])
            self._time_stage(ctx, "Step 7: Export", t0)

            # ISSUE-02: Record successful completion
            if run_repo:
                run_repo.complete(
                    run_id=ctx.run_id,
                    seed_count=len(ctx.seeds),
                    instruction_count=len(ctx.instructions),
                    accepted_count=len(ctx.accepted_examples),
                    rejected_count=ctx.rejected_count,
                    dataset_path=ctx.export_path,
                    error_log=ctx.error_log,
                )

            logger.info("=" * 60)
            logger.info("AIDEP Orchestrator: pipeline complete.")
            logger.info("  Total candidates : %d", len(ctx.instructions))
            logger.info("  Accepted         : %d", len(ctx.accepted_examples))
            logger.info("  Rejected         : %d", ctx.rejected_count)
            logger.info("  Exported to      : %s", ctx.export_path)
            logger.info("  Stage timings    : %s", ctx.stage_timings)
            logger.info("=" * 60)

            return PipelineResult(
                total_candidates=len(ctx.instructions),
                accepted_count=len(ctx.accepted_examples),
                rejected_count=ctx.rejected_count,
                total_dataset_size=len(ctx.accepted_examples),
                export_path=ctx.export_path,
                quality_report=ctx.quality_report,
                weaknesses=ctx.weaknesses,
            )

        except Exception as exc:
            logger.error("Orchestrator: fatal pipeline error: %s", exc, exc_info=True)
            ctx.error_log.append(f"Fatal: {exc}")
            if run_repo:
                run_repo.fail(ctx.run_id, error_log=ctx.error_log)
            raise

    # ── Convenience single-step methods ───────────────────────────────────────

    def load_seeds_from_file(self, path: str) -> List[SeedTask]:
        """Load seeds from a JSONL file into the Knowledge Repository."""
        return self.knowledge_engine.load_seeds(path)

    def add_seed(self, seed: SeedTask) -> SeedTask:
        """Add a single seed to the Knowledge Repository."""
        return self.knowledge_engine.add_seed(seed)

    def get_all_seeds(self) -> List[SeedTask]:
        return self.knowledge_engine.get_all_seeds()
