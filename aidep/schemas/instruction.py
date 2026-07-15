"""API request/response schemas for instruction endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InstructionGenerateRequest(BaseModel):
    """Request body for POST /instructions/generate"""

    count: int = Field(default=10, ge=1, le=200, description="Number of instructions to generate")
    domains: Optional[List[str]] = Field(
        default=None,
        description="Optional list of domains to expand. If provided, generates per-domain instructions.",
    )
    seed_ids: Optional[List[int]] = Field(
        default=None,
        description="Specific seed IDs to use. If None, uses all seeds.",
    )

    model_config = {"json_schema_extra": {"example": {
        "count": 20,
        "domains": ["Software Engineering", "Healthcare", "Finance"],
    }}}


class InstructionAnalyzeRequest(BaseModel):
    """Request body for POST /instructions/analyze"""

    instruction_ids: Optional[List[int]] = Field(
        default=None,
        description="Specific instruction IDs to analyze. If None, analyzes all pending.",
    )


class InstructionResponse(BaseModel):
    """Response schema for a generated instruction."""

    id: int
    instruction: str
    domain: str
    difficulty: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class InstructionGenerateResponse(BaseModel):
    total_generated: int
    instructions: List[InstructionResponse]
    message: str


class InstructionMetadataResponse(BaseModel):
    instruction_id: int
    task_type: str
    category: str
    domain: str
    subdomain: str
    difficulty: str
    reasoning_level: str
    expected_output_type: str
    complexity: float


class InstructionAnalyzeResponse(BaseModel):
    analyzed_count: int
    results: List[InstructionMetadataResponse]
    message: str
