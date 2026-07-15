"""
Quality Engine — Phase 6

Scores each validated training example on multiple quality dimensions:
  - Semantic Score    (clarity, readability, formatting)
  - Factual Score     (factuality heuristic)
  - Reasoning Score   (step-by-step logic indicators)
  - Diversity Score   (category-based novelty)
  - Consistency Score (constraint satisfaction)
  - Confidence Score  (difficulty-adjusted)
  - Toxicity Score    (heuristic safety filter)
  - Hallucination Score (complexity-adjusted estimate)
  - Overall Score     (weighted combination)

Migrated from: next_gen_self_instruct/engines/quality_evaluation.py
Extended with: DB persistence via ExampleRepository
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseQualityEngine
from aidep.core.models import (
    ApprovalStatus,
    InstructionMetadata,
    QualityMetrics,
    TaskCategory,
    TrainingExample,
)
from aidep.database.repositories.example_repo import ExampleRepository

logger = logging.getLogger(__name__)

_TOXIC_TERMS = frozenset(
    ["harmful", "illegal", "exploit", "hack", "weapon", "bomb", "violence"]
)
_LOGICAL_INDICATORS = frozenset(
    ["step", "first", "second", "then", "therefore", "because",
     "consequently", "finally", "thus", "hence"]
)


class QualityEngine(BaseQualityEngine):
    """
    Heuristic-based quality scorer.
    Produces a QualityMetrics object for each training example.
    Persists scores to DB if a session is available.
    """

    def __init__(
        self,
        quality_threshold: float = 0.65,
        session: Optional[Session] = None,
    ):
        self.quality_threshold = quality_threshold
        self.session = session

    def score(
        self,
        example: TrainingExample,
        metadata: InstructionMetadata,
    ) -> QualityMetrics:
        """Compute all quality scores and return a QualityMetrics object."""

        output = example.output or ""
        output_len = len(output)
        output_lower = output.lower()
        category = metadata.category

        # ── 1. Semantic Score ─────────────────────────────────────────────────
        semantic = 0.75
        if output_len < 30:
            semantic -= 0.25
        elif output_len > 3000:
            semantic -= 0.05
        if "```" in output:
            semantic += 0.10  # Code blocks indicate structured response
        if any(m in output for m in ["\n-", "\n1.", "\n*", "\n•"]):
            semantic += 0.05  # Lists indicate structured output
        semantic = self._clamp(semantic)

        # ── 2. Reasoning Score ────────────────────────────────────────────────
        reasoning_map = {
            "Low": 0.50, "Medium": 0.70, "High": 0.85, "Expert": 0.95
        }
        reasoning = reasoning_map.get(metadata.reasoning_level.value, 0.70)
        if any(ind in output_lower for ind in _LOGICAL_INDICATORS):
            reasoning = min(1.0, reasoning + 0.05)
        reasoning = self._clamp(reasoning)

        # ── 3. Diversity Score ────────────────────────────────────────────────
        diversity_map = {
            TaskCategory.REASONING: 0.85,
            TaskCategory.CODING: 0.85,
            TaskCategory.PLANNING: 0.80,
            TaskCategory.DIALOGUE: 0.70,
            TaskCategory.TRANSLATION: 0.65,
            TaskCategory.SUMMARIZATION: 0.65,
            TaskCategory.CLASSIFICATION: 0.60,
            TaskCategory.GENERATION: 0.70,
            TaskCategory.OTHER: 0.40,
        }
        diversity = self._clamp(diversity_map.get(category, 0.60))

        # ── 4. Consistency Score (constraint satisfaction) ────────────────────
        consistency = self._check_consistency(example)

        # ── 5. Confidence Score ───────────────────────────────────────────────
        confidence_map = {
            "Easy": 0.95, "Medium": 0.85, "Hard": 0.75, "Expert": 0.60
        }
        confidence = self._clamp(
            confidence_map.get(metadata.difficulty.value, 0.85)
        )

        # ── 6. Factual Score ──────────────────────────────────────────────────
        factual = 0.95
        if category in (TaskCategory.REASONING, TaskCategory.CODING):
            factual = 0.98
        factual = self._clamp(factual)

        # ── 7. Toxicity Score ─────────────────────────────────────────────────
        instruction_lower = example.instruction.lower()
        toxicity = 0.30 if any(t in instruction_lower for t in _TOXIC_TERMS) else 0.00
        toxicity = self._clamp(toxicity)

        # ── 8. Hallucination Score ────────────────────────────────────────────
        if metadata.complexity > 0.7:
            hallucination = 0.08
        elif metadata.complexity > 0.4:
            hallucination = 0.04
        else:
            hallucination = 0.02
        hallucination = self._clamp(hallucination)

        # ── 9. Overall Score ──────────────────────────────────────────────────
        weighted = (
            semantic * 0.25
            + reasoning * 0.20
            + diversity * 0.15
            + consistency * 0.15
            + confidence * 0.15
            + factual * 0.10
        )
        overall = self._clamp(round(weighted * (1.0 - toxicity) * (1.0 - hallucination), 4))

        # ── 10. Approval status ───────────────────────────────────────────────
        if toxicity >= 0.5:
            approval = ApprovalStatus.REJECTED
        elif overall >= self.quality_threshold and toxicity < 0.2:
            approval = ApprovalStatus.APPROVED
        else:
            approval = ApprovalStatus.PENDING

        metrics = QualityMetrics(
            semantic_score=semantic,
            factual_score=factual,
            reasoning_score=reasoning,
            diversity_score=diversity,
            consistency_score=consistency,
            confidence_score=confidence,
            toxicity_score=toxicity,
            hallucination_score=hallucination,
            overall_score=overall,
            approval_status=approval,
        )

        # Persist to DB
        if self.session and example.id is not None:
            repo = ExampleRepository(self.session)
            repo.save_quality(example.id, metrics)
            repo.update_example_status(example.id, approval.value)

        logger.debug(
            "QualityEngine: scored example (overall=%.4f, status=%s)",
            overall,
            approval.value,
        )
        return metrics

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_consistency(self, example: TrainingExample) -> float:
        """Return constraint satisfaction ratio [0.0–1.0]."""
        if not example.constraints:
            return 1.0

        satisfied = 0
        for constraint in example.constraints:
            c = constraint.lower()
            if "under" in c and "words" in c:
                try:
                    limit = int(re.search(r"\d+", c).group())
                    if len(example.output.split()) <= limit:
                        satisfied += 1
                except (AttributeError, ValueError):
                    satisfied += 1
            elif "json" in c:
                if "{" in example.output or "[" in example.output:
                    satisfied += 1
            elif any(k in c for k in ["code", "python", "function"]):
                if any(k in example.output for k in ["def ", "class ", "import ", "```"]):
                    satisfied += 1
            else:
                satisfied += 1

        return self._clamp(satisfied / len(example.constraints))

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, round(value, 4)))
