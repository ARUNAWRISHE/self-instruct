"""Add pipeline_runs table — ISSUE-02.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use checkfirst to avoid failure if create_all() already ran during startup
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pipeline_runs" not in inspector.get_table_names():
        op.create_table(
            "pipeline_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("version", sa.String(50), nullable=False, server_default="1.0.0"),
            sa.Column("status", sa.String(50), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("seed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("instruction_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dataset_path", sa.String(500), nullable=True),
            sa.Column("error_log", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
