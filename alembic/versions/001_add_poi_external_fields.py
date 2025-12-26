"""Add external source fields to POI model.

Revision ID: 001_add_poi_external_fields
Revises:
Create Date: 2024-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_poi_external_fields'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add external source tracking columns to pois table."""
    # Add external source columns
    op.add_column('pois', sa.Column('external_source', sa.String(), nullable=True))
    op.add_column('pois', sa.Column('external_id', sa.String(), nullable=True))

    # Add geolocation columns
    op.add_column('pois', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('pois', sa.Column('lon', sa.Float(), nullable=True))

    # Add price level column
    op.add_column('pois', sa.Column('price_level', sa.Integer(), nullable=True))

    # Add updated_at column
    op.add_column('pois', sa.Column('updated_at', sa.DateTime(), nullable=True))

    # Create indexes for faster lookups
    op.create_index('ix_pois_external_source', 'pois', ['external_source'])
    op.create_index('ix_pois_external_id', 'pois', ['external_id'])

    # Create unique constraint on (external_source, external_id) to prevent duplicates
    # Only for rows where both are not null
    op.create_unique_constraint(
        'uq_pois_external_source_id',
        'pois',
        ['external_source', 'external_id']
    )


def downgrade() -> None:
    """Remove external source tracking columns from pois table."""
    # Drop unique constraint
    op.drop_constraint('uq_pois_external_source_id', 'pois', type_='unique')

    # Drop indexes
    op.drop_index('ix_pois_external_id', 'pois')
    op.drop_index('ix_pois_external_source', 'pois')

    # Drop columns
    op.drop_column('pois', 'updated_at')
    op.drop_column('pois', 'price_level')
    op.drop_column('pois', 'lon')
    op.drop_column('pois', 'lat')
    op.drop_column('pois', 'external_id')
    op.drop_column('pois', 'external_source')
