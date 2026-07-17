"""
Quality Engine — Phase 6

ISSUE-05: Each quality dimension is now an independent scorer class.
ISSUE-05: Scoring weights are read from Settings (config.yaml), not hardcoded.
ISSUE-10: Consistency scorer uses shared constraint_checker module.

Scorers:
  SemanticScorer, ReasoningScorer, DiversityScorer,
  ConsistencyScorer, ConfidenceScorer, FactualScorer,
  ToxicityScorer, HallucinationScorer
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from aidep.core import constraint_checker
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


@staticmethod
def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, round(value, 4)))


# ── ISSUE-05: Independent scorer classes ──────────────────────────────────────

class SemanticScorer:
    """Scores output clarity, structure, and length-appropriateness."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        output = example.output or ""
        output_len = len(output)
        semantic = 0.75
        if output_len < 30:
            semantic -= 0.25
        elif output_len > 3000:
            semantic -= 0.05
        if "```" in output:
            semantic += 0.10
        if any(m in output for m in ["\n-", "\n1.", "\n*", "\n•"]):
            semantic += 0.05
        return _clamp(semantic)


class ReasoningScorer:
    """Scores logical structure based on reasoning level and output indicators."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        output_lower = (example.output or "").lower()
        reasoning_map = {
            "Low": 0.50, "Medium": 0.70, "High": 0.85, "Expert": 0.95
        }
        base = reasoning_map.get(metadata.reasoning_level.value, 0.70)
        if any(ind in output_lower for ind in _LOGICAL_INDICATORS):
            base = min(1.0, base + 0.05)
        return _clamp(base)


class DiversityScorer:
    """Scores novelty based on task category."""

    _diversity_map = {
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

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        return _clamp(self._diversity_map.get(metadata.category, 0.60))


class ConsistencyScorer:
    """Scores constraint satisfaction ratio. ISSUE-10: uses shared module."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        return _clamp(constraint_checker.satisfaction_ratio(example))


class ConfidenceScorer:
    """Scores confidence based on difficulty level."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        confidence_map = {
            "Easy": 0.95, "Medium": 0.85, "Hard": 0.75, "Expert": 0.60
        }
        return _clamp(confidence_map.get(metadata.difficulty.value, 0.85))


class FactualScorer:
    """Scores factual accuracy heuristic based on category."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        base = 0.95
        if metadata.category in (TaskCategory.REASONING, TaskCategory.CODING):
            base = 0.98
        return _clamp(base)


class ToxicityScorer:
    """Flags potentially harmful content via keyword heuristic."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        instruction_lower = (example.instruction or "").lower()
        return _clamp(0.30 if any(t in instruction_lower for t in _TOXIC_TERMS) else 0.00)


class HallucinationScorer:
    """Estimates hallucination risk from instruction complexity."""

    def score(self, example: TrainingExample, metadata: InstructionMetadata) -> float:
        if metadata.complexity > 0.7:
            return _clamp(0.08)
        elif metadata.complexity > 0.4:
            return _clamp(0.04)
        return _clamp(0.02)


# ── Main engine: orchestrates all scorers ─────────────────────────────────────

class QualityEngine(BaseQualityEngine):
    """
    ISSUE-05: Orchestrates individual scorer classes.
    Weights loaded from Settings — fully configurable via config.yaml.
    """

    def __init__(
        self,
        quality_threshold: float = 0.65,
        session: Optional[Session] = None,
        weights: Optional[dict] = None,
    ):
        self.quality_threshold = quality_threshold
        self.session = session

        # Default weights — overridden by config if provided
        default_weights = {
            "semantic": 0.25,
            "reasoning": 0.20,
            "diversity": 0.15,
            "consistency": 0.15,
            "confidence": 0.15,
            "factual": 0.10,
        }
        self._weights = weights or default_weights

        # Instantiate scorers
        self._semantic = SemanticScorer()
        self._reasoning = ReasoningScorer()
        self._diversity = DiversityScorer()
        self._consistency = ConsistencyScorer()
        self._confidence = ConfidenceScorer()
        self._factual = FactualScorer()
        self._toxicity = ToxicityScorer()
        self._hallucination = HallucinationScorer()

    def score(
        self,
        example: TrainingExample,
        metadata: InstructionMetadata,
    ) -> QualityMetrics:
        """Compute all quality scores and return a QualityMetrics object."""

        semantic = self._semantic.score(example, metadata)
        reasoning = self._reasoning.score(example, metadata)
        diversity = self._diversity.score(example, metadata)
        consistency = self._consistency.score(example, metadata)
        confidence = self._confidence.score(example, metadata)
        factual = self._factual.score(example, metadata)
        toxicity = self._toxicity.score(example, metadata)
        hallucination = self._hallucination.score(example, metadata)

        w = self._weights
        weighted = (
            semantic * w.get("semantic", 0.25)
            + reasoning * w.get("reasoning", 0.20)
            + diversity * w.get("diversity", 0.15)
            + consistency * w.get("consistency", 0.15)
            + confidence * w.get("confidence", 0.15)
            + factual * w.get("factual", 0.10)
        )
        overall = _clamp(round(weighted * (1.0 - toxicity) * (1.0 - hallucination), 4))

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
