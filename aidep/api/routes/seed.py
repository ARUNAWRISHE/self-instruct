"""
Seed routes — Knowledge Foundation API.

POST /seed        — Upload a single seed task
POST /seed/bulk   — Upload multiple seed tasks
GET  /seed        — List all seed tasks
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from aidep.api.deps import get_seed_service
from aidep.schemas.seed import (
    SeedFileUploadResponse,
    SeedTaskBulkCreateRequest,
    SeedTaskCreateRequest,
    SeedTaskListResponse,
    SeedTaskResponse,
)
from aidep.services.seed_service import SeedService

router = APIRouter(prefix="/seed", tags=["Knowledge — Seed Repository"])


@router.post(
    "",
    response_model=SeedTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single seed task",
)
def create_seed(
    request: SeedTaskCreateRequest,
    service: SeedService = Depends(get_seed_service),
):
    """
    Add a human-authored seed task to the Knowledge Repository.

    Seed tasks are the starting point for all instruction generation.
    Minimum 20–100 seeds are recommended for good coverage.
    """
    return service.create_seed(request)


@router.post(
    "/bulk",
    response_model=list[SeedTaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple seed tasks at once",
)
def create_seeds_bulk(
    request: SeedTaskBulkCreateRequest,
    service: SeedService = Depends(get_seed_service),
):
    """Upload a batch of seed tasks in a single request."""
    return service.create_bulk(request.seeds)


@router.get(
    "",
    response_model=SeedTaskListResponse,
    summary="List all seed tasks in the Knowledge Repository",
)
def list_seeds(service: SeedService = Depends(get_seed_service)):
    """Return all seeds currently stored in the Knowledge Repository."""
    return service.list_seeds()
