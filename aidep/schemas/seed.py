"""API request/response schemas for seed endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aidep.core.models import TaskCategory


class SeedTaskCreateRequest(BaseModel):
    """Request body for POST /seed"""

    instruction: str = Field(..., min_length=10, description="Task instruction text")
    input: str = Field(default="", description="Optional input context")
    output: str = Field(default="", description="Expected output (leave empty to auto-generate)")
    domain: str = Field(default="General", description="Knowledge domain")
    category: TaskCategory = Field(default=TaskCategory.OTHER)
    difficulty: int = Field(default=3, ge=1, le=10)
    source: str = Field(default="human")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"json_schema_extra": {"example": {
        "instruction": "Write a Python function to check if a number is prime.",
        "domain": "Software Engineering",
        "category": "coding",
        "difficulty": 4,
    }}}


class SeedTaskBulkCreateRequest(BaseModel):
    """Request body for bulk seed upload."""
    seeds: List[SeedTaskCreateRequest] = Field(..., min_length=1)


class SeedTaskResponse(BaseModel):
    """Response schema for a single seed task."""

    id: int
    task_key: str
    instruction: str
    input: str
    output: str
    domain: str
    category: str
    difficulty: int
    source: str
    created_at: str

    model_config = {"from_attributes": True}


class SeedTaskListResponse(BaseModel):
    total: int
    seeds: List[SeedTaskResponse]


class SeedFileUploadResponse(BaseModel):
    """Response after loading seeds from a JSONL file."""
    loaded_count: int
    file_path: str
    message: str
