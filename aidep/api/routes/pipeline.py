"""
Example, Validation, Quality, and Dataset routes.

POST /examples/generate  — Generate training examples
POST /validate           — Run validation
POST /quality            — Score quality
POST /dataset/export     — Export dataset.jsonl
POST /pipeline/run       — Run full end-to-end pipeline
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status

from aidep.api.deps import (
    get_dataset_service,
    get_example_service,
    get_llm,
    get_quality_service,
    get_settings,
    get_validation_service,
    get_db,
)
from aidep.schemas.dataset import (
    DatasetExportRequest,
    DatasetExportResponse,
    ExampleGenerateRequest,
    ExampleGenerateResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    QualityRequest,
    QualityResponse,
    ValidateRequest,
    ValidateResponse,
)
from aidep.services.pipeline_services import (
    DatasetService,
    ExampleService,
    QualityService,
    ValidationService,
)

# ── Example generation ────────────────────────────────────────────────────────
examples_router = APIRouter(prefix="/examples", tags=["Example Engine"])

@examples_router.post(
    "/generate",
    response_model=ExampleGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate training examples from analyzed instructions",
)
def generate_examples(
    request: ExampleGenerateRequest,
    service: ExampleService = Depends(get_example_service),
):
    """
    Phase 4 — Training Example Generator.

    For each analyzed instruction, generates:
    - A realistic input (if applicable)
    - A correct, high-quality output
    - Any explicit constraints

    Results are stored in `training_examples` table.
    """
    return service.generate(instruction_ids=request.instruction_ids)


# ── Validation ────────────────────────────────────────────────────────────────
validation_router = APIRouter(prefix="/validate", tags=["Validation Engine"])

@validation_router.post(
    "",
    response_model=ValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate training examples",
)
def validate_examples(
    request: ValidateRequest,
    service: ValidationService = Depends(get_validation_service),
):
    """
    Phase 5 — Validation Engine.

    Each example is checked for:
    - Empty instruction or output
    - Duplicate detection (sentence-transformers → RapidFuzz → ROUGE-L)
    - Semantic similarity against existing approved examples
    - Constraint satisfaction

    Results stored in `validation_results` table.
    Examples that pass get status=approved; failures get status=rejected.
    """
    return service.validate(
        example_ids=request.example_ids,
        similarity_threshold=request.similarity_threshold,
    )


# ── Quality scoring ───────────────────────────────────────────────────────────
quality_router = APIRouter(prefix="/quality", tags=["Quality Engine"])

@quality_router.post(
    "",
    response_model=QualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Score quality of validated examples",
)
def score_quality(
    request: QualityRequest,
    service: QualityService = Depends(get_quality_service),
):
    """
    Phase 6 — Quality Engine.

    Scores each validated example on 8 dimensions:
    semantic, factual, reasoning, diversity, consistency,
    confidence, toxicity, hallucination.

    Final weighted overall_score determines approval_status.
    Results stored in `quality_scores` table.
    """
    return service.score(example_ids=request.example_ids)


# ── Dataset export ────────────────────────────────────────────────────────────
dataset_router = APIRouter(prefix="/dataset", tags=["Dataset Repository"])

@dataset_router.post(
    "/export",
    response_model=DatasetExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export approved examples as dataset.jsonl",
)
def export_dataset(
    request: DatasetExportRequest,
    service: DatasetService = Depends(get_dataset_service),
):
    """
    Phase 7 — Dataset Repository.

    Collects all approved examples and:
    - Exports dataset.jsonl
    - Exports alignment_openai_chat.jsonl (fine-tuning ready)
    - Generates a quality report
    - Stores a dataset record in the `datasets` table
    - Identifies category deficits (continuous improvement signal)
    """
    return service.export(request)


# ── Full pipeline ─────────────────────────────────────────────────────────────
pipeline_router = APIRouter(prefix="/pipeline", tags=["Pipeline Orchestrator"])

@pipeline_router.post(
    "/run",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the complete AIDEP pipeline end-to-end",
)
def run_pipeline(
    request: PipelineRunRequest,
    db=Depends(get_db),
    llm=Depends(get_llm),
    settings=Depends(get_settings),
):
    """
    Runs all 7 AIDEP phases in sequence:

    1. Knowledge Foundation (load seeds)
    2. Instruction Generation
    3. Task Intelligence
    4. Training Example Generation
    5. Validation
    6. Quality Scoring
    7. Dataset Export

    This is the primary end-to-end pipeline endpoint.
    """
    from aidep.orchestrator.pipeline import AIDEPOrchestrator
    from aidep.core.models import SeedTask

    orchestrator = AIDEPOrchestrator(
        llm_client=llm,
        session=db,
        num_instructions=request.count,
        similarity_threshold=settings.validation_similarity_threshold,
        quality_threshold=settings.quality_threshold,
        output_dir=settings.output_dir,
    )

    if request.seed_file:
        orchestrator.load_seeds_from_file(request.seed_file)

    result = orchestrator.run_pipeline(version=request.version)

    return PipelineRunResponse(
        total_candidates=result.total_candidates,
        accepted_count=result.accepted_count,
        rejected_count=result.rejected_count,
        total_dataset_size=result.total_dataset_size,
        export_path=result.export_path,
        weaknesses=result.weaknesses,
        quality_report=result.quality_report,
        message=(
            f"Pipeline complete. {result.accepted_count}/{result.total_candidates} "
            f"examples accepted. Dataset: {result.export_path}"
        ),
    )
