"""
Instruction routes — Instruction Generation & Intelligence APIs.

POST /instructions/generate  — Generate instruction candidates from seeds
POST /instructions/analyze   — Run Task Intelligence on instruction(s)
GET  /instructions           — List generated instructions
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from aidep.api.deps import get_instruction_service
from aidep.schemas.instruction import (
    InstructionAnalyzeRequest,
    InstructionAnalyzeResponse,
    InstructionGenerateRequest,
    InstructionGenerateResponse,
)
from aidep.services.pipeline_services import InstructionService

router = APIRouter(prefix="/instructions", tags=["Instruction Engine"])


@router.post(
    "/generate",
    response_model=InstructionGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate new instruction candidates from the seed pool",
)
def generate_instructions(
    request: InstructionGenerateRequest,
    service: InstructionService = Depends(get_instruction_service),
):
    """
    Phase 2 — Instruction Generation Engine.

    Reads from the Seed Repository and generates `count` diverse instruction
    candidates using the LLM. Optionally expands per domain.

    Results are stored in `generated_instructions` table with status=pending.
    """
    return service.generate(
        count=request.count,
        seed_ids=request.seed_ids,
        domains=request.domains,
    )


@router.post(
    "/analyze",
    response_model=InstructionAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze instructions with the Task Intelligence Engine",
)
def analyze_instructions(
    request: InstructionAnalyzeRequest,
    service: InstructionService = Depends(get_instruction_service),
):
    """
    Phase 3 — Task Intelligence Engine.

    Classifies each instruction by:
    - Task type (Coding, Reasoning, Planning, etc.)
    - Domain / Subdomain
    - Difficulty (Easy / Medium / Hard / Expert)
    - Reasoning level
    - Expected output format
    - Structural complexity score

    Results are stored in `instruction_metadata` table.
    """
    return service.analyze(instruction_ids=request.instruction_ids)
