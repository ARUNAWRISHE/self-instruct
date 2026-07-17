"""
PipelineService — ISSUE-15

Encapsulates orchestrator construction and pipeline execution.
The pipeline route now calls this service instead of building
the orchestrator directly, keeping routes clean.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from aidep.core.llm import LLMClient
from aidep.core.models import PipelineResult
from aidep.core.config import Settings

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(
        self,
        session: Session,
        llm_client: LLMClient,
        settings: Settings,
    ):
        self.session = session
        self.llm = llm_client
        self.settings = settings

    def run(
        self,
        count: int,
        version: str = "1.0.0",
        seed_file: str = "",
        run_id: Optional[int] = None,
    ) -> PipelineResult:
        """Build the orchestrator and run the full pipeline."""
        from aidep.orchestrator.pipeline import AIDEPOrchestrator  # noqa: PLC0415

        s = self.settings
        orchestrator = AIDEPOrchestrator(
            llm_client=self.llm,
            session=self.session,
            num_instructions=count,
            similarity_threshold=s.validation_similarity_threshold,
            quality_threshold=s.quality_threshold,
            output_dir=s.output_dir,
            quality_weights={
                "semantic": s.quality_weight_semantic,
                "reasoning": s.quality_weight_reasoning,
                "diversity": s.quality_weight_diversity,
                "consistency": s.quality_weight_consistency,
                "confidence": s.quality_weight_confidence,
                "factual": s.quality_weight_factual,
            },
        )

        if seed_file:
            orchestrator.load_seeds_from_file(seed_file)

        return orchestrator.run_pipeline(version=version, run_id=run_id)
