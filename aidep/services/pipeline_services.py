"""Services for instruction generation, analysis, example generation,
validation, quality scoring, and dataset export."""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from aidep.core.llm import LLMClient
from aidep.core.models import (
    ApprovalStatus,
    GeneratedInstruction,
    InstructionMetadata,
    SeedTask,
    TaskCategory,
    TrainingExample,
)
from aidep.database.repositories.example_repo import ExampleRepository
from aidep.database.repositories.instruction_repo import InstructionRepository
from aidep.database.repositories.seed_repo import SeedRepository
from aidep.engines.dataset_engine.engine import DatasetEngine
from aidep.engines.example_engine.engine import ExampleEngine
from aidep.engines.instruction_engine.engine import InstructionEngine
from aidep.engines.intelligence_engine.engine import IntelligenceEngine
from aidep.engines.quality_engine.engine import QualityEngine
from aidep.engines.validation_engine.engine import ValidationEngine
from aidep.schemas.dataset import (
    DatasetExportRequest,
    DatasetExportResponse,
    ExampleGenerateResponse,
    ExampleResponse,
    QualityResponse,
    QualityScoreResponse,
    ValidateResponse,
    ValidationResultResponse,
)
from aidep.schemas.instruction import (
    InstructionAnalyzeResponse,
    InstructionGenerateResponse,
    InstructionMetadataResponse,
    InstructionResponse,
)

logger = logging.getLogger(__name__)


# ── Instruction Service ───────────────────────────────────────────────────────

