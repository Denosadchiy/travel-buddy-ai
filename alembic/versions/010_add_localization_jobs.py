"""Add localization_jobs table for async translation queue.

Revision ID: 010_add_localization_jobs
Revises: 009_add_localization_entries
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "010_add_localization_jobs"
down_revision: Union[str, None] = "009_add_localization_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create localization_jobs table."""
    op.create_table(
        "localization_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("translation_key", sa.String(), nullable=False),
        sa.Column("target_locale", sa.String(length=32), nullable=False),
        sa.Column("source_locale", sa.String(length=16), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_unique_constraint(
        "uq_localization_jobs_key_locale_hash",
        "localization_jobs",
        ["translation_key", "target_locale", "source_hash"],
    )
    op.create_index(
        "ix_localization_jobs_status",
        "localization_jobs",
        ["status"],
    )
    op.create_index(
        "ix_localization_jobs_next_attempt_at",
        "localization_jobs",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_localization_jobs_target_locale",
        "localization_jobs",
        ["target_locale"],
    )
    op.create_index(
        "ix_localization_jobs_translation_key",
        "localization_jobs",
        ["translation_key"],
    )


def downgrade() -> None:
    """Drop localization_jobs table."""
    op.drop_index("ix_localization_jobs_translation_key", table_name="localization_jobs")
    op.drop_index("ix_localization_jobs_target_locale", table_name="localization_jobs")
    op.drop_index("ix_localization_jobs_next_attempt_at", table_name="localization_jobs")
    op.drop_index("ix_localization_jobs_status", table_name="localization_jobs")
    op.drop_constraint(
        "uq_localization_jobs_key_locale_hash",
        "localization_jobs",
        type_="unique",
    )
    op.drop_table("localization_jobs")

