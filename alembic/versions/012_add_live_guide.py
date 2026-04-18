"""Live Audio Guide — complete DDL for all guide_* tables.

Revision ID: 009_add_live_guide
Revises: 008_add_saved_trips
Create Date: 2026-04-06

Consolidated migration (replaces the original two-file draft: 009 + 010).
Creates all 19 guide_* tables in their final schema state from the start,
so no follow-up ALTER TABLE patches are needed.

Tables created (in FK dependency order):
  1.  guide_cities           — cities index
  2.  guide_zones            — coverage polygons (PostGIS Polygon 4326)
  3.  guide_points           — graph nodes (PostGIS Point 4326)
  4.  guide_edges            — directed pedestrian-graph edges
  5.  guide_knowledge_cards  — raw knowledge collected by City Seeder
  6.  guide_voices           — narrator personas + seed data (8 rows)
  7.  guide_content_blocks   — text + audio per (point × voice × language × detail_level)
  8.  guide_content_jobs     — content pipeline job tracking
  9.  guide_sessions         — active/ended guide sessions
  10. guide_session_gps_log  — full GPS track per session
  11. guide_session_visits   — visited-point log (replaces UUID[] column)
  12. guide_session_qa       — Q&A history per session (replaces JSONB column)
  13. guide_user_preferences — per-user guide defaults
  14. guide_analytics_events — in-house product analytics events
  15. guide_minute_balances  — user minute balance stored in seconds
  16. guide_minute_transactions — balance debit/credit audit log
  17. guide_iap_purchases    — validated IAP receipts (Apple + Google)
  18. guide_packages         — minute package catalog + seed data (3 rows)
  19. guide_seed_jobs        — city seeder job status tracking

PostGIS columns (guide_cities.center, guide_zones.boundary,
guide_points.location, guide_sessions.last_known_location) are created as
TEXT then immediately ALTERed to the proper GEOMETRY type — this is the
pattern used throughout this project to avoid a GeoAlchemy2 dependency in
migrations.

Extensions required: postgis, pgcrypto (both created IF NOT EXISTS).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_add_live_guide"
down_revision: Union[str, None] = "008_add_saved_trips"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ================================================================== #
    # Extensions (idempotent — safe to run even if already present)
    # ================================================================== #
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ================================================================== #
    # 1. guide_cities
    # ================================================================== #
    op.create_table(
        "guide_cities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_local", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=False),
        # Stored as TEXT then converted — see ALTER below
        sa.Column(
            "center",
            sa.Text(),
            nullable=False,
            comment="PostGIS GEOMETRY(Point, 4326)",
        ),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "ALTER TABLE guide_cities "
        "ALTER COLUMN center TYPE GEOMETRY(Point, 4326) "
        "USING ST_GeomFromText(center, 4326)"
    )
    op.execute(
        "CREATE INDEX idx_guide_cities_center ON guide_cities USING GIST(center)"
    )

    # ================================================================== #
    # 2. guide_zones
    # ================================================================== #
    op.create_table(
        "guide_zones",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "city_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_cities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("theme", sa.String(), nullable=True),
        sa.Column(
            "boundary",
            sa.Text(),
            nullable=False,
            comment="PostGIS GEOMETRY(Polygon, 4326)",
        ),
        sa.Column("poi_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_approved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "ALTER TABLE guide_zones "
        "ALTER COLUMN boundary TYPE GEOMETRY(Polygon, 4326) "
        "USING ST_GeomFromText(boundary, 4326)"
    )
    op.execute(
        "CREATE INDEX idx_guide_zones_boundary ON guide_zones USING GIST(boundary)"
    )
    op.create_index("idx_guide_zones_city_id", "guide_zones", ["city_id"])

    # ================================================================== #
    # 3. guide_points
    # ================================================================== #
    op.create_table(
        "guide_points",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_zones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "location",
            sa.Text(),
            nullable=False,
            comment="PostGIS GEOMETRY(Point, 4326)",
        ),
        sa.Column(
            "trigger_radius_m", sa.Integer(), nullable=False, server_default="25"
        ),
        # point_type: 'poi' — significant landmark; 'connector' — intermediate path node
        sa.Column("point_type", sa.String(), nullable=False, server_default="poi"),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("google_place_id", sa.String(), nullable=True),
        sa.Column("osm_node_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "is_approved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "ALTER TABLE guide_points "
        "ALTER COLUMN location TYPE GEOMETRY(Point, 4326) "
        "USING ST_GeomFromText(location, 4326)"
    )
    op.execute(
        "CREATE INDEX idx_guide_points_location ON guide_points USING GIST(location)"
    )
    op.create_index("idx_guide_points_zone_id", "guide_points", ["zone_id"])
    op.create_index(
        "idx_guide_points_type", "guide_points", ["zone_id", "point_type"]
    )
    # Idempotency: prevent duplicate POI / OSM nodes within a zone
    op.create_unique_constraint(
        "uq_guide_points_zone_google",
        "guide_points",
        ["zone_id", "google_place_id"],
    )
    op.create_unique_constraint(
        "uq_guide_points_zone_osm",
        "guide_points",
        ["zone_id", "osm_node_id"],
    )

    # ================================================================== #
    # 4. guide_edges
    # ================================================================== #
    op.create_table(
        "guide_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "from_point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("walk_seconds", sa.Integer(), nullable=False),
        sa.Column("bearing_deg", sa.Float(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.create_unique_constraint(
        "uq_guide_edges_from_to", "guide_edges", ["from_point_id", "to_point_id"]
    )
    op.create_index("idx_guide_edges_from", "guide_edges", ["from_point_id"])
    op.create_index("idx_guide_edges_to", "guide_edges", ["to_point_id"])

    # ================================================================== #
    # 5. guide_knowledge_cards
    # ================================================================== #
    op.create_table(
        "guide_knowledge_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # card_type: 'poi' — main POI card; 'street_context' — for connector nodes
        sa.Column(
            "card_type", sa.String(), nullable=False, server_default="poi"
        ),
        sa.Column("google_place_data", postgresql.JSONB(), nullable=True),
        # street_name populated for street_context cards (connector nodes)
        sa.Column("street_name", sa.String(), nullable=True),
        sa.Column("wikipedia_summary", sa.Text(), nullable=True),
        sa.Column("wikidata_facts", postgresql.JSONB(), nullable=True),
        sa.Column("enriched_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # ================================================================== #
    # 6. guide_voices
    # ================================================================== #
    op.create_table(
        "guide_voices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        # style_group: academic | friendly | dramatic | minimal
        # Column is named style_group (not style) from the start to avoid renaming later.
        sa.Column("style_group", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column("elevenlabs_voice_id", sa.String(), nullable=False),
        sa.Column("preview_audio_url", sa.String(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    # One ElevenLabs voice per (style × language) combination
    op.create_unique_constraint(
        "uq_guide_voices_style_group_lang",
        "guide_voices",
        ["style_group", "language"],
    )

    # Seed: 4 styles × 2 languages = 8 voices
    # elevenlabs_voice_id will be replaced with real IDs before launch
    op.execute("""
        INSERT INTO guide_voices (id, name, style_group, language, elevenlabs_voice_id, is_active)
        VALUES
            (gen_random_uuid(), 'Historian EN',    'academic', 'en', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Historian RU',    'academic', 'ru', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Local Friend EN', 'friendly', 'en', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Local Friend RU', 'friendly', 'ru', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Storyteller EN',  'dramatic', 'en', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Storyteller RU',  'dramatic', 'ru', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Minimalist EN',   'minimal',  'en', 'PLACEHOLDER_VOICE_ID', TRUE),
            (gen_random_uuid(), 'Minimalist RU',   'minimal',  'ru', 'PLACEHOLDER_VOICE_ID', TRUE)
        ON CONFLICT (style_group, language) DO NOTHING
    """)

    # ================================================================== #
    # 7. guide_content_blocks
    # ================================================================== #
    # Stores one row per (point × voice × language × detail_level × content_type × variant).
    # zone_id is denormalized from guide_points.zone_id — populated on insert — so that
    # S3 key construction and zone-level aggregates work without a JOIN.
    # detail_level: 'brief' | 'standard'. Transitions/zone_transition/recap are always 'standard'.
    # generation_status pipeline:
    #   pending → draft → validated → needs_manual_review → reviewed → synthesizing → synthesized → failed
    op.create_table(
        "guide_content_blocks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalized: populated from guide_points.zone_id at insert time
        sa.Column(
            "zone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_zones.id"),
            nullable=False,
        ),
        sa.Column(
            "voice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_voices.id"),
            nullable=False,
        ),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        # detail_level needed to distinguish brief vs standard versions;
        # navigation engine picks block matching session.detail_level (or speed-adjusted)
        sa.Column(
            "detail_level", sa.String(), nullable=False, server_default="standard"
        ),
        # content_type: main | bonus | transition | zone_transition | recap
        sa.Column("content_type", sa.String(), nullable=False),
        # edge_id is set only for transition / zone_transition blocks
        sa.Column(
            "edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_edges.id"),
            nullable=True,
        ),
        sa.Column("variant_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text_script", sa.Text(), nullable=False),
        sa.Column("audio_url", sa.String(), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "generation_status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        # coherence_score: 1–5 from LLM validator (thresholds: transitions ≥ 4.0; others ≥ 3.5)
        sa.Column("coherence_score", sa.Float(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("synthesized_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Lookup index: find the right block for a point given voice/language/detail/type/variant
    op.create_index(
        "idx_guide_content_lookup",
        "guide_content_blocks",
        ["point_id", "voice_id", "language", "detail_level", "content_type", "variant_index"],
    )
    # Edge-based lookup (for transition content); includes detail_level for version selection
    op.create_index(
        "idx_guide_content_edge",
        "guide_content_blocks",
        ["edge_id", "voice_id", "language", "detail_level"],
    )
    # Direct zone filter without JOIN guide_points (used by admin API + dashboard aggregates)
    op.create_index("idx_guide_content_zone", "guide_content_blocks", ["zone_id"])
    op.create_index(
        "idx_guide_content_status", "guide_content_blocks", ["generation_status"]
    )

    # Two partial UNIQUE indexes for upsert idempotency (ON CONFLICT DO UPDATE).
    # A single UNIQUE across all columns would not work because PostgreSQL treats
    # NULL != NULL, allowing infinite duplicate rows when edge_id IS NULL.
    # Specify conflict_index name in db.upsert_content_block() calls.
    op.execute(
        "CREATE UNIQUE INDEX idx_guide_content_uq_no_edge "
        "ON guide_content_blocks(point_id, voice_id, language, detail_level, content_type, variant_index) "
        "WHERE edge_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_guide_content_uq_with_edge "
        "ON guide_content_blocks(point_id, voice_id, language, detail_level, content_type, edge_id, variant_index) "
        "WHERE edge_id IS NOT NULL"
    )

    # ================================================================== #
    # 8. guide_content_jobs
    # ================================================================== #
    # Tracks batch runs of the content pipeline (generate_drafts | validate | synthesize).
    # Separate from guide_seed_jobs for granular per-zone content status monitoring.
    op.create_table(
        "guide_content_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_zones.id"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default="running"
        ),
        sa.Column(
            "voice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_voices.id"),
            nullable=True,
        ),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column(
            "progress_json",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Composite index — most queries filter by both zone and status
    op.create_index(
        "idx_guide_content_jobs_zone", "guide_content_jobs", ["zone_id", "status"]
    )

    # ================================================================== #
    # 9. guide_sessions
    # ================================================================== #
    # visited_point_ids (UUID[]) and qa_history (JSONB) are stored in separate
    # normalized tables (guide_session_visits, guide_session_qa) instead of
    # inline columns — avoids row bloat and enables efficient aggregation.
    op.create_table(
        "guide_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "zone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_zones.id"),
            nullable=False,
        ),
        sa.Column(
            "voice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_voices.id"),
            nullable=False,
        ),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column(
            "detail_level", sa.String(), nullable=False, server_default="standard"
        ),
        # status: active | paused | ended
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "total_seconds_billed", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # PostGIS point — stored as TEXT then ALTERed below
        sa.Column(
            "last_known_location",
            sa.Text(),
            nullable=True,
            comment="PostGIS GEOMETRY(Point, 4326)",
        ),
        # exit_reason: manual | balance_empty | out_of_zone
        sa.Column("exit_reason", sa.String(), nullable=True),
        # Post-session feedback fields
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
    )
    op.execute(
        "ALTER TABLE guide_sessions "
        "ALTER COLUMN last_known_location TYPE GEOMETRY(Point, 4326) "
        "USING CASE WHEN last_known_location IS NULL THEN NULL "
        "ELSE ST_GeomFromText(last_known_location, 4326) END"
    )
    # CHECK constraint: rating must be 1–5 (NULL is allowed — means no rating yet)
    op.create_check_constraint(
        "ck_guide_sessions_rating",
        "guide_sessions",
        "rating BETWEEN 1 AND 5",
    )
    op.create_index("idx_guide_sessions_user_id", "guide_sessions", ["user_id"])
    # Partial index: only non-ended sessions matter for active-session queries
    op.execute(
        "CREATE INDEX idx_guide_sessions_status ON guide_sessions(status) "
        "WHERE status != 'ended'"
    )

    # ================================================================== #
    # 10. guide_session_gps_log
    # ================================================================== #
    # Stores every GPS sample (≈ 1/5 s) for post-session analytics
    # (heat maps, trigger-radius optimisation). DESC index enables fast
    # "latest N samples" queries used by the navigation engine.
    op.create_table(
        "guide_session_gps_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "CREATE INDEX idx_guide_gps_log_session "
        "ON guide_session_gps_log(session_id, recorded_at DESC)"
    )

    # ================================================================== #
    # 11. guide_session_visits
    # ================================================================== #
    # Replaces the visited_point_ids UUID[] column in the original design.
    # Separate table enables: content-type analytics, per-point popularity counts,
    # exact visit timestamps, and avoids array length limits.
    op.create_table(
        "guide_session_visits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id"),
            nullable=False,
        ),
        # content_type_played: main | bonus | skipped | zone_transition
        sa.Column(
            "content_type_played",
            sa.String(),
            nullable=False,
            server_default="main",
        ),
        sa.Column(
            "visited_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Composite index: deduplication check "has (session, point) been visited?"
    op.create_index(
        "idx_guide_visits_session",
        "guide_session_visits",
        ["session_id", "point_id"],
    )
    # Single-column index on point_id for point-popularity analytics
    op.create_index("idx_guide_visits_point", "guide_session_visits", ["point_id"])

    # ================================================================== #
    # 12. guide_session_qa
    # ================================================================== #
    # Replaces the qa_history JSONB column in the original design.
    # Structured rows enable: question count per session, full-text search,
    # easy "last N Q&A pairs for LLM context" via ORDER BY created_at DESC LIMIT N.
    op.create_table(
        "guide_session_qa",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # point_id is nullable — user may ask a question away from any POI
        sa.Column(
            "point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_points.id"),
            nullable=True,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("audio_question_url", sa.String(), nullable=True),
        sa.Column("audio_answer_url", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # DESC on created_at: supports "last N pairs for LLM context" without full scan
    op.execute(
        "CREATE INDEX idx_guide_qa_session "
        "ON guide_session_qa(session_id, created_at DESC)"
    )

    # ================================================================== #
    # 13. guide_user_preferences
    # ================================================================== #
    # Stores defaults for new sessions. If voice_id/language/detail_level are
    # omitted in POST /sessions, these values are used. Updated after each session.
    op.create_table(
        "guide_user_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "preferred_voice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_voices.id"),
            nullable=True,
        ),
        sa.Column(
            "preferred_language",
            sa.String(),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "preferred_detail_level",
            sa.String(),
            nullable=False,
            server_default="standard",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ================================================================== #
    # 14. guide_analytics_events
    # ================================================================== #
    # In-house product analytics (duplicates key events alongside Mixpanel/Amplitude).
    # event_type examples: session_started | point_visited | question_asked |
    #   session_ended | purchase_completed | zone_entered | balance_low | balance_empty
    op.create_table(
        "guide_analytics_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_sessions.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "event_data",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Supports "events of type X per day" aggregations
    op.execute(
        "CREATE INDEX idx_guide_analytics_type_time "
        "ON guide_analytics_events(event_type, created_at DESC)"
    )
    # Session-level filtering (e.g. "all events for session Y")
    op.create_index(
        "idx_guide_analytics_session", "guide_analytics_events", ["session_id"]
    )

    # ================================================================== #
    # 15. guide_minute_balances
    # ================================================================== #
    # Balance stored in seconds (not minutes) for sub-minute billing precision.
    # trial_seconds_* tracked separately to enforce trial-first debit order.
    op.create_table(
        "guide_minute_balances",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "seconds_remaining", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "trial_seconds_granted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "trial_seconds_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ================================================================== #
    # 16. guide_iap_purchases  (before guide_minute_transactions — FK target)
    # ================================================================== #
    # Server-side validated IAP receipts. UNIQUE on transaction_id is the
    # primary fraud guard against double-crediting a single purchase.
    op.create_table(
        "guide_iap_purchases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("original_transaction_id", sa.String(), nullable=True),
        sa.Column("minutes_purchased", sa.Integer(), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=True),
        sa.Column(
            "validated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # status: valid | revoked | refunded
        sa.Column("status", sa.String(), nullable=False, server_default="valid"),
    )
    op.create_unique_constraint(
        "uq_guide_iap_transaction_id", "guide_iap_purchases", ["transaction_id"]
    )
    op.create_index("idx_guide_iap_user_id", "guide_iap_purchases", ["user_id"])

    # ================================================================== #
    # 17. guide_minute_transactions
    # ================================================================== #
    # Immutable audit log for every balance change.
    # transaction_type: purchase | trial | debit | refund
    # seconds_delta: positive = credit, negative = debit
    op.create_table(
        "guide_minute_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_sessions.id"),
            nullable=True,
        ),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("seconds_delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.String(), nullable=True),
        sa.Column(
            "iap_purchase_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_guide_transactions_user_id",
        "guide_minute_transactions",
        ["user_id"],
    )
    op.create_index(
        "idx_guide_transactions_session",
        "guide_minute_transactions",
        ["session_id"],
    )

    # ================================================================== #
    # 18. guide_packages
    # ================================================================== #
    op.create_table(
        "guide_packages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=False),
        sa.Column("apple_product_id", sa.String(), nullable=False),
        sa.Column("google_product_id", sa.String(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )

    # Seed: initial package catalog
    op.execute("""
        INSERT INTO guide_packages (id, minutes, price_usd, apple_product_id, google_product_id)
        VALUES
            ('guide_30min',  30,  4.99, 'com.locally.guide.minutes30',  'guide_30min'),
            ('guide_60min',  60,  7.99, 'com.locally.guide.minutes60',  'guide_60min'),
            ('guide_120min', 120, 12.99, 'com.locally.guide.minutes120', 'guide_120min')
        ON CONFLICT (id) DO NOTHING
    """)

    # ================================================================== #
    # 19. guide_seed_jobs
    # ================================================================== #
    # City Seeder job status tracking. One job per city-run; city_id populated
    # once guide_cities row is created during the job.
    # status phases: running | awaiting_zone_approval | placing_points |
    #   building_graph | collecting_knowledge | generating_content | complete | failed
    op.create_table(
        "guide_seed_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("city_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("current_phase", sa.String(), nullable=True),
        sa.Column(
            "city_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("guide_cities.id"),
            nullable=True,
        ),
        sa.Column(
            "progress_json",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Drop in reverse FK-dependency order (19 → 1).
    # PostGIS/pgcrypto extensions are NOT dropped — they may be used by other modules.

    op.drop_table("guide_seed_jobs")

    op.drop_table("guide_packages")

    op.drop_index(
        "idx_guide_transactions_session",
        table_name="guide_minute_transactions",
    )
    op.drop_index(
        "idx_guide_transactions_user_id",
        table_name="guide_minute_transactions",
    )
    op.drop_table("guide_minute_transactions")

    op.drop_index("idx_guide_iap_user_id", table_name="guide_iap_purchases")
    op.drop_constraint(
        "uq_guide_iap_transaction_id", "guide_iap_purchases", type_="unique"
    )
    op.drop_table("guide_iap_purchases")

    op.drop_table("guide_minute_balances")

    op.drop_index("idx_guide_analytics_session", table_name="guide_analytics_events")
    op.execute("DROP INDEX IF EXISTS idx_guide_analytics_type_time")
    op.drop_table("guide_analytics_events")

    op.drop_table("guide_user_preferences")

    op.execute("DROP INDEX IF EXISTS idx_guide_qa_session")
    op.drop_table("guide_session_qa")

    op.drop_index("idx_guide_visits_point", table_name="guide_session_visits")
    op.drop_index("idx_guide_visits_session", table_name="guide_session_visits")
    op.drop_table("guide_session_visits")

    op.execute("DROP INDEX IF EXISTS idx_guide_gps_log_session")
    op.drop_table("guide_session_gps_log")

    op.execute("DROP INDEX IF EXISTS idx_guide_sessions_status")
    op.drop_constraint(
        "ck_guide_sessions_rating", "guide_sessions", type_="check"
    )
    op.drop_index("idx_guide_sessions_user_id", table_name="guide_sessions")
    op.drop_table("guide_sessions")

    op.drop_index("idx_guide_content_jobs_zone", table_name="guide_content_jobs")
    op.drop_table("guide_content_jobs")

    op.execute("DROP INDEX IF EXISTS idx_guide_content_uq_with_edge")
    op.execute("DROP INDEX IF EXISTS idx_guide_content_uq_no_edge")
    op.drop_index("idx_guide_content_status", table_name="guide_content_blocks")
    op.drop_index("idx_guide_content_zone", table_name="guide_content_blocks")
    op.drop_index("idx_guide_content_edge", table_name="guide_content_blocks")
    op.drop_index("idx_guide_content_lookup", table_name="guide_content_blocks")
    op.drop_table("guide_content_blocks")

    op.drop_constraint(
        "uq_guide_voices_style_group_lang", "guide_voices", type_="unique"
    )
    op.drop_table("guide_voices")

    op.drop_table("guide_knowledge_cards")

    op.drop_index("idx_guide_edges_to", table_name="guide_edges")
    op.drop_index("idx_guide_edges_from", table_name="guide_edges")
    op.drop_constraint("uq_guide_edges_from_to", "guide_edges", type_="unique")
    op.drop_table("guide_edges")

    op.drop_constraint("uq_guide_points_zone_osm", "guide_points", type_="unique")
    op.drop_constraint(
        "uq_guide_points_zone_google", "guide_points", type_="unique"
    )
    op.drop_index("idx_guide_points_type", table_name="guide_points")
    op.drop_index("idx_guide_points_zone_id", table_name="guide_points")
    op.execute("DROP INDEX IF EXISTS idx_guide_points_location")
    op.drop_table("guide_points")

    op.drop_index("idx_guide_zones_city_id", table_name="guide_zones")
    op.execute("DROP INDEX IF EXISTS idx_guide_zones_boundary")
    op.drop_table("guide_zones")

    op.execute("DROP INDEX IF EXISTS idx_guide_cities_center")
    op.drop_table("guide_cities")