class InstructionService:
    def __init__(self, session: Session, llm_client: LLMClient):
        self.session = session
        self.llm = llm_client
        self.seed_repo = SeedRepository(session)
        self.inst_repo = InstructionRepository(session)
        self.engine = InstructionEngine(llm_client, session=session)
        self.intelligence = IntelligenceEngine(llm_client, session=session)

    def generate(
        self,
        count: int,
        seed_ids: Optional[List[int]] = None,
        domains: Optional[List[str]] = None,
    ) -> InstructionGenerateResponse:
        # Load seeds
        if seed_ids:
            seed_records = [self.seed_repo.get_by_id(i) for i in seed_ids if self.seed_repo.get_by_id(i)]
        else:
            seed_records = self.seed_repo.get_all()

        seeds = [
            SeedTask(
                id=r.task_key,
                instruction=r.instruction,
                domain=r.domain,
                category=TaskCategory(r.category),
                difficulty=r.difficulty,
            )
            for r in seed_records
        ]

        if domains:
            instructions = self.engine.generate_domain_expanded(seeds, domains, per_domain=max(1, count // len(domains)))
        else:
            instructions = self.engine.generate(seeds, count)

        # Re-query DB to get IDs
        db_records = self.inst_repo.get_all_instructions(status="pending")
        recent = db_records[-len(instructions):]

        responses = [
            InstructionResponse(
                id=r.id,
                instruction=r.instruction,
                domain=r.domain,
                difficulty=r.difficulty,
                status=r.status,
                created_at=r.created_at.isoformat(),
            )
            for r in recent
        ]
        return InstructionGenerateResponse(
            total_generated=len(responses),
            instructions=responses,
            message=f"Generated {len(responses)} instruction candidates.",
        )

    def analyze(self, instruction_ids: Optional[List[int]] = None) -> InstructionAnalyzeResponse:
        if instruction_ids:
            records = [self.inst_repo.get_instruction(i) for i in instruction_ids if self.inst_repo.get_instruction(i)]
        else:
            records = self.inst_repo.get_all_instructions(status="pending")

        results = []
        for record in records:
            inst = GeneratedInstruction(
                id=record.id,
                instruction=record.instruction,
                domain=record.domain,
                difficulty=record.difficulty,
                status=record.status,
            )
            meta = self.intelligence.analyze(inst)
            results.append(InstructionMetadataResponse(
                instruction_id=record.id,
                task_type=meta.task_type,
                category=meta.category.value,
                domain=meta.domain,
                subdomain=meta.subdomain,
                difficulty=meta.difficulty.value,
                reasoning_level=meta.reasoning_level.value,
                expected_output_type=meta.expected_output_type,
                complexity=meta.complexity,
            ))

        return InstructionAnalyzeResponse(
            analyzed_count=len(results),
            results=results,
            message=f"Analyzed {len(results)} instructions.",
        )


# ── Example Service ───────────────────────────────────────────────────────────

class ExampleService:
    def __init__(self, session: Session, llm_client: LLMClient):
        self.session = session
        self.llm = llm_client
        self.inst_repo = InstructionRepository(session)
        self.ex_repo = ExampleRepository(session)
        self.engine = ExampleEngine(llm_client, session=session)

    def generate(self, instruction_ids: Optional[List[int]] = None) -> ExampleGenerateResponse:
        if instruction_ids:
            records = [self.inst_repo.get_instruction(i) for i in instruction_ids if self.inst_repo.get_instruction(i)]
        else:
            records = self.inst_repo.get_all_instructions(status="analyzed")

        generated = []
        for record in records:
            meta_record = self.inst_repo.get_metadata(record.id)
            if not meta_record:
                continue
            inst = GeneratedInstruction(
                id=record.id,
                instruction=record.instruction,
                domain=record.domain,
                difficulty=record.difficulty,
            )
            from aidep.core.models import DifficultyLevel, ReasoningLevel
            meta = InstructionMetadata(
                instruction_id=record.id,
                task_type=meta_record.task_type,
                category=TaskCategory(meta_record.category),
                domain=meta_record.domain,
                subdomain=meta_record.subdomain,
                difficulty=DifficultyLevel(meta_record.difficulty),
                reasoning_level=ReasoningLevel(meta_record.reasoning_level),
                expected_output_type=meta_record.expected_output_type,
                complexity=meta_record.complexity,
            )
            example = self.engine.generate_example(inst, meta)
            generated.append(example)

        responses = []
        for ex in generated:
            db_rec = self.ex_repo.get_example(ex.id) if ex.id else None
            if db_rec:
                responses.append(ExampleResponse(
                    id=db_rec.id,
                    instruction=db_rec.instruction_text,
                    input=db_rec.input or "",
                    output=db_rec.output,
                    constraints=db_rec.constraints_json or [],
                    status=db_rec.status,
                    created_at=db_rec.created_at.isoformat(),
                ))

        return ExampleGenerateResponse(
            total_generated=len(responses),
            examples=responses,
            message=f"Generated {len(responses)} training examples.",
        )


# ── Validation Service ────────────────────────────────────────────────────────

class ValidationService:
    def __init__(self, session: Session, similarity_threshold: float = 0.7):
        self.session = session
        self.ex_repo = ExampleRepository(session)
        self.engine = ValidationEngine(similarity_threshold=similarity_threshold, session=session)

    def validate(
        self,
        example_ids: Optional[List[int]] = None,
        similarity_threshold: float = 0.7,
    ) -> ValidateResponse:
        if example_ids:
            records = [self.ex_repo.get_example(i) for i in example_ids if self.ex_repo.get_example(i)]
        else:
            records = self.ex_repo.get_all_examples(status="pending")

        from aidep.core.models import ApprovalStatus, QualityMetrics
        all_examples = [
            TrainingExample(
                id=r.id,
                instruction=r.instruction_text,
                input=r.input or "",
                output=r.output,
                constraints=r.constraints_json or [],
                quality=QualityMetrics(approval_status=ApprovalStatus.PENDING),
            )
            for r in records
        ]

        results = []
        accepted_so_far = []
        passed = 0
        failed = 0

        for example in all_examples:
            result = self.engine.validate(example, accepted_so_far)
            if result.is_valid:
                accepted_so_far.append(example)
                passed += 1
            else:
                failed += 1
            results.append(ValidationResultResponse(
                example_id=example.id,
                is_valid=result.is_valid,
                reasons=result.reasons,
                duplicates=result.duplicates,
            ))

        return ValidateResponse(
            total_validated=len(results),
            passed_count=passed,
            failed_count=failed,
            results=results,
            message=f"Validated {len(results)} examples. Passed: {passed}, Failed: {failed}.",
        )


# ── Quality Service ───────────────────────────────────────────────────────────

class QualityService:
    def __init__(self, session: Session, quality_threshold: float = 0.65):
        self.session = session
        self.ex_repo = ExampleRepository(session)
        self.inst_repo = InstructionRepository(session)
        self.engine = QualityEngine(quality_threshold=quality_threshold, session=session)

    def score(self, example_ids: Optional[List[int]] = None) -> QualityResponse:
        if example_ids:
            records = [self.ex_repo.get_example(i) for i in example_ids if self.ex_repo.get_example(i)]
        else:
            records = self.ex_repo.get_all_examples(status="approved")

        from aidep.core.models import ApprovalStatus, DifficultyLevel, QualityMetrics, ReasoningLevel
        scored = []
        approved_count = 0
        rejected_count = 0

        for record in records:
            meta_record = None
            if record.instruction_id:
                meta_record = self.inst_repo.get_metadata(record.instruction_id)

            meta = InstructionMetadata(
                task_type=meta_record.task_type if meta_record else "Generation",
                category=TaskCategory(meta_record.category if meta_record else "other"),
                domain=meta_record.domain if meta_record else "General",
                difficulty=DifficultyLevel(meta_record.difficulty if meta_record else "Medium"),
                reasoning_level=ReasoningLevel(meta_record.reasoning_level if meta_record else "Medium"),
                complexity=meta_record.complexity if meta_record else 0.3,
            )

            example = TrainingExample(
                id=record.id,
                instruction=record.instruction_text,
                input=record.input or "",
                output=record.output,
                constraints=record.constraints_json or [],
                task_metadata=meta,
                quality=QualityMetrics(approval_status=ApprovalStatus.PENDING),
            )

            metrics = self.engine.score(example, meta)

            if metrics.approval_status == ApprovalStatus.APPROVED:
                approved_count += 1
            elif metrics.approval_status == ApprovalStatus.REJECTED:
                rejected_count += 1

            scored.append(QualityScoreResponse(
                example_id=record.id,
                semantic_score=metrics.semantic_score,
                factual_score=metrics.factual_score,
                reasoning_score=metrics.reasoning_score,
                diversity_score=metrics.diversity_score,
                consistency_score=metrics.consistency_score,
                confidence_score=metrics.confidence_score,
                toxicity_score=metrics.toxicity_score,
                hallucination_score=metrics.hallucination_score,
                overall_score=metrics.overall_score,
                approval_status=metrics.approval_status.value,
            ))

        avg_score = sum(s.overall_score for s in scored) / max(len(scored), 1)

        return QualityResponse(
            total_scored=len(scored),
            approved_count=approved_count,
            rejected_count=rejected_count,
            avg_overall_score=round(avg_score, 4),
            scores=scored,
            message=f"Scored {len(scored)} examples. Approved: {approved_count}.",
        )


# ── Dataset Service ───────────────────────────────────────────────────────────

class DatasetService:
    def __init__(self, session: Session, output_dir: str = "datasets"):
        self.session = session
        self.ex_repo = ExampleRepository(session)
        self.inst_repo = InstructionRepository(session)
        self.engine = DatasetEngine(output_dir=output_dir, session=session)

    def export(self, req: DatasetExportRequest) -> DatasetExportResponse:
        from aidep.core.models import ApprovalStatus, DifficultyLevel, QualityMetrics, ReasoningLevel

        approved_records = self.ex_repo.get_all_examples(status="approved")

        examples = []
        for record in approved_records:
            quality_record = self.ex_repo.get_quality(record.id)
            meta_record = self.inst_repo.get_metadata(record.instruction_id) if record.instruction_id else None

            meta = InstructionMetadata(
                task_type=meta_record.task_type if meta_record else "Generation",
                category=TaskCategory(meta_record.category if meta_record else "other"),
                domain=meta_record.domain if meta_record else "General",
                subdomain=meta_record.subdomain if meta_record else "General",
                difficulty=DifficultyLevel(meta_record.difficulty if meta_record else "Medium"),
                reasoning_level=ReasoningLevel(meta_record.reasoning_level if meta_record else "Medium"),
                expected_output_type=meta_record.expected_output_type if meta_record else "Text",
                complexity=meta_record.complexity if meta_record else 0.3,
            )

            quality = QualityMetrics(
                semantic_score=quality_record.semantic_score if quality_record else 0.0,
                factual_score=quality_record.factual_score if quality_record else 0.0,
                reasoning_score=quality_record.reasoning_score if quality_record else 0.0,
                diversity_score=quality_record.diversity_score if quality_record else 0.0,
                consistency_score=quality_record.consistency_score if quality_record else 0.0,
                confidence_score=quality_record.confidence_score if quality_record else 0.0,
                toxicity_score=quality_record.toxicity_score if quality_record else 0.0,
                hallucination_score=quality_record.hallucination_score if quality_record else 0.0,
                overall_score=quality_record.overall_score if quality_record else 0.0,
                approval_status=ApprovalStatus.APPROVED,
            )

            examples.append(TrainingExample(
                id=record.id,
                instruction=record.instruction_text,
                input=record.input or "",
                output=record.output,
                constraints=record.constraints_json or [],
                task_metadata=meta,
                quality=quality,
                status="approved",
            ))

        result = self.engine.export_full(examples, version=req.version)

        return DatasetExportResponse(
            dataset_id=result.dataset_id,
            name=result.name,
            version=result.version,
            export_path=result.export_path,
            total_examples=result.total_examples,
            approved_count=result.approved_count,
            rejected_count=result.rejected_count,
            quality_report=result.quality_report,
            message=f"Dataset exported: {result.approved_count} approved examples → {result.export_path}",
        )
