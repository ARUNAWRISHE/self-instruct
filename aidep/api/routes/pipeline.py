"""
Example, Validation, Quality, and Dataset routes.

POST /examples/generate  — Generate training examples
POST /validate           — Run validation
POST /quality            — Score quality
POST /dataset/export     — Export dataset.jsonl
POST /pipeline/run       — Run full end-to-end pipeline
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, status

from aidep.api.deps import (
    get_dataset_service,
    get_example_service,
    get_llm,
    get_pipeline_service,
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


def _run_pipeline_bg(
    count: int,
    version: str,
    seed_file: str,
    llm,
    settings,
    run_id: int,
):
    from aidep.database.base import _SessionLocal
    from aidep.services.pipeline_service import PipelineService
    
    session = _SessionLocal()
    try:
        pipeline_service = PipelineService(session=session, llm_client=llm, settings=settings)
        pipeline_service.run(
            count=count,
            version=version,
            seed_file=seed_file,
            run_id=run_id,
        )
    finally:
        session.close()


@pipeline_router.post(
    "/run",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run the complete AIDEP pipeline end-to-end in the background",
)
def run_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    llm=Depends(get_llm),
    settings=Depends(get_settings),
):
    """
    ISSUE-19: Enqueues pipeline run as a background task and returns immediately.
    """
    from aidep.database.repositories.pipeline_run_repo import PipelineRunRepository
    
    # Pre-create the run to return the ID immediately
    run_repo = PipelineRunRepository(db)
    run_record = run_repo.create(version=request.version)
    run_id = run_record.id

    background_tasks.add_task(
        _run_pipeline_bg,
        count=request.count,
        version=request.version,
        seed_file=request.seed_file or "",
        llm=llm,
        settings=settings,
        run_id=run_id,
    )

    return PipelineRunResponse(
        run_id=run_id,
        message=f"Pipeline run started in the background (run_id={run_id}). Check status via GET /pipeline/status/{run_id}",
    )


@pipeline_router.get(
    "/status/{run_id}",
    response_model=PipelineStatusResponse,
    summary="Check status of a pipeline run",
)
def get_pipeline_status(
    run_id: int,
    db=Depends(get_db),
):
    from aidep.database.repositories.pipeline_run_repo import PipelineRunRepository
    from fastapi import HTTPException
    
    run_repo = PipelineRunRepository(db)
    record = run_repo.get_by_id(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
        
    return PipelineStatusResponse(
        run_id=record.id,
        version=record.version,
        status=record.status,
        started_at=record.started_at.isoformat() if record.started_at else "",
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        duration_seconds=record.duration_seconds,
        seed_count=record.seed_count,
        instruction_count=record.instruction_count,
        accepted_count=record.accepted_count,
        rejected_count=record.rejected_count,
        dataset_path=record.dataset_path,
        error_log=record.error_log or [],
    )


@pipeline_router.get(
    "/runs",
    response_model=List[PipelineStatusResponse],
    summary="List recent pipeline runs",
)
def list_pipeline_runs(
    limit: int = 50,
    db=Depends(get_db),
):
    """ISSUE-20: Fetch recent pipeline runs for UI history."""
    from aidep.database.repositories.pipeline_run_repo import PipelineRunRepository
    
    run_repo = PipelineRunRepository(db)
    records = run_repo.get_all(limit=limit)
    
    return [
        PipelineStatusResponse(
            run_id=record.id,
            version=record.version,
            status=record.status,
            started_at=record.started_at.isoformat() if record.started_at else "",
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
            duration_seconds=record.duration_seconds,
            seed_count=record.seed_count,
            instruction_count=record.instruction_count,
            accepted_count=record.accepted_count,
            rejected_count=record.rejected_count,
            dataset_path=record.dataset_path,
            error_log=record.error_log or [],
        )
        for record in records
    ]

