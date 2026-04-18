"""
Admin API for the Live Audio Guide.

All endpoints require JWT authentication + admin role.
See ARCHITECTURE.md §3.2 for the full specification.

Implemented (working):
  POST /api/guide/admin/seed
  GET  /api/guide/admin/seed/{job_id}
  GET  /api/guide/admin/zones
  PUT  /api/guide/admin/zones/{zone_id}/approve
  GET  /api/guide/admin/zones/{zone_id}/points
  PUT  /api/guide/admin/points/{point_id}

Stubs (501 Not Implemented):
  POST /api/guide/admin/content/generate
  POST /api/guide/admin/content/validate
  POST /api/guide/admin/content/synthesize
  GET  /api/guide/admin/content/status
  GET  /api/guide/admin/analytics
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import UserModel
from src.guide.api.dependencies import get_current_user_admin, get_navigation_repo
from src.guide.application.navigation_repository import NavigationRepository
from src.guide.domain.models import (
    GuideSeedJob,
    GuideZone,
    GuidePoint,
    GuideEdge,
)
from src.guide.domain.schemas import (
    ContentBlockReviewView,
    ContentGenerateRequest,
    ContentGenerateResponse,
    ContentReviewActionRequest,
    ContentReviewActionResponse,
    ContentReviewListResponse,
    ContentStatusResponse,
    ContentSynthesizeRequest,
    ContentSynthesizeResponse,
    ContentValidateRequest,
    ContentValidateResponse,
    PointAdminView,
    PointsAdminListResponse,
    PointUpdateRequest,
    SeedRequest,
    SeedResponse,
    SeedJobStatusResponse,
    SeedJobProgress,
    ZoneAdminView,
    ZoneApproveRequest,
    ZoneApproveResponse,
    ZonesAdminListResponse,
)
from src.infrastructure.database import get_db

guide_admin_router = APIRouter(prefix="/guide/admin", tags=["guide-admin"])


# ---------------------------------------------------------------------------
# City Seeder
# ---------------------------------------------------------------------------

@guide_admin_router.post("/seed", response_model=SeedResponse, status_code=202)
async def trigger_seed(
    request: SeedRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger City Seeder for a new city.
    Runs the seeder pipeline in background; returns job_id immediately.
    """
    from src.guide.application.seeder.orchestrator import SeederOrchestrator
    from src.guide.application.seeder.repository import SeederRepository
    from src.infrastructure.database import AsyncSessionLocal

    # Create job record
    seed_job = GuideSeedJob(
        city_name=request.city_name,
        status="running",
    )
    db.add(seed_job)
    await db.commit()
    await db.refresh(seed_job)
    job_id = seed_job.id

    # Fire-and-forget background seeder
    async def _run_seeder():
        async with AsyncSessionLocal() as bg_db:
            repo = SeederRepository(bg_db)
            orchestrator = SeederOrchestrator(repo)
            await orchestrator.seed(
                city_name=request.city_name,
                country=request.country,
                seed_job_id=job_id,
            )

    asyncio.create_task(_run_seeder())

    return SeedResponse(job_id=job_id, status="running")


