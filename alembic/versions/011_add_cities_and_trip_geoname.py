"""Add cities catalog and trip city geoname_id.

Revision ID: 011_add_cities_and_trip_geoname
Revises: 010_add_localization_jobs
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "011_add_cities_and_trip_geoname"
down_revision: Union[str, None] = "010_add_localization_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cities table + indexes and add trips.city_geoname_id."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    alternate_names_type = (
        postgresql.ARRAY(sa.Text()) if dialect == "postgresql" else sa.JSON()
    )

    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("geoname_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_ascii", sa.Text(), nullable=False),
        sa.Column("alternate_names", alternate_names_type, nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("country_name", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timezone", sa.Text(), nullable=True),
    )

    op.create_index("ix_cities_geoname_id", "cities", ["geoname_id"], unique=True)
    if dialect == "postgresql":
        op.execute("CREATE INDEX idx_cities_population ON cities (population DESC)")
    else:
        op.create_index("idx_cities_population", "cities", ["population"])

    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX idx_cities_name_ascii_trgm "
            "ON cities USING GIN (name_ascii gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX idx_cities_alt_names_trgm "
            "ON cities USING GIN ((array_to_string(alternate_names, ',')) gin_trgm_ops)"
        )
    else:
        op.create_index("idx_cities_name_ascii", "cities", ["name_ascii"])

    op.add_column("trips", sa.Column("city_geoname_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_trips_city_geoname_id",
        "trips",
        ["city_geoname_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop cities table and remove trips.city_geoname_id."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_trips_city_geoname_id", table_name="trips")
    op.drop_column("trips", "city_geoname_id")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_cities_alt_names_trgm")
        op.execute("DROP INDEX IF EXISTS idx_cities_name_ascii_trgm")
    else:
        op.drop_index("idx_cities_name_ascii", table_name="cities")

    op.drop_index("idx_cities_population", table_name="cities")
    op.drop_index("ix_cities_geoname_id", table_name="cities")
    op.drop_table("cities")
