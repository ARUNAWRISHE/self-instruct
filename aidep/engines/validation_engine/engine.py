"""
Validation Engine — Phase 5

ISSUE-04: Decomposed into composable validators:
  - StructureValidator
  - DuplicateValidator (with 3 backend strategies: ST, RapidFuzz, ROUGE)
  - ConstraintValidator

ISSUE-09: Sentence-transformer model cached as module-level singleton
          (loaded once per process, not once per pipeline run).

ISSUE-10: Constraint logic imported from shared ConstraintChecker.
"""

from __future__ import annotations

import functools
import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from aidep.core import constraint_checker
from aidep.core.interfaces import BaseValidationEngine
from aidep.core.models import TrainingExample, ValidationResult
from aidep.database.repositories.example_repo import ExampleRepository

logger = logging.getLogger(__name__)


# ── ISSUE-09: Module-level singleton for sentence-transformer model ────────────

@functools.lru_cache(maxsize=1)
def _load_sentence_transformer():
    """Load once per process — cached at module level."""
    try:
        from sentence_transformers import SentenceTransformer, util  # noqa: PLC0415
        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("ValidationEngine: sentence-transformer loaded (cached).")
        return model, util
    except Exception as exc:
        logger.warning("ValidationEngine: sentence-transformer unavailable (%s).", exc)
        return None, None


def _load_rapidfuzz():
    try:
        from rapidfuzz import fuzz  # noqa: PLC0415
        return fuzz
    except ImportError:
        return None


def _load_rouge():
    try:
        from rouge_score import rouge_scorer  # noqa: PLC0415
        return rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    except ImportError:
        return None


# ── ISSUE-04: Composable validator classes ─────────────────────────────────────

class StructureValidator:
    """Checks that instruction and output meet minimum structural requirements."""

    def __init__(self, min_output_length: int = 15):
        self.min_output_length = min_output_length

    def validate(self, example: TrainingExample) -> List[str]:
        issues = []
        if not example.instruction or not example.instruction.strip():
            issues.append("Instruction is empty.")
        if not example.output or len(example.output.strip()) < self.min_output_length:
            issues.append(
                f"Output is missing or too short (minimum {self.min_output_length} characters)."
            )
        return issues


class DuplicateValidator:
    """
    Detects duplicates using the best available backend.
    ISSUE-09: ST model loaded via cached singleton.
    """

    def __init__(self, similarity_threshold: float = 0.7):
        self.similarity_threshold = similarity_threshold
        self._st_model, self._st_util = _load_sentence_transformer()
        self._fuzz = _load_rapidfuzz()
        self._rouge = _load_rouge()

        backend = (
            "sentence-transformers"
            if self._st_model
            else ("rapidfuzz" if self._fuzz else "rouge-L")
        )
        logger.info("DuplicateValidator: using '%s' for similarity detection.", backend)

    def find_duplicate(
        self, instruction: str, existing: List[TrainingExample]
    ) -> Tuple[Optional[str], float]:
        """Return (duplicate_id, similarity_score) or (None, 0.0)."""
        if self._st_model and self._st_util:
            return self._st_similarity(instruction, existing)
        if self._fuzz:
            return self._fuzz_similarity(instruction, existing)
        if self._rouge:
            return self._rouge_similarity(instruction, existing)
        return None, 0.0

    def _st_similarity(
        self, instruction: str, existing: List[TrainingExample]
    ) -> Tuple[Optional[str], float]:
        try:
            target_emb = self._st_model.encode(instruction, convert_to_tensor=True)
            existing_texts = [e.instruction for e in existing if e.instruction]
            if not existing_texts:
                return None, 0.0
            corpus_emb = self._st_model.encode(existing_texts, convert_to_tensor=True)
            scores = self._st_util.cos_sim(target_emb, corpus_emb)[0]
            max_idx = int(scores.argmax())
            max_score = float(scores[max_idx])
            if max_score >= self.similarity_threshold:
                dup_id = str(existing[max_idx].id or existing[max_idx].instruction[:30])
                return dup_id, max_score
        except Exception as exc:
            logger.debug("ST similarity error: %s", exc)
        return None, 0.0

    def _fuzz_similarity(
        self, instruction: str, existing: List[TrainingExample]
    ) -> Tuple[Optional[str], float]:
        try:
            threshold_pct = int(self.similarity_threshold * 100)
            for ex in existing:
                if not ex.instruction:
                    continue
                score = self._fuzz.token_sort_ratio(instruction, ex.instruction)
                if score >= threshold_pct:
                    return str(ex.id or ex.instruction[:30]), score / 100.0
        except Exception as exc:
            logger.debug("RapidFuzz error: %s", exc)
        return None, 0.0

    def _rouge_similarity(
        self, instruction: str, existing: List[TrainingExample]
    ) -> Tuple[Optional[str], float]:
        for ex in existing:
            if not ex.instruction:
                continue
            scores = self._rouge.score(instruction, ex.instruction)
            rouge_l = scores["rougeL"].fmeasure
            if rouge_l >= self.similarity_threshold:
                return str(ex.id or ex.instruction[:30]), rouge_l
        return None, 0.0


class ConstraintValidator:
    """
    Validates that training example output satisfies declared constraints.
    ISSUE-10: Delegates to shared constraint_checker module.
    """

    def validate(self, example: TrainingExample) -> List[str]:
        return constraint_checker.check_violations(example)


# ── Main engine: orchestrates the three validators ────────────────────────────

class ValidationEngine(BaseValidationEngine):
    """
    ISSUE-04: Orchestrates StructureValidator, DuplicateValidator,
    and ConstraintValidator. Public interface is unchanged.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        session: Optional[Session] = None,
        min_output_length: int = 15,
    ):
        self.session = session
        self._structure = StructureValidator(min_output_length=min_output_length)
        self._duplicate = DuplicateValidator(similarity_threshold=similarity_threshold)
        self._constraint = ConstraintValidator()

    def validate(
        self,
        example: TrainingExample,
        existing: List[TrainingExample],
    ) -> ValidationResult:
        """
        Run all validation checks and return a ValidationResult.
        Persists result to DB if session is available.
        """
        reasons: List[str] = []
        duplicates: List[str] = []

        # 1. Structural checks
        reasons.extend(self._structure.validate(example))

        # 2. Duplicate / similarity check
        if example.instruction and existing:
            dup_id, sim_score = self._duplicate.find_duplicate(
                example.instruction, existing
            )
            if dup_id:
                reasons.append(
                    f"Too similar to example '{dup_id}' (similarity: {sim_score:.2f})."
                )
                duplicates.append(dup_id)

        # 3. Constraint satisfaction checks
        reasons.extend(self._constraint.validate(example))

        is_valid = len(reasons) == 0
        result = ValidationResult(
            example_id=example.id,
            is_valid=is_valid,
            reasons=reasons,
            duplicates=duplicates,
        )

        # Persist
        if self.session and example.id is not None:
            repo = ExampleRepository(self.session)
            repo.save_validation(example.id, result)
            status = "approved" if is_valid else "rejected"
            repo.update_example_status(example.id, status)

        return result
