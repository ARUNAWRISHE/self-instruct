"""
Dataset Engine — Phase 7

Manages the Dataset Repository:
  - Stores approved/rejected samples
  - Exports dataset.jsonl
  - Generates quality report
  - Formats alignment data (OpenAI chat / GPT-3 finetune / generic)
  - Detects dataset weaknesses (continuous improvement signal)

Migrated from: next_gen_self_instruct/engines/dataset_management.py +
               next_gen_self_instruct/engines/model_alignment.py +
               next_gen_self_instruct/engines/continuous_improvement.py
Extended with: DB persistence via DatasetRepository + ExampleRepository
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from aidep.core.interfaces import BaseDatasetEngine
from aidep.core.models import DatasetExportResult, TrainingExample
from aidep.database.repositories.dataset_repo import DatasetRepository
from aidep.database.repositories.example_repo import ExampleRepository

logger = logging.getLogger(__name__)

_TARGET_CATEGORY_RATIOS = {
    "coding": 0.15,
    "reasoning": 0.15,
    "summarization": 0.10,
    "translation": 0.10,
}


class DatasetEngine(BaseDatasetEngine):
    """
    Final-stage engine that exports the approved dataset and generates
    a quality report + alignment file.
    """

    def __init__(
        self,
        output_dir: str = "datasets",
        session: Optional[Session] = None,
    ):
        self.output_dir = output_dir
        self.session = session
        os.makedirs(output_dir, exist_ok=True)

    def export(
        self,
        examples: List[TrainingExample],
        version: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Export approved examples to dataset.jsonl.
        Returns the path to the exported file.
        """
        approved = [e for e in examples if e.quality.approval_status.value == "approved"]

        if output_path is None:
            output_path = os.path.join(self.output_dir, "dataset.jsonl")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        records = [self._to_jsonl_record(ex, version) for ex in approved]

        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        logger.info(
            "DatasetEngine: exported %d approved examples to %s",
            len(approved),
            output_path,
        )

        # Save archived version
        archive_dir = os.path.join(self.output_dir, "archives")
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, f"dataset_v{version}.jsonl")
        with open(archive_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        return output_path

    def export_full(
        self,
        examples: List[TrainingExample],
        version: str = "1.0.0",
    ) -> DatasetExportResult:
        """
        Export dataset, generate quality report, persist dataset record to DB.
        Returns a DatasetExportResult.
        """
        output_path = os.path.join(self.output_dir, "dataset.jsonl")
        self.export(examples, version, output_path)

        # Generate alignment file
        alignment_path = os.path.join(self.output_dir, "alignment_openai_chat.jsonl")
        alignment_data = self.format_for_alignment(examples, "openai_chat")
        with open(alignment_path, "w", encoding="utf-8") as f:
            for item in alignment_data:
                f.write(json.dumps(item) + "\n")

        approved = [e for e in examples if e.quality.approval_status.value == "approved"]
        rejected = [e for e in examples if e.quality.approval_status.value == "rejected"]

        quality_report = self._build_quality_report(examples)
        weaknesses = self.detect_weaknesses(examples)
        quality_report["weaknesses"] = weaknesses

        # Persist dataset record
        dataset_id = 0
        if self.session:
            repo = DatasetRepository(self.session)
            record = repo.create(
                name=f"AIDEP Dataset v{version}",
                version=version,
                export_path=output_path,
                total_examples=len(examples),
                approved_count=len(approved),
                rejected_count=len(rejected),
                quality_report=quality_report,
            )
            dataset_id = record.id

        logger.info(
            "DatasetEngine: full export complete "
            "(total=%d, approved=%d, rejected=%d)",
            len(examples),
            len(approved),
            len(rejected),
        )

        return DatasetExportResult(
            dataset_id=dataset_id,
            name=f"AIDEP Dataset v{version}",
            version=version,
            export_path=output_path,
            total_examples=len(examples),
            approved_count=len(approved),
            rejected_count=len(rejected),
            quality_report=quality_report,
        )

    # ── Alignment formatting ──────────────────────────────────────────────────

    def format_for_alignment(
        self,
        examples: List[TrainingExample],
        format_type: str = "openai_chat",
    ) -> List[Dict[str, Any]]:
        """Format approved examples for fine-tuning."""
        approved = [e for e in examples if e.quality.approval_status.value in ("approved", "pending_review")]
        formatted = []

        for ex in approved:
            prompt_parts = []
            if ex.constraints:
                prompt_parts.append("Constraints to follow:")
                prompt_parts.extend(f"- {c}" for c in ex.constraints)
                prompt_parts.append("")
            if ex.context:
                prompt_parts.append(f"Context: {ex.context}\n")
            prompt_parts.append(f"Task: {ex.instruction}")
            if ex.input:
                prompt_parts.append(f"Input: {ex.input}")
            full_prompt = "\n".join(prompt_parts).strip()

            if format_type == "openai_chat":
                formatted.append({
                    "messages": [
                        {"role": "system", "content": "You are a helpful, instruction-following assistant."},
                        {"role": "user", "content": full_prompt},
                        {"role": "assistant", "content": ex.output},
                    ]
                })
            elif format_type == "gpt3_finetune":
                formatted.append({
                    "prompt": full_prompt + "\n\nResponse:",
                    "completion": " " + ex.output,
                })
            else:
                formatted.append({
                    "prompt": full_prompt,
                    "response": ex.output,
                })

        return formatted

    # ── Quality reporting ─────────────────────────────────────────────────────

    def _build_quality_report(self, examples: List[TrainingExample]) -> Dict[str, Any]:
        if not examples:
            return {}

        approved = [e for e in examples if e.quality.approval_status.value == "approved"]
        scores = [e.quality.overall_score for e in approved]

        category_dist: Dict[str, int] = {}
        for ex in examples:
            cat = ex.task_metadata.category.value
            category_dist[cat] = category_dist.get(cat, 0) + 1

        return {
            "total_examples": len(examples),
            "approved_count": len(approved),
            "rejected_count": len(examples) - len(approved),
            "approval_rate": round(len(approved) / max(len(examples), 1), 4),
            "avg_quality_score": round(sum(scores) / max(len(scores), 1), 4),
            "min_quality_score": round(min(scores, default=0.0), 4),
            "max_quality_score": round(max(scores, default=0.0), 4),
            "category_distribution": category_dist,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def detect_weaknesses(self, examples: List[TrainingExample]) -> List[str]:
        """Identify category deficits and suggest improvements."""
        if not examples:
            return ["Dataset is empty. Initiate generation pipeline."]

        category_counts: Dict[str, int] = {}
        for ex in examples:
            cat = ex.task_metadata.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        total = len(examples)
        weaknesses = []

        for category, target in _TARGET_CATEGORY_RATIOS.items():
            count = category_counts.get(category, 0)
            ratio = count / total
            if ratio < target:
                deficit = max(1, int(total * target) - count)
                weaknesses.append(
                    f"Category deficit: '{category}' is {ratio*100:.1f}% of dataset "
                    f"(target ≥ {target*100:.1f}%). "
                    f"Suggest generating {deficit} more '{category}' instructions."
                )

        return weaknesses

    # ── JSONL record serialization ────────────────────────────────────────────

    @staticmethod
    def _to_jsonl_record(example: TrainingExample, version: str) -> Dict[str, Any]:
        return {
            "sample_id": str(example.id or "unknown"),
            "instruction": example.instruction,
            "input": example.input or "",
            "output": example.output,
            "context": example.context,
            "constraints": example.constraints,
            "task": {
                "task_type": example.task_metadata.task_type,
                "category": example.task_metadata.category.value,
                "domain": example.task_metadata.domain,
                "subdomain": example.task_metadata.subdomain,
                "difficulty": example.task_metadata.difficulty.value,
                "reasoning_level": example.task_metadata.reasoning_level.value,
                "expected_output_type": example.task_metadata.expected_output_type,
                "complexity": example.task_metadata.complexity,
            },
            "provenance": {
                "source": "aidep_pipeline",
                "source_type": "synthetic",
                "dataset_version": version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "quality": {
                "semantic_score": example.quality.semantic_score,
                "factual_score": example.quality.factual_score,
                "reasoning_score": example.quality.reasoning_score,
                "diversity_score": example.quality.diversity_score,
                "consistency_score": example.quality.consistency_score,
                "confidence_score": example.quality.confidence_score,
                "toxicity_score": example.quality.toxicity_score,
                "hallucination_score": example.quality.hallucination_score,
                "overall_score": example.quality.overall_score,
                "approval_status": example.quality.approval_status.value,
            },
        }
