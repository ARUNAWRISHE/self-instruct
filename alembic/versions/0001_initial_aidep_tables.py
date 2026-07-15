"""Initial AIDEP tables — create all 11 tables.

Revision ID: 0001
Revises: 
Create Date: 2026-07-14

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── seed_tasks ──────────────────────────────────────────────────────────
    op.create_table(
        "seed_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_key", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(255), server_default="General"),
        sa.Column("category", sa.String(100), server_default="other"),
        sa.Column("difficulty", sa.Integer(), server_default="3"),
        sa.Column("source", sa.String(100), server_default="human"),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── prompt_templates ─────────────────────────────────────────────────────
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("prompt_type", sa.String(100), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("version", sa.String(50), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── domains ──────────────────────────────────────────────────────────────
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("domains.id", ondelete="SET NULL"), nullable=True),
    )

    # ── constraints ──────────────────────────────────────────────────────────
    op.create_table(
        "constraints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("constraint_type", sa.String(100), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
    )

    # ── taxonomy ─────────────────────────────────────────────────────────────
    op.create_table(
        "taxonomy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("taxonomy.id", ondelete="SET NULL"), nullable=True),
        sa.Column("level", sa.Integer(), server_default="0"),
    )

    # ── generated_instructions ───────────────────────────────────────────────
    op.create_table(
        "generated_instructions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("seed_id", sa.Integer(), sa.ForeignKey("seed_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain", sa.String(255), server_default="General"),
        sa.Column("difficulty", sa.String(50), server_default="Medium"),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── instruction_metadata ─────────────────────────────────────────────────
    op.create_table(
        "instruction_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instruction_id", sa.Integer(), sa.ForeignKey("generated_instructions.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("task_type", sa.String(100), server_default="Generation"),
        sa.Column("category", sa.String(100), server_default="other"),
        sa.Column("domain", sa.String(255), server_default="General"),
        sa.Column("subdomain", sa.String(255), server_default="General"),
        sa.Column("difficulty", sa.String(50), server_default="Medium"),
        sa.Column("reasoning_level", sa.String(50), server_default="Medium"),
        sa.Column("expected_output_type", sa.String(100), server_default="Text"),
        sa.Column("complexity", sa.Float(), server_default="0.3"),
    )

    # ── training_examples ────────────────────────────────────────────────────
    op.create_table(
        "training_examples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instruction_id", sa.Integer(), sa.ForeignKey("generated_instructions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("instruction_text", sa.Text(), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("constraints_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── validation_results ───────────────────────────────────────────────────
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("example_id", sa.Integer(), sa.ForeignKey("training_examples.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=True),
        sa.Column("duplicates_json", sa.JSON(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── quality_scores ───────────────────────────────────────────────────────
    op.create_table(
        "quality_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("example_id", sa.Integer(), sa.ForeignKey("training_examples.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("semantic_score", sa.Float(), server_default="0.0"),
        sa.Column("factual_score", sa.Float(), server_default="0.0"),
        sa.Column("reasoning_score", sa.Float(), server_default="0.0"),
        sa.Column("diversity_score", sa.Float(), server_default="0.0"),
        sa.Column("consistency_score", sa.Float(), server_default="0.0"),
        sa.Column("confidence_score", sa.Float(), server_default="0.0"),
        sa.Column("toxicity_score", sa.Float(), server_default="0.0"),
        sa.Column("hallucination_score", sa.Float(), server_default="0.0"),
        sa.Column("overall_score", sa.Float(), server_default="0.0"),
        sa.Column("approval_status", sa.String(50), server_default="pending_review"),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── datasets ─────────────────────────────────────────────────────────────
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("export_path", sa.String(500), nullable=True),
        sa.Column("total_examples", sa.Integer(), server_default="0"),
        sa.Column("approved_count", sa.Integer(), server_default="0"),
        sa.Column("rejected_count", sa.Integer(), server_default="0"),
        sa.Column("quality_report_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("datasets")
    op.drop_table("quality_scores")
    op.drop_table("validation_results")
    op.drop_table("training_examples")
    op.drop_table("instruction_metadata")
    op.drop_table("generated_instructions")
    op.drop_table("taxonomy")
    op.drop_table("constraints")
    op.drop_table("domains")
    op.drop_table("prompt_templates")
    op.drop_table("seed_tasks")
