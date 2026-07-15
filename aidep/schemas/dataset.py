"""API request/response schemas for example, validation, quality, and dataset endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Example Generation ────────────────────────────────────────────────────────

class ExampleGenerateRequest(BaseModel):
    """Request body for POST /examples/generate"""

    instruction_ids: Optional[List[int]] = Field(
        default=None,
        description="IDs of instructions to generate examples for. If None, uses all analyzed.",
    )


class ExampleResponse(BaseModel):
    id: int
    instruction: str
    input: str
    output: str
    constraints: List[str]
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class ExampleGenerateResponse(BaseModel):
    total_generated: int
    examples: List[ExampleResponse]
    message: str


# ── Validation ────────────────────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    """Request body for POST /validate"""

    example_ids: Optional[List[int]] = Field(
        default=None,
        description="IDs of examples to validate. If None, validates all pending.",
    )
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for duplicate detection.",
    )


class ValidationResultResponse(BaseModel):
    example_id: int
    is_valid: bool
    reasons: List[str]
    duplicates: List[str]


class ValidateResponse(BaseModel):
    total_validated: int
    passed_count: int
    failed_count: int
    results: List[ValidationResultResponse]
    message: str


# ── Quality Scoring ───────────────────────────────────────────────────────────

class QualityRequest(BaseModel):
    """Request body for POST /quality"""

    example_ids: Optional[List[int]] = Field(
        default=None,
        description="IDs of examples to score. If None, scores all validated.",
    )


class QualityScoreResponse(BaseModel):
    example_id: int
    semantic_score: float
    factual_score: float
    reasoning_score: float
    diversity_score: float
    consistency_score: float
    confidence_score: float
    toxicity_score: float
    hallucination_score: float
    overall_score: float
    approval_status: str


class QualityResponse(BaseModel):
    total_scored: int
    approved_count: int
    rejected_count: int
    avg_overall_score: float
    scores: List[QualityScoreResponse]
    message: str


# ── Dataset Export ────────────────────────────────────────────────────────────

class DatasetExportRequest(BaseModel):
    """Request body for POST /dataset/export"""

    version: str = Field(default="1.0.0")
    format_type: str = Field(
        default="openai_chat",
        description="Alignment format: openai_chat | gpt3_finetune | generic",
    )


class DatasetExportResponse(BaseModel):
    dataset_id: int
    name: str
    version: str
    export_path: str
    total_examples: int
    approved_count: int
    rejected_count: int
    quality_report: Dict[str, Any]
    message: str


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    """Request body for POST /pipeline/run — runs all 7 phases end-to-end."""

    version: str = Field(default="1.0.0")
    count: int = Field(default=10, ge=1, le=200)
    seed_file: Optional[str] = Field(
        default=None,
        description="Optional path to a seed .jsonl file to load before running.",
    )


class PipelineRunResponse(BaseModel):
    total_candidates: int
    accepted_count: int
    rejected_count: int
    total_dataset_size: int
    export_path: str
    weaknesses: List[str]
    quality_report: Dict[str, Any]
    message: str