@guide_admin_router.get("/seed/{job_id}", response_model=SeedJobStatusResponse)
async def get_seed_job(
    job_id: uuid.UUID,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return the current status of a City Seeder job."""
    job = await db.get(GuideSeedJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Seed job not found")

    progress_raw = job.progress_json or {}
    progress = SeedJobProgress(
        zones_found=progress_raw.get("zones_found", 0),
        points_placed=progress_raw.get("points_placed", 0),
        edges_built=progress_raw.get("edges_built", 0),
        cards_collected=progress_raw.get("cards_collected", 0),
        blocks_generated=progress_raw.get("blocks_generated", 0),
        blocks_synthesized=progress_raw.get("blocks_synthesized", 0),
    )

    return SeedJobStatusResponse(
        job_id=job.id,
        city_name=job.city_name,
        status=job.status,
        current_phase=job.current_phase,
        progress=progress,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# ---------------------------------------------------------------------------
# Zone management
# ---------------------------------------------------------------------------

@guide_admin_router.get("/zones", response_model=ZonesAdminListResponse)
async def list_zones(
    city_id: Optional[uuid.UUID] = Query(None),
    filter_status: Optional[str] = Query(None, description="pending_approval | approved | active"),
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """List guide zones with optional city and status filters."""
    from src.guide.domain.models import GuideCity
    query = select(GuideZone)
    if city_id is not None:
        query = query.where(GuideZone.city_id == city_id)
    if filter_status == "pending_approval":
        query = query.where(GuideZone.is_approved == False)
    elif filter_status == "approved":
        query = query.where(GuideZone.is_approved == True)
    elif filter_status == "active":
        query = query.where(GuideZone.is_active == True)

    result = await db.execute(query)
    zones = result.scalars().all()

    zone_views = []
    for z in zones:
        # Convert PostGIS boundary to GeoJSON dict
        try:
            shape = to_shape(z.boundary)
            import json as _json
            from shapely.geometry import mapping
            boundary_geojson = mapping(shape)
        except Exception:
            boundary_geojson = {}

        # Get city name from zone's city relationship
        city_result = await db.execute(
            select(GuideCity).where(GuideCity.id == z.city_id)
        )
        city = city_result.scalar_one_or_none()
        city_name = city.name if city else "Unknown"

        zone_views.append(ZoneAdminView(
            id=z.id,
            city_id=z.city_id,
            name=z.name,
            description=z.description,
            theme=z.theme,
            boundary_geojson=boundary_geojson,
            poi_count=z.poi_count,
            point_count=z.point_count,
            is_approved=z.is_approved,
            is_active=z.is_active,
            approved_at=z.approved_at,
            created_at=z.created_at,
        ))

    return ZonesAdminListResponse(zones=zone_views, total=len(zone_views))


@guide_admin_router.put("/zones/{zone_id}/approve", response_model=ZoneApproveResponse)
async def approve_zone(
    zone_id: uuid.UUID,
    request: ZoneApproveRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a zone. Optionally adjust its boundary polygon."""
    from datetime import datetime, timezone
    zone = await db.get(GuideZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    zone.is_approved = request.approved
    if request.approved:
        zone.approved_at = datetime.now(timezone.utc)
    if request.adjusted_boundary_geojson:
        from shapely.geometry import shape
        import json as _json
        shp = shape(request.adjusted_boundary_geojson)
        zone.boundary = WKTElement(shp.wkt, srid=4326)

    await db.commit()
    await db.refresh(zone)

    return ZoneApproveResponse(
        zone_id=zone.id,
        is_approved=zone.is_approved,
        approved_at=zone.approved_at,
    )


# ---------------------------------------------------------------------------
# Point management
# ---------------------------------------------------------------------------

@guide_admin_router.get("/zones/{zone_id}/points", response_model=PointsAdminListResponse)
async def list_zone_points(
    zone_id: uuid.UUID,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all points in a zone with basic content status info."""
    result = await db.execute(
        select(GuidePoint).where(GuidePoint.zone_id == zone_id)
    )
    points = result.scalars().all()

    # Count edges per point
    edge_result = await db.execute(
        select(GuideEdge).join(GuidePoint, GuideEdge.from_point_id == GuidePoint.id)
        .where(GuidePoint.zone_id == zone_id)
    )
    all_edges = edge_result.scalars().all()
    neighbor_count_map: dict[uuid.UUID, int] = {}
    for e in all_edges:
        neighbor_count_map[e.from_point_id] = neighbor_count_map.get(e.from_point_id, 0) + 1

    point_views = []
    for p in points:
        try:
            shape = to_shape(p.location)
            lat, lng = shape.y, shape.x
        except Exception:
            lat, lng = 0.0, 0.0

        point_views.append(PointAdminView(
            id=p.id,
            zone_id=p.zone_id,
            name=p.name,
            point_type=p.point_type,
            lat=lat,
            lng=lng,
            trigger_radius_m=p.trigger_radius_m,
            google_place_id=p.google_place_id,
            osm_node_id=p.osm_node_id,
            is_approved=p.is_approved,
            is_active=p.is_active,
            neighbor_count=neighbor_count_map.get(p.id, 0),
            content_status=None,
        ))

    return PointsAdminListResponse(points=point_views, total=len(point_views))


@guide_admin_router.put("/points/{point_id}", response_model=PointAdminView)
async def update_point(
    point_id: uuid.UUID,
    request: PointUpdateRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a guide point's location, trigger radius, or approval status."""
    point = await db.get(GuidePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="Point not found")

    if request.lat is not None and request.lng is not None:
        point.location = WKTElement(
            f"SRID=4326;POINT({request.lng} {request.lat})", srid=4326
        )
    if request.trigger_radius_m is not None:
        point.trigger_radius_m = request.trigger_radius_m
    if request.is_active is not None:
        point.is_active = request.is_active
    if request.is_approved is not None:
        point.is_approved = request.is_approved

    await db.commit()
    await db.refresh(point)

    try:
        shape = to_shape(point.location)
        lat, lng = shape.y, shape.x
    except Exception:
        lat, lng = 0.0, 0.0

    return PointAdminView(
        id=point.id,
        zone_id=point.zone_id,
        name=point.name,
        point_type=point.point_type,
        lat=lat,
        lng=lng,
        trigger_radius_m=point.trigger_radius_m,
        google_place_id=point.google_place_id,
        osm_node_id=point.osm_node_id,
        is_approved=point.is_approved,
        is_active=point.is_active,
        neighbor_count=0,
        content_status=None,
    )


# ---------------------------------------------------------------------------
# Content Pipeline — Stage 1: Draft generation
# ---------------------------------------------------------------------------

@guide_admin_router.post("/content/generate", response_model=ContentGenerateResponse, status_code=202)
async def trigger_content_generate(
    request: ContentGenerateRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger batch LLM draft generation for a zone. Runs in background; returns job_id immediately.
    """
    from src.guide.application.content_pipeline.draft_generator import DraftGenerator
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.infrastructure.database import AsyncSessionLocal
    from src.infrastructure.llm_client import LLMClient

    repo = ContentPipelineRepository(db)
    llm = LLMClient()
    generator = DraftGenerator(repo=repo, llm_client=llm)

    # Count queued blocks before launching (dry-run for count)
    # Fire-and-forget actual generation in background
    async def _run_generate():
        async with AsyncSessionLocal() as bg_db:
            bg_repo = ContentPipelineRepository(bg_db)
            bg_llm = LLMClient()
            bg_gen = DraftGenerator(repo=bg_repo, llm_client=bg_llm)
            await bg_gen.generate_zone_drafts(
                zone_id=request.zone_id,
                voice_ids=[str(v) for v in request.voice_ids] if request.voice_ids else None,
                force_regenerate=request.force_regenerate,
            )

    # Create job record to return job_id immediately
    repo_for_job = ContentPipelineRepository(db)
    job = await repo_for_job.create_content_job(
        zone_id=request.zone_id,
        job_type="generate_drafts",
    )
    await db.commit()

    asyncio.create_task(_run_generate())

    return ContentGenerateResponse(job_id=job.id, blocks_queued=0)


# ---------------------------------------------------------------------------
# Content Pipeline — Stage 2: Coherence validation
# ---------------------------------------------------------------------------

@guide_admin_router.post("/content/validate", response_model=ContentValidateResponse, status_code=202)
async def trigger_content_validate(
    request: ContentValidateRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger batch LLM coherence validation for draft blocks. Runs in background.
    """
    from src.guide.application.content_pipeline.coherence_validator import CoherenceValidator
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.infrastructure.database import AsyncSessionLocal
    from src.infrastructure.llm_client import LLMClient

    repo = ContentPipelineRepository(db)
    job = await repo.create_content_job(
        zone_id=request.zone_id,
        job_type="validate",
    )
    await db.commit()
    job_id = job.id

    async def _run_validate():
        async with AsyncSessionLocal() as bg_db:
            bg_repo = ContentPipelineRepository(bg_db)
            bg_llm = LLMClient()
            validator = CoherenceValidator(repo=bg_repo, llm_client=bg_llm)
            await validator.validate_zone(
                zone_id=request.zone_id,
                job_id=job_id,
            )

    asyncio.create_task(_run_validate())

    return ContentValidateResponse(job_id=job_id, blocks_queued=0)


# ---------------------------------------------------------------------------
# Content Pipeline — Stage 4: Audio synthesis
# ---------------------------------------------------------------------------

@guide_admin_router.post("/content/synthesize", response_model=ContentSynthesizeResponse, status_code=202)
async def trigger_content_synthesize(
    request: ContentSynthesizeRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger ElevenLabs TTS synthesis for reviewed blocks. Runs in background.
    """
    from src.guide.application.content_pipeline.audio_synthesizer import AudioSynthesizer
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client
    from src.infrastructure.database import AsyncSessionLocal

    repo = ContentPipelineRepository(db)
    job = await repo.create_content_job(
        zone_id=request.zone_id,
        job_type="synthesize",
    )
    await db.commit()
    job_id = job.id

    async def _run_synthesize():
        async with AsyncSessionLocal() as bg_db:
            bg_repo = ContentPipelineRepository(bg_db)
            tts = ElevenLabsClient()
            s3 = GuideS3Client()
            synthesizer = AudioSynthesizer(repo=bg_repo, elevenlabs_client=tts, s3_client=s3)
            await synthesizer.synthesize_zone(
                zone_id=request.zone_id,
                voice_ids=request.voice_ids,
                job_id=job_id,
            )

    asyncio.create_task(_run_synthesize())

    return ContentSynthesizeResponse(job_id=job_id, files_queued=0)


# ---------------------------------------------------------------------------
# Content Pipeline — status
# ---------------------------------------------------------------------------

@guide_admin_router.get("/content/status", response_model=ContentStatusResponse)
async def content_status(
    zone_id: uuid.UUID = Query(...),
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregate content generation status for a zone."""
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository

    repo = ContentPipelineRepository(db)
    data = await repo.get_zone_content_status(zone_id)
    return ContentStatusResponse(**data)


# ---------------------------------------------------------------------------
# Content Pipeline — Stage 3: Manual review
# ---------------------------------------------------------------------------

@guide_admin_router.get("/content/review", response_model=ContentReviewListResponse)
async def get_review_queue(
    zone_id: uuid.UUID = Query(...),
    status: str = Query("needs_manual_review"),
    language: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    voice_id: Optional[uuid.UUID] = Query(None),
    min_score: Optional[float] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated review queue for a zone."""
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.review_service import ReviewService
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

    repo = ContentPipelineRepository(db)
    service = ReviewService(repo=repo, tts=ElevenLabsClient(), s3=GuideS3Client())
    blocks, total = await service.get_review_queue(
        zone_id=zone_id,
        status=status,
        language=language,
        content_type=content_type,
        voice_id=voice_id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return ContentReviewListResponse(
        blocks=[ContentBlockReviewView(**b) for b in blocks],
        total=total,
    )


@guide_admin_router.put("/content/{block_id}/review", response_model=ContentReviewActionResponse)
async def review_block(
    block_id: uuid.UUID,
    request: ContentReviewActionRequest,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve, edit or regenerate a single content block.

    action: "approve" | "edit" | "regenerate"
    For "edit": include new_text in review_notes field.
    For "regenerate": review_notes is used as instruction hint.
    """
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.review_service import ReviewService
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

    repo = ContentPipelineRepository(db)
    service = ReviewService(repo=repo, tts=ElevenLabsClient(), s3=GuideS3Client())
    reviewer = request.reviewed_by or admin.email or str(admin.id)

    if request.action == "approve":
        await service.approve_block(block_id, reviewer=reviewer)
    elif request.action == "edit":
        if not request.review_notes:
            raise HTTPException(status_code=400, detail="review_notes required for edit action (contains new text)")
        await service.edit_block(block_id, new_text=request.review_notes, reviewer=reviewer)
    elif request.action == "regenerate":
        await service.regenerate_block(block_id, instruction=request.review_notes, reviewer=reviewer)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action!r}")

    from src.guide.domain.models import GuideContentBlock
    block = await db.get(GuideContentBlock, block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    return ContentReviewActionResponse(
        block_id=block_id,
        generation_status=block.generation_status,
        reviewed_at=block.reviewed_at,
    )


@guide_admin_router.post("/content/{block_id}/preview-tts")
async def preview_tts(
    block_id: uuid.UUID,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Synthesize a TTS preview for a block and return a presigned S3 URL."""
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.review_service import ReviewService
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

    repo = ContentPipelineRepository(db)
    service = ReviewService(repo=repo, tts=ElevenLabsClient(), s3=GuideS3Client())
    try:
        result = await service.preview_tts(block_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@guide_admin_router.post("/content/batch-approve")
async def batch_approve(
    zone_id: uuid.UUID = Query(...),
    min_score: float = Query(..., ge=0.0, le=5.0),
    language: Optional[str] = Query(None),
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mass-approve all needs_manual_review blocks with coherence_score >= min_score."""
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.review_service import ReviewService
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

    repo = ContentPipelineRepository(db)
    service = ReviewService(repo=repo, tts=ElevenLabsClient(), s3=GuideS3Client())
    result = await service.batch_approve(
        zone_id=zone_id,
        min_score=min_score,
        language=language,
    )
    return result


# ---------------------------------------------------------------------------
# Content Pipeline — job status
# ---------------------------------------------------------------------------

@guide_admin_router.get("/content/jobs")
async def list_content_jobs(
    zone_id: Optional[uuid.UUID] = Query(None),
    job_type: Optional[str] = Query(None, description="generate_drafts | validate | synthesize"),
    job_status: Optional[str] = Query(None, description="running | complete | failed"),
    limit: int = Query(50, ge=1, le=200),
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """List content pipeline jobs with optional filters."""
    from src.guide.domain.models import GuideContentJob

    query = select(GuideContentJob).order_by(GuideContentJob.created_at.desc()).limit(limit)
    if zone_id is not None:
        query = query.where(GuideContentJob.zone_id == zone_id)
    if job_type is not None:
        query = query.where(GuideContentJob.job_type == job_type)
    if job_status is not None:
        query = query.where(GuideContentJob.status == job_status)

    result = await db.execute(query)
    jobs = result.scalars().all()
    return {
        "jobs": [
            {
                "id": j.id,
                "zone_id": j.zone_id,
                "job_type": j.job_type,
                "status": j.status,
                "voice_id": j.voice_id,
                "language": j.language,
                "progress": j.progress_json,
                "error_message": j.error_message,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ],
        "total": len(jobs),
    }


@guide_admin_router.get("/content/jobs/{job_id}")
async def get_content_job(
    job_id: uuid.UUID,
    admin: UserModel = Depends(get_current_user_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return details for a single content pipeline job."""
    from src.guide.domain.models import GuideContentJob

    job = await db.get(GuideContentJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "zone_id": job.zone_id,
        "job_type": job.job_type,
        "status": job.status,
        "voice_id": job.voice_id,
        "language": job.language,
        "progress": job.progress_json,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


@guide_admin_router.get("/analytics")
async def analytics_dashboard(
    admin: UserModel = Depends(get_current_user_admin),
):
    """
    Analytics dashboard — session counts, revenue, top zones.
    TODO: implement with aggregation queries.
    """
    raise HTTPException(status_code=501, detail="Analytics not yet implemented")
