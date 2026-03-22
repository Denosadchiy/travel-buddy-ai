"""Add localization_entries table for persistent translation storage.

Revision ID: 009_add_localization_entries
Revises: 008_add_saved_trips
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "009_add_localization_entries"
down_revision: Union[str, None] = "008_add_saved_trips"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create localization_entries table."""
    op.create_table(
        "localization_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("translation_key", sa.String(), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("source_language", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
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
        "uq_localization_entries_key_locale",
        "localization_entries",
        ["translation_key", "locale"],
    )
    op.create_index(
        "ix_localization_entries_translation_key",
        "localization_entries",
        ["translation_key"],
    )
    op.create_index(
        "ix_localization_entries_locale",
        "localization_entries",
        ["locale"],
    )
    op.create_index(
        "ix_localization_entries_status",
        "localization_entries",
        ["status"],
    )
    op.create_index(
        "ix_localization_entries_source_hash",
        "localization_entries",
        ["source_hash"],
    )


def downgrade() -> None:
    """Drop localization_entries table."""
    op.drop_index("ix_localization_entries_source_hash", table_name="localization_entries")
    op.drop_index("ix_localization_entries_status", table_name="localization_entries")
    op.drop_index("ix_localization_entries_locale", table_name="localization_entries")
    op.drop_index("ix_localization_entries_translation_key", table_name="localization_entries")
    op.drop_constraint(
        "uq_localization_entries_key_locale",
        "localization_entries",
        type_="unique",
    )
    op.drop_table("localization_entries")

