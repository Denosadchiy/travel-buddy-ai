"""
Client API for the Live Audio Guide.

All endpoints require JWT authentication (Bearer token).
See ARCHITECTURE.md §3.1 for the full specification.

Implemented:
  GET  /api/guide/coverage
  GET  /api/guide/zones/{zone_id}
  POST /api/guide/sessions
  POST /api/guide/sessions/{session_id}/heartbeat
  POST /api/guide/sessions/{session_id}/pause
  POST /api/guide/sessions/{session_id}/resume
  POST /api/guide/sessions/{session_id}/end
  GET  /api/guide/sessions/{session_id}/summary
  GET  /api/guide/sessions/history
  POST /api/guide/sessions/{session_id}/rate
  GET  /api/guide/navigation/next
  GET  /api/guide/balance      → hardcoded 99999 (billing stub)
  GET  /api/guide/packages     → from guide_packages table

Stubs (501 Not Implemented):
  POST /api/guide/qa/ask
  POST /api/guide/purchases/validate
  POST /api/guide/purchases/refund-webhook
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import UserModel
from src.config import settings
from src.guide.api.dependencies import (
    get_current_user,
    get_navigation_repo,
    get_session_manager,
)
from src.guide.application.navigation_repository import NavigationRepository
from src.guide.application.session_manager import SessionManager
from src.guide.domain.schemas import (
    BalanceResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    Package,
    PackagesResponse,
    PauseResponse,
    ResumeResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionEndRequest,
    SessionRateRequest,
    SessionRateResponse,
    SessionSummary,
    SessionsHistoryResponse,
)

guide_router = APIRouter(prefix="/guide", tags=["guide"])


# ---------------------------------------------------------------------------
# Coverage & Zones
# ---------------------------------------------------------------------------

@guide_router.get("/coverage")
async def get_coverage(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    radius_km: float = Query(5.0, description="Search radius in km"),
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """Return active guide zones near the user via PostGIS ST_DWithin."""
    from sqlalchemy import text as sa_text

    result = await repo._db.execute(sa_text("""
        SELECT z.id, z.name, z.theme, z.poi_count,
               c.name as city_name,
               ST_Distance(
                   z.boundary::geography,
                   ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
               ) AS dist_m,
               ST_Contains(z.boundary, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)) AS is_inside
        FROM guide_zones z
        JOIN guide_cities c ON c.id = z.city_id
        WHERE z.is_active = true
          AND ST_DWithin(
              z.boundary::geography,
              ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
              :radius_m
          )
        ORDER BY dist_m
    """), {"lat": lat, "lng": lng, "radius_m": radius_km * 1000})
    rows = result.fetchall()

    voices = await repo.get_active_voices()
    zones = []
    for r in rows:
        zones.append({
            "id": r.id,
            "name": r.name,
            "theme": r.theme,
            "city_name": r.city_name,
            "poi_count": r.poi_count,
            "distance_m": r.dist_m,
            "is_user_inside": r.is_inside,
            "voice_options": [
                {"id": v.id, "name": v.name, "style_group": v.style_group,
                 "language": v.language, "preview_audio_url": v.preview_audio_url}
                for v in voices
            ],
        })
    return {"zones": zones}


@guide_router.get("/zones/{zone_id}")
async def get_zone_detail(
    zone_id: uuid.UUID,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """
    Return full zone detail including available voices and sample audio.
    """
    zone = await repo.get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    voices = await repo.get_active_voices()

    return {
        "id": zone.id,
        "name": zone.name,
        "description": zone.description,
        "theme": zone.theme,
        "point_count": zone.point_count,
        "available_voices": [
            {
                "id": v.id,
                "name": v.name,
                "style_group": v.style_group,
                "language": v.language,
                "preview_audio_url": v.preview_audio_url,
            }
            for v in voices
        ],
        "available_languages": list({v.language for v in voices}),
        "sample_audio_url": None,
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@guide_router.post("/sessions", response_model=SessionCreateResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """
    Create a new guide session and preload content for 8 nearest points.
    < 500ms budget (heavy: loads topology + CDN URLs from DB).
    """
    return await manager.create_session(
        repo=repo,
        user_id=user.id,
        zone_id=request.zone_id,
        voice_id=request.voice_id,
        language=request.language,
        detail_level=request.detail_level,
        initial_lat=request.initial_location.lat,
        initial_lng=request.initial_location.lng,
    )


@guide_router.post("/sessions/{session_id}/heartbeat", response_model=HeartbeatResponse)
async def session_heartbeat(
    session_id: uuid.UUID,
    request: HeartbeatRequest,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """
    Report active listening time and current position.
    Debits balance and refreshes preloaded content if position changed > 50m.
    < 200ms budget.
    """
    return await manager.process_heartbeat(
        repo=repo,
        session_id=session_id,
        seconds_active=request.seconds_active,
        lat=request.location.lat,
        lng=request.location.lng,
        heading_deg=request.heading_deg,
    )


@guide_router.post("/sessions/{session_id}/pause", response_model=PauseResponse)
async def pause_session(
    session_id: uuid.UUID,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """Pause the session. Balance stops being debited."""
    return await manager.pause_session(repo, session_id)


@guide_router.post("/sessions/{session_id}/resume", response_model=ResumeResponse)
async def resume_session(
    session_id: uuid.UUID,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """
    Resume a paused session.
    Returns recap content for the last visited POI so the user can re-orient.
    """
    return await manager.resume_session(repo, session_id)


@guide_router.post("/sessions/{session_id}/end", response_model=SessionSummary)
async def end_session(
    session_id: uuid.UUID,
    request: SessionEndRequest,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """
    End the session, release in-memory state, and return a summary.
    < 500ms budget.
    """
    return await manager.end_session(repo, session_id, request.exit_reason)


@guide_router.get("/sessions/{session_id}/summary", response_model=SessionSummary)
async def get_session_summary(
    session_id: uuid.UUID,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """Return the summary for a completed or active session."""
    from src.guide.application.session_manager import _build_summary_standalone
    return await manager._build_summary(repo, session_id)


@guide_router.get("/sessions/history", response_model=SessionsHistoryResponse)
async def get_sessions_history(
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """
    Return the user's session history.
    TODO: implement with pagination.
    """
    return SessionsHistoryResponse(sessions=[], total=0)


@guide_router.post("/sessions/{session_id}/rate", response_model=SessionRateResponse)
async def rate_session(
    session_id: uuid.UUID,
    request: SessionRateRequest,
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """Submit a 1–5 star rating for a completed session."""
    if not 1 <= request.rating <= 5:
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5")
    await manager.rate_session(repo, session_id, request.rating, request.review_text)
    return SessionRateResponse(
        session_id=session_id,
        rating=request.rating,
        review_text=request.review_text,
    )


# ---------------------------------------------------------------------------
# Navigation (hot path — < 100ms)
# ---------------------------------------------------------------------------

@guide_router.get("/navigation/next")
async def navigation_next(
    session_id: uuid.UUID = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
    heading_deg: Optional[float] = Query(None),
    gps_accuracy_m: float = Query(5.0),
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
    manager: SessionManager = Depends(get_session_manager),
):
    """
    The hot navigation endpoint — called every 3–5 seconds while the user walks.
    All computation is in-memory (synchronous NavigationEngine).
    < 100ms budget.
    """
    return await manager.get_navigation_next(
        repo=repo,
        session_id=session_id,
        lat=lat,
        lng=lng,
        heading_deg=heading_deg,
        gps_accuracy_m=gps_accuracy_m,
    )


# ---------------------------------------------------------------------------
# Balance & Packages
# ---------------------------------------------------------------------------

@guide_router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """
    Return the user's current minute balance.
    Billing is stubbed — returns 99999 until Step 6 is implemented.
    TODO Step 6: query guide_minute_balances.
    """
    balance = await repo.get_balance(user.id)
    seconds = balance.seconds_remaining if balance else 99999
    trial_used = balance.trial_seconds_used if balance else 0
    trial_granted = balance.trial_seconds_granted if balance else 0
    trial_remaining = max(0, trial_granted - trial_used)
    return BalanceResponse(
        seconds_remaining=seconds,
        minutes_remaining=round(seconds / 60, 2),
        trial_minutes_remaining=round(trial_remaining / 60, 2),
        last_purchase_at=None,
    )


@guide_router.get("/packages", response_model=PackagesResponse)
async def get_packages(
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """Return available minute packages from guide_packages table."""
    pkgs = await repo.get_packages()
    return PackagesResponse(
        packages=[
            Package(
                id=p.id,
                minutes=p.minutes,
                price_usd=p.price_usd,
                apple_product_id=p.apple_product_id,
                google_product_id=p.google_product_id,
                is_active=p.is_active,
            )
            for p in pkgs
        ]
    )


# ---------------------------------------------------------------------------
# Stubs (501 Not Implemented)
# ---------------------------------------------------------------------------

@guide_router.post("/qa/ask")
async def qa_ask(
    session_id: uuid.UUID = Form(...),
    audio: UploadFile = File(...),
    current_point_id: Optional[uuid.UUID] = Form(None),
    user: UserModel = Depends(get_current_user),
    repo: NavigationRepository = Depends(get_navigation_repo),
):
    """
    Streaming Q&A endpoint (SSE).

    Accepts multipart/form-data with:
      - session_id (UUID)
      - audio (mp3/m4a/wav, max 5 MB)
      - current_point_id (UUID, optional)

    Emits Server-Sent Events:
      transcript, answer_chunk, audio_chunk (base64 or URL), done, error
    """
    from src.guide.application.qa_pipeline import QAPipeline
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client
    from src.guide.infrastructure.stt_client import get_stt_client
    from src.infrastructure.llm_client import IoNetLLMClient, AnthropicLLMClient

    # Validate size
    audio_bytes = await audio.read()
    if len(audio_bytes) > settings.guide_qa_max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio file too large (max 5 MB)")

    mime = audio.content_type or "audio/mpeg"

    # Build pipeline
    stt = get_stt_client()
    if settings.llm_provider == "anthropic":
        llm = AnthropicLLMClient()
    else:
        llm = IoNetLLMClient()

    pipeline = QAPipeline(
        stt_client=stt,
        llm_client=llm,
        elevenlabs_client=ElevenLabsClient(),
        s3_client=GuideS3Client(),
        repo=repo,
        settings=settings,
    )

    async def event_stream():
        async for event in pipeline.process_question(
            session_id=session_id,
            audio_bytes=audio_bytes,
            audio_mime=mime,
            current_point_id=current_point_id,
        ):
            event_type = event["event"]
            data = json.dumps(event["data"])
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@guide_router.post("/purchases/validate")
async def validate_purchase(user: UserModel = Depends(get_current_user)):
    """
    IAP receipt validation (Apple + Google).
    TODO Step 6: implement server-side IAP validation.
    """
    raise HTTPException(status_code=501, detail="IAP validation not yet implemented (Step 6)")


@guide_router.post("/purchases/refund-webhook")
async def refund_webhook():
    """
    Apple / Google refund webhook handler.
    TODO Step 6: implement refund revocation logic.
    """
    raise HTTPException(status_code=501, detail="Refund webhook not yet implemented (Step 6)")
