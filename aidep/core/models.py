"""
Pydantic domain models (data-layer schemas, not ORM models).
These are the canonical data shapes used across all engines and services.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────


class TaskCategory(str, Enum):
    GENERATION = "generation"
    CLASSIFICATION = "classification"
    REASONING = "reasoning"
    CODING = "coding"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    PLANNING = "planning"
    DIALOGUE = "dialogue"
    OTHER = "other"


class DifficultyLevel(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    EXPERT = "Expert"


class ReasoningLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    EXPERT = "Expert"


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending_review"


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Foundation Models
# ─────────────────────────────────────────────────────────────────────────────


class SeedTask(BaseModel):
    """A single human-authored seed task loaded into the Knowledge Repository."""

    id: str = Field(..., description="Unique identifier")
    instruction: str = Field(..., description="Task instruction text")
    input: str = Field(default="", description="Optional input context")
    output: str = Field(default="", description="Expected output")
    domain: str = Field(default="General", description="Knowledge domain")
    category: TaskCategory = Field(default=TaskCategory.OTHER)
    difficulty: int = Field(default=3, ge=1, le=10)
    source: str = Field(default="human", description="human | synthetic")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromptTemplate(BaseModel):
    """A reusable prompt stored in the Prompt Library."""

    id: Optional[int] = None
    name: str
    prompt_type: str  # instruction_generation | task_analysis | example_generation | validation
    template_text: str
    version: str = "1.0"


class Domain(BaseModel):
    """A domain entry in the Domain Library."""

    id: Optional[int] = None
    name: str
    description: str = ""
    parent_id: Optional[int] = None


class Constraint(BaseModel):
    """A constraint rule in the Constraint Library."""

    id: Optional[int] = None
    name: str
    constraint_type: str  # format | tone | length | content
    rule_text: str


class TaxonomyNode(BaseModel):
    """A taxonomy classification node."""

    id: Optional[int] = None
    name: str
    parent_id: Optional[int] = None
    level: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Instruction Pool Models
# ─────────────────────────────────────────────────────────────────────────────


class GeneratedInstruction(BaseModel):
    """A machine-generated instruction candidate."""

    id: Optional[int] = None
    instruction: str
    seed_id: Optional[str] = None
    domain: str = "General"
    difficulty: str = "Medium"
    status: str = "pending"  # pending | analyzed | accepted | rejected
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InstructionMetadata(BaseModel):
    """Task Intelligence analysis result for an instruction."""

    instruction_id: Optional[int] = None
    task_type: str = "Generation"
    category: TaskCategory = TaskCategory.OTHER
    domain: str = "General"
    subdomain: str = "General"
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    reasoning_level: ReasoningLevel = ReasoningLevel.MEDIUM
    expected_output_type: str = "Text"
    complexity: float = Field(default=0.3, ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Training Example Models
# ─────────────────────────────────────────────────────────────────────────────


class QualityMetrics(BaseModel):
    """Quality scores for a training example."""

    semantic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    factual_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_score: float = Field(default=0.0, ge=0.0, le=1.0)
    diversity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    toxicity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    hallucination_score: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING


class ValidationResult(BaseModel):
    """Output of the Validation Engine for a single training example."""

    example_id: Optional[int] = None
    is_valid: bool
    reasons: List[str] = Field(default_factory=list)
    duplicates: List[str] = Field(default_factory=list)


class TrainingExample(BaseModel):
    """
    A complete, ready-to-validate training example.
    This is the canonical unit of data that flows through Validation → Quality → Dataset.
    """

    id: Optional[int] = None
    instruction_id: Optional[int] = None
    instruction: str
    input: str = ""
    output: str
    context: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    task_metadata: InstructionMetadata = Field(default_factory=InstructionMetadata)
    quality: QualityMetrics = Field(default_factory=QualityMetrics)
    status: str = "pending"  # pending | approved | rejected


# ─────────────────────────────────────────────────────────────────────────────
# Dataset Export Models
# ─────────────────────────────────────────────────────────────────────────────


class DatasetRecord(BaseModel):
    """
    Final JSONL export record — the canonical AIDEP output format.
    Compatible with OpenAI fine-tuning and other alignment workflows.
    """

    sample_id: str
    instruction: str
    input: str = ""
    output: str
    context: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    task: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)


class DatasetExportResult(BaseModel):
    """Result returned after a dataset export operation."""

    dataset_id: int
    name: str
    version: str
    export_path: str
    total_examples: int
    approved_count: int
    rejected_count: int
    quality_report: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Models
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResult(BaseModel):
    """Summary result of a full pipeline run."""

    total_candidates: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    total_dataset_size: int = 0
    export_path: str = ""
    quality_report: Dict[str, Any] = Field(default_factory=dict)
    weaknesses: List[str] = Field(default_factory=list)
