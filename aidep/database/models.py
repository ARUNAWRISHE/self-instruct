"""
SQLAlchemy ORM table definitions for all 11 AIDEP tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidep.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Knowledge Foundation
# ─────────────────────────────────────────────────────────────────────────────


class SeedTaskModel(Base):
    """seed_tasks — stores human-authored seed instructions."""

    __tablename__ = "seed_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[Optional[str]] = mapped_column(Text, default="")
    output: Mapped[Optional[str]] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(255), default="General")
    category: Mapped[str] = mapped_column(String(100), default="other")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    source: Mapped[str] = mapped_column(String(100), default="human")
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # Relationships
    generated_instructions: Mapped[list["GeneratedInstructionModel"]] = relationship(
        back_populates="seed_task"
    )


class PromptTemplateModel(Base):
    """prompt_templates — reusable LLM prompt templates."""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    prompt_type: Mapped[str] = mapped_column(String(100))  # e.g. instruction_generation
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class DomainModel(Base):
    """domains — domain taxonomy entries."""

    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )


class ConstraintModel(Base):
    """constraints — reusable constraint rules."""

    __tablename__ = "constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(100))  # format | tone | length | content
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)


class TaxonomyModel(Base):
    """taxonomy — hierarchical task taxonomy."""

    __tablename__ = "taxonomy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("taxonomy.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Instruction Generation
# ─────────────────────────────────────────────────────────────────────────────


class GeneratedInstructionModel(Base):
    """generated_instructions — machine-generated instruction candidates."""

    __tablename__ = "generated_instructions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    seed_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("seed_tasks.id", ondelete="SET NULL"), nullable=True
    )
    domain: Mapped[str] = mapped_column(String(255), default="General")
    difficulty: Mapped[str] = mapped_column(String(50), default="Medium")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    seed_task: Mapped[Optional[SeedTaskModel]] = relationship(
        back_populates="generated_instructions"
    )
    instruction_metadata: Mapped[Optional["InstructionMetadataModel"]] = relationship(
        back_populates="instruction", uselist=False
    )
    training_examples: Mapped[list["TrainingExampleModel"]] = relationship(
        back_populates="instruction"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Task Intelligence
# ─────────────────────────────────────────────────────────────────────────────


class InstructionMetadataModel(Base):
    """instruction_metadata — task intelligence analysis results."""

    __tablename__ = "instruction_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("generated_instructions.id", ondelete="CASCADE"),
        unique=True,
    )
    task_type: Mapped[str] = mapped_column(String(100), default="Generation")
    category: Mapped[str] = mapped_column(String(100), default="other")
    domain: Mapped[str] = mapped_column(String(255), default="General")
    subdomain: Mapped[str] = mapped_column(String(255), default="General")
    difficulty: Mapped[str] = mapped_column(String(50), default="Medium")
    reasoning_level: Mapped[str] = mapped_column(String(50), default="Medium")
    expected_output_type: Mapped[str] = mapped_column(String(100), default="Text")
    complexity: Mapped[float] = mapped_column(Float, default=0.3)

    # Relationships
    instruction: Mapped[GeneratedInstructionModel] = relationship(
        back_populates="instruction_metadata"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Training Example Generation
# ─────────────────────────────────────────────────────────────────────────────


class TrainingExampleModel(Base):
    """training_examples — generated input/output training pairs."""

    __tablename__ = "training_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("generated_instructions.id", ondelete="SET NULL"),
        nullable=True,
    )
    instruction_text: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[Optional[str]] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    constraints_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    instruction: Mapped[Optional[GeneratedInstructionModel]] = relationship(
        back_populates="training_examples"
    )
    validation_result: Mapped[Optional["ValidationResultModel"]] = relationship(
        back_populates="example", uselist=False
    )
    quality_score: Mapped[Optional["QualityScoreModel"]] = relationship(
        back_populates="example", uselist=False
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Validation
# ─────────────────────────────────────────────────────────────────────────────


class ValidationResultModel(Base):
    """validation_results — stores pass/fail outcome per training example."""

    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    example_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("training_examples.id", ondelete="CASCADE"),
        unique=True,
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reasons_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    duplicates_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    example: Mapped[TrainingExampleModel] = relationship(
        back_populates="validation_result"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 — Quality Scoring
# ─────────────────────────────────────────────────────────────────────────────


class QualityScoreModel(Base):
    """quality_scores — stores per-dimension quality scores."""

    __tablename__ = "quality_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    example_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("training_examples.id", ondelete="CASCADE"),
        unique=True,
    )
    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    factual_score: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning_score: Mapped[float] = mapped_column(Float, default=0.0)
    diversity_score: Mapped[float] = mapped_column(Float, default=0.0)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    toxicity_score: Mapped[float] = mapped_column(Float, default=0.0)
    hallucination_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending_review")
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    example: Mapped[TrainingExampleModel] = relationship(back_populates="quality_score")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 — Dataset Repository
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunModel(Base):
    """pipeline_runs — ISSUE-02: tracks every pipeline execution for audit/monitoring."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    status: Mapped[str] = mapped_column(String(50), default="running")  # running | completed | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    seed_count: Mapped[int] = mapped_column(Integer, default=0)
    instruction_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    dataset_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_log: Mapped[Optional[list]] = mapped_column(JSON, default=list)


class DatasetModel(Base):
    """datasets — metadata records for each exported dataset version."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    export_path: Mapped[Optional[str]] = mapped_column(String(500))
    total_examples: Mapped[int] = mapped_column(Integer, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_report_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
