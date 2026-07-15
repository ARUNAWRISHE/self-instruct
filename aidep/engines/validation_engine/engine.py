"""
Validation Engine — Phase 5

Validates training examples against:
  1. Structural checks (non-empty instruction/output, minimum length)
  2. Duplicate detection (RapidFuzz fuzzy matching + ROUGE-L similarity)
  3. Semantic similarity (sentence-transformers cosine similarity)
  4. Consistency (constraint satisfaction checks)

Migrated from: next_gen_self_instruct/engines/validation.py
Extended with:
  - RapidFuzz for fast fuzzy duplicate detection
  - sentence-transformers for semantic similarity (when available)
  - DB persistence via ExampleRepository
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseValidationEngine
from aidep.core.models import TrainingExample, ValidationResult
from aidep.database.repositories.example_repo import ExampleRepository

logger = logging.getLogger(__name__)


# ── Optional imports (graceful degradation) ───────────────────────────────────

def _try_rouge():
    try:
        from rouge_score import rouge_scorer  # noqa: PLC0415
        return rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    except ImportError:
        return None


def _try_rapidfuzz():
    try:
        from rapidfuzz import fuzz  # noqa: PLC0415
        return fuzz
    except ImportError:
        return None


def _try_sentence_transformers():
    try:
        from sentence_transformers import SentenceTransformer, util  # noqa: PLC0415
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model, util
    except Exception:
        return None, None


class ValidationEngine(BaseValidationEngine):
    """
    Multi-layer validation engine.

    Similarity is checked using the best available method:
      1. sentence-transformers (semantic cosine similarity) — highest quality
      2. RapidFuzz (fast fuzzy string matching) — medium quality
      3. ROUGE-L — fallback

    All three can coexist; the primary method is used for the threshold comparison.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        session: Optional[Session] = None,
        min_output_length: int = 15,
    ):
        self.similarity_threshold = similarity_threshold
        self.session = session
        self.min_output_length = min_output_length

        # Initialize available similarity backends
        self._rouge = _try_rouge()
        self._fuzz = _try_rapidfuzz()
        self._st_model, self._st_util = _try_sentence_transformers()

        backend = (
            "sentence-transformers"
            if self._st_model
            else ("rapidfuzz" if self._fuzz else "rouge-L")
        )
        logger.info("ValidationEngine: using '%s' for similarity detection.", backend)

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
        if not example.instruction or not example.instruction.strip():
            reasons.append("Instruction is empty.")

        if not example.output or len(example.output.strip()) < self.min_output_length:
            reasons.append(
                f"Output is missing or too short (minimum {self.min_output_length} characters)."
            )

        # 2. Duplicate / similarity check
        if example.instruction and existing:
            dup_id, sim_score = self._find_duplicate(example.instruction, existing)
            if dup_id:
                reasons.append(
                    f"Too similar to example '{dup_id}' (similarity: {sim_score:.2f})."
                )
                duplicates.append(dup_id)

        # 3. Consistency checks (constraint satisfaction)
        constraint_issues = self._check_constraints(example)
        reasons.extend(constraint_issues)

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

    # ── Similarity detection ──────────────────────────────────────────────────

    def _find_duplicate(
        self,
        instruction: str,
        existing: List[TrainingExample],
    ) -> tuple[Optional[str], float]:
        """
        Return (duplicate_id, similarity_score) if a duplicate is found,
        otherwise (None, 0.0).
        """
        if self._st_model and self._st_util:
            return self._st_similarity(instruction, existing)
        if self._fuzz:
            return self._fuzz_similarity(instruction, existing)
        if self._rouge:
            return self._rouge_similarity(instruction, existing)
        return None, 0.0

    def _st_similarity(
        self,
        instruction: str,
        existing: List[TrainingExample],
    ) -> tuple[Optional[str], float]:
        """Sentence-transformer cosine similarity."""
        try:
            import torch  # noqa: PLC0415

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
        self,
        instruction: str,
        existing: List[TrainingExample],
    ) -> tuple[Optional[str], float]:
        """RapidFuzz token_sort_ratio similarity."""
        try:
            threshold_pct = int(self.similarity_threshold * 100)
            for ex in existing:
                if not ex.instruction:
                    continue
                score = self._fuzz.token_sort_ratio(instruction, ex.instruction)
                if score >= threshold_pct:
                    dup_id = str(ex.id or ex.instruction[:30])
                    return dup_id, score / 100.0
        except Exception as exc:
            logger.debug("RapidFuzz error: %s", exc)

        return None, 0.0

    def _rouge_similarity(
        self,
        instruction: str,
        existing: List[TrainingExample],
    ) -> tuple[Optional[str], float]:
        """ROUGE-L F1 similarity (fallback)."""
        for ex in existing:
            if not ex.instruction:
                continue
            scores = self._rouge.score(instruction, ex.instruction)
            rouge_l = scores["rougeL"].fmeasure
            if rouge_l >= self.similarity_threshold:
                dup_id = str(ex.id or ex.instruction[:30])
                return dup_id, rouge_l

        return None, 0.0

    # ── Constraint checks ─────────────────────────────────────────────────────

    def _check_constraints(self, example: TrainingExample) -> List[str]:
        """Basic rule-based constraint satisfaction check."""
        issues: List[str] = []
        import re

        for constraint in example.constraints:
            c_lower = constraint.lower()

            # Word count limit: "under N words"
            if "under" in c_lower and "words" in c_lower:
                try:
                    limit = int(re.search(r"\d+", c_lower).group())
                    word_count = len(example.output.split())
                    if word_count > limit:
                        issues.append(
                            f"Output exceeds word limit ({word_count} > {limit})."
                        )
                except (AttributeError, ValueError):
                    pass

            # JSON output required
            elif "json" in c_lower:
                if "{" not in example.output and "[" not in example.output:
                    issues.append("Constraint requires JSON output but none found.")

            # Code output required
            elif any(k in c_lower for k in ["code", "python", "function"]):
                if not any(
                    k in example.output
                    for k in ["def ", "class ", "import ", "```"]
                ):
                    issues.append("Constraint requires code output but none found.")

        return issues
