"""
i18n runtime and rollout control endpoints.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.infrastructure.database import get_db
from src.infrastructure.models import LocalizationEntryModel
from src.i18n import (
    get_budget_alert_state,
    get_enabled_rollout_locales,
    get_i18n_observability,
    get_rollout_matrix,
    get_translation_budget_guard,
    TranslationStatus,
    build_locale_fallback_chain,
    get_tier_keys,
    is_status_ready_for_tier_a,
    normalize_locale,
    resolve_or_enqueue_translation,
    translation_queue_service,
    translation_storage_service,
)

router = APIRouter(prefix="/i18n", tags=["i18n"])


class TranslationBudgetStatus(BaseModel):
    day_key: str
    month_key: str
    day_used_chars: int
    month_used_chars: int
    day_limit_chars: int
    month_limit_chars: int
    day_remaining_chars: int
    month_remaining_chars: int
    machine_translation_enabled: bool
    budget_guard_enabled: bool


class I18nRuntimeStatus(BaseModel):
    source_language: str
    fallback_language: str
    supported_languages: list[str]
    resolved_locale: str
    locale_source: str
    locale_is_fallback: bool
    machine_translation_enabled: bool
    budget_guard_enabled: bool
    budget: TranslationBudgetStatus


class BudgetPreviewResponse(BaseModel):
    char_count: int
    allowed: bool
    reason: str


class TranslationUpsertRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Translation key, e.g. errors.trip_not_found")
    locale: str = Field(..., min_length=2, description="Target locale, e.g. ru or ru-RU")
    text: str = Field(..., min_length=1, description="Translated text")
    status: Optional[TranslationStatus] = Field(
        default=None,
        description="Optional target status; if omitted existing status is preserved",
    )
    source_hash: Optional[str] = Field(
        default=None,
        description="Optional source text hash for invalidation",
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Optional source text (hash will be derived if source_hash is omitted)",
    )
    source_language: Optional[str] = Field(
        default=None,
        description="Source language locale code",
    )


class TranslationEntryResponse(BaseModel):
    id: str
    key: str
    locale: str
    source_language: str
    text: str
    status: str
    source_hash: Optional[str]
    created_at: datetime
    updated_at: datetime


class TranslationResolveResponse(BaseModel):
    key: str
    requested_locale: str
    resolved_locale: str
    is_fallback: bool
    fallback_chain: list[str]
    text: str
    status: str
    source_hash: Optional[str]
    source_language: str


class MissingTranslationsResponse(BaseModel):
    source_locale: str
    target_locale: str
    missing_keys: list[str]


class RuntimeResolveResponse(BaseModel):
    key: str
    requested_locale: str
    resolved_locale: str
    text: str
    is_fallback: bool
    queued: bool
    queue_reason: str
    source: str
    status: str
    rollout_enabled: bool


class TranslationQueueStatsResponse(BaseModel):
    pending: int
    processing: int
    done: int
    failed: int
    blocked: int


class TranslationQueueActionResponse(BaseModel):
    queued: bool
    reason: str
    job_id: Optional[str]
    status: Optional[str]


class TranslationQueueRequeueRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Translation key")
    locale: str = Field(..., min_length=2, description="Target locale")


class TranslationStatusTransitionRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Translation key")
    locale: str = Field(..., min_length=2, description="Target locale")
    status: TranslationStatus = Field(..., description="Target workflow status")


class PendingReviewItem(BaseModel):
    key: str
    locale: str
    status: str
    text: str
    updated_at: datetime


class PendingReviewResponse(BaseModel):
    tier: str
    locale: str
    total: int
    entries: list[PendingReviewItem]


class LocaleFallbackRateResponse(BaseModel):
    locale: str
    total_requests: int
    fallback_requests: int
    fallback_rate: float


class MissingKeyMetricResponse(BaseModel):
    locale: str
    key: str
    hits: int


class ScreenFallbackMetricResponse(BaseModel):
    locale: str
    screen: str
    hits: int


class CounterMetricResponse(BaseModel):
    name: str
    hits: int


class BudgetAlertStateResponse(BaseModel):
    day_used_chars: int
    day_limit_chars: int
    month_used_chars: int
    month_limit_chars: int
    day_usage_ratio: float
    month_usage_ratio: float
    day_alert_threshold: float
    month_alert_threshold: float
    day_alert: bool
    month_alert: bool
    machine_translation_enabled: bool
    budget_guard_enabled: bool


class I18nMetricsResponse(BaseModel):
    generated_at: datetime
    locale_fallback_rates: list[LocaleFallbackRateResponse]
    top_missing_keys: list[MissingKeyMetricResponse]
    top_fallback_screens: list[ScreenFallbackMetricResponse]
    queue_reasons: list[CounterMetricResponse]
    sources: list[CounterMetricResponse]
    budget_alerts: BudgetAlertStateResponse


class RolloutLocaleResponse(BaseModel):
    locale: str
    enabled: bool


class RolloutStatusResponse(BaseModel):
    rollout_enforced: bool
    enabled_locales: list[str]
    supported_locales: list[str]
    locales: list[RolloutLocaleResponse]


def _to_entry_response(entry: LocalizationEntryModel) -> TranslationEntryResponse:
    return TranslationEntryResponse(
        id=str(entry.id),
        key=entry.translation_key,
        locale=entry.locale,
        source_language=entry.source_language,
        text=entry.text,
        status=entry.status,
        source_hash=entry.source_hash,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("/runtime", response_model=I18nRuntimeStatus)
async def i18n_runtime_status(request: Request) -> I18nRuntimeStatus:
    """
    Runtime i18n settings and machine-translation budget snapshot.
    """
    snapshot = get_translation_budget_guard().snapshot()
    budget_status = TranslationBudgetStatus(
        day_key=snapshot.day_key,
        month_key=snapshot.month_key,
        day_used_chars=snapshot.day_used_chars,
        month_used_chars=snapshot.month_used_chars,
        day_limit_chars=snapshot.day_limit_chars,
        month_limit_chars=snapshot.month_limit_chars,
        day_remaining_chars=snapshot.day_remaining_chars,
        month_remaining_chars=snapshot.month_remaining_chars,
        machine_translation_enabled=snapshot.machine_translation_enabled,
        budget_guard_enabled=snapshot.budget_guard_enabled,
    )

    return I18nRuntimeStatus(
        source_language=settings.i18n_source_language,
        fallback_language=settings.i18n_fallback_language,
        supported_languages=settings.i18n_supported_languages_list,
        resolved_locale=getattr(
            request.state, "resolved_locale", settings.i18n_fallback_language
        ),
        locale_source=getattr(request.state, "locale_source", "fallback"),
        locale_is_fallback=getattr(request.state, "locale_is_fallback", True),
        machine_translation_enabled=settings.i18n_machine_translation_enabled,
        budget_guard_enabled=settings.i18n_budget_guard_enabled,
        budget=budget_status,
    )


@router.get("/budget/preview", response_model=BudgetPreviewResponse)
async def preview_translation_budget(
    char_count: int = Query(..., ge=0, description="Characters to check"),
) -> BudgetPreviewResponse:
    """
    Dry-run budget check for a hypothetical machine-translation call.
    """
    allowed, reason = get_translation_budget_guard().preview(char_count)
    return BudgetPreviewResponse(
        char_count=char_count,
        allowed=allowed,
        reason=reason,
    )


@router.get(
    "/budget/alerts",
    response_model=BudgetAlertStateResponse,
    summary="Get app-side budget alert state",
)
async def i18n_budget_alerts() -> BudgetAlertStateResponse:
    budget = get_budget_alert_state()
    return BudgetAlertStateResponse(
        day_used_chars=budget.day_used_chars,
        day_limit_chars=budget.day_limit_chars,
        month_used_chars=budget.month_used_chars,
        month_limit_chars=budget.month_limit_chars,
        day_usage_ratio=budget.day_usage_ratio,
        month_usage_ratio=budget.month_usage_ratio,
        day_alert_threshold=budget.day_alert_threshold,
        month_alert_threshold=budget.month_alert_threshold,
        day_alert=budget.day_alert,
        month_alert=budget.month_alert,
        machine_translation_enabled=budget.machine_translation_enabled,
        budget_guard_enabled=budget.budget_guard_enabled,
    )


@router.post(
    "/translations/upsert",
    response_model=TranslationEntryResponse,
    summary="Create or update translation entry",
)
async def upsert_translation(
    payload: TranslationUpsertRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslationEntryResponse:
    try:
        entry = await translation_storage_service.upsert_entry(
            db,
            key=payload.key,
            locale=payload.locale,
            text=payload.text,
            status=payload.status,
            source_hash=payload.source_hash,
            source_text=payload.source_text,
            source_language=payload.source_language,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return _to_entry_response(entry)


@router.get(
    "/translations/entry",
    response_model=TranslationEntryResponse,
    summary="Get exact translation entry by key and locale",
)
async def get_translation_entry(
    key: str = Query(..., min_length=1),
    locale: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
) -> TranslationEntryResponse:
    entry = await translation_storage_service.get_entry(
        db,
        key=key,
        locale=locale,
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Translation entry not found",
        )
    return _to_entry_response(entry)


@router.get(
    "/translations/resolve",
    response_model=TranslationResolveResponse,
    summary="Resolve translation with locale fallback chain",
)
async def resolve_translation(
    key: str = Query(..., min_length=1),
    locale: str = Query(..., min_length=2),
    fallback_language: Optional[str] = Query(
        default=None, min_length=2, description="Optional fallback language override"
    ),
    db: AsyncSession = Depends(get_db),
) -> TranslationResolveResponse:
    resolved = await translation_storage_service.resolve_entry(
        db,
        key=key,
        locale=locale,
        fallback_language=fallback_language,
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No translation found in fallback chain",
        )

    chain = build_locale_fallback_chain(
        locale,
        fallback_language=fallback_language,
    )
    return TranslationResolveResponse(
        key=resolved.key,
        requested_locale=resolved.requested_locale,
        resolved_locale=resolved.resolved_locale,
        is_fallback=resolved.is_fallback,
        fallback_chain=chain,
        text=resolved.text,
        status=resolved.status,
        source_hash=resolved.source_hash,
        source_language=resolved.source_language,
    )


@router.get(
    "/translations/runtime",
    response_model=RuntimeResolveResponse,
    summary="Resolve translation and enqueue async job when missing",
)
async def resolve_translation_runtime(
    key: str = Query(..., min_length=1),
    locale: str = Query(..., min_length=2),
    screen: Optional[str] = Query(
        default=None,
        min_length=1,
        description="Logical screen name for fallback-rate metrics",
    ),
    fallback_language: Optional[str] = Query(
        default=None,
        min_length=2,
        description="Optional fallback language override",
    ),
    db: AsyncSession = Depends(get_db),
) -> RuntimeResolveResponse:
    try:
        runtime = await resolve_or_enqueue_translation(
            db,
            key=key,
            locale=locale,
            fallback_language=fallback_language,
            screen=screen,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return RuntimeResolveResponse(
        key=runtime.key,
        requested_locale=runtime.requested_locale,
        resolved_locale=runtime.resolved_locale,
        text=runtime.text,
        is_fallback=runtime.is_fallback,
        queued=runtime.queued,
        queue_reason=runtime.queue_reason,
        source=runtime.source,
        status=runtime.status,
        rollout_enabled=runtime.rollout_enabled,
    )


@router.get(
    "/metrics",
    response_model=I18nMetricsResponse,
    summary="Get i18n runtime observability metrics",
)
async def i18n_metrics(
    missing_limit: int = Query(10, ge=1, le=100),
    screen_limit: int = Query(10, ge=1, le=100),
) -> I18nMetricsResponse:
    snapshot = get_i18n_observability().snapshot(
        missing_limit=missing_limit,
        screen_limit=screen_limit,
    )
    budget = snapshot.budget_alerts
    return I18nMetricsResponse(
        generated_at=snapshot.generated_at,
        locale_fallback_rates=[
            LocaleFallbackRateResponse(
                locale=item.locale,
                total_requests=item.total_requests,
                fallback_requests=item.fallback_requests,
                fallback_rate=item.fallback_rate,
            )
            for item in snapshot.locale_fallback_rates
        ],
        top_missing_keys=[
            MissingKeyMetricResponse(
                locale=item.locale,
                key=item.key,
                hits=item.hits,
            )
            for item in snapshot.top_missing_keys
        ],
        top_fallback_screens=[
            ScreenFallbackMetricResponse(
                locale=item.locale,
                screen=item.screen,
                hits=item.hits,
            )
            for item in snapshot.top_fallback_screens
        ],
        queue_reasons=[
            CounterMetricResponse(name=item.name, hits=item.hits)
            for item in snapshot.queue_reasons
        ],
        sources=[
            CounterMetricResponse(name=item.name, hits=item.hits)
            for item in snapshot.sources
        ],
        budget_alerts=BudgetAlertStateResponse(
            day_used_chars=budget.day_used_chars,
            day_limit_chars=budget.day_limit_chars,
            month_used_chars=budget.month_used_chars,
            month_limit_chars=budget.month_limit_chars,
            day_usage_ratio=budget.day_usage_ratio,
            month_usage_ratio=budget.month_usage_ratio,
            day_alert_threshold=budget.day_alert_threshold,
            month_alert_threshold=budget.month_alert_threshold,
            day_alert=budget.day_alert,
            month_alert=budget.month_alert,
            machine_translation_enabled=budget.machine_translation_enabled,
            budget_guard_enabled=budget.budget_guard_enabled,
        ),
    )


@router.get(
    "/rollout",
    response_model=RolloutStatusResponse,
    summary="Get per-locale rollout status matrix",
)
async def i18n_rollout_status() -> RolloutStatusResponse:
    matrix = get_rollout_matrix()
    return RolloutStatusResponse(
        rollout_enforced=settings.i18n_rollout_enforced,
        enabled_locales=sorted(get_enabled_rollout_locales()),
        supported_locales=settings.i18n_supported_languages_list,
        locales=[
            RolloutLocaleResponse(locale=item.locale, enabled=item.enabled)
            for item in matrix
        ],
    )


@router.get(
    "/translations/missing",
    response_model=MissingTranslationsResponse,
    summary="List keys missing in target locale compared to source locale",
)
async def list_missing_translations(
    target_locale: str = Query(..., min_length=2),
    source_locale: Optional[str] = Query(default=None, min_length=2),
    db: AsyncSession = Depends(get_db),
) -> MissingTranslationsResponse:
    try:
        missing_keys = await translation_storage_service.get_missing_keys(
            db,
            target_locale=target_locale,
            source_locale=source_locale,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    resolved_source = source_locale or settings.i18n_source_language
    return MissingTranslationsResponse(
        source_locale=resolved_source,
        target_locale=target_locale,
        missing_keys=missing_keys,
    )


@router.get(
    "/translations/queue/stats",
    response_model=TranslationQueueStatsResponse,
    summary="Get async translation queue status counters",
)
async def translation_queue_stats(
    db: AsyncSession = Depends(get_db),
) -> TranslationQueueStatsResponse:
    stats = await translation_queue_service.get_stats(db)
    return TranslationQueueStatsResponse(
        pending=stats.pending,
        processing=stats.processing,
        done=stats.done,
        failed=stats.failed,
        blocked=stats.blocked,
    )


@router.post(
    "/translations/queue/requeue",
    response_model=TranslationQueueActionResponse,
    summary="Force requeue latest translation job for key+locale",
)
async def translation_queue_requeue(
    payload: TranslationQueueRequeueRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslationQueueActionResponse:
    result = await translation_queue_service.requeue_latest_job(
        db,
        key=payload.key,
        target_locale=payload.locale,
    )
    await db.commit()
    return TranslationQueueActionResponse(
        queued=result.queued,
        reason=result.reason,
        job_id=result.job_id,
        status=result.status,
    )


@router.post(
    "/translations/status",
    response_model=TranslationEntryResponse,
    summary="Transition translation status (mt -> reviewed -> approved)",
)
async def transition_translation_status(
    payload: TranslationStatusTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslationEntryResponse:
    try:
        entry = await translation_storage_service.transition_entry_status(
            db,
            key=payload.key,
            locale=payload.locale,
            status=payload.status,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return _to_entry_response(entry)


@router.get(
    "/translations/review/pending",
    response_model=PendingReviewResponse,
    summary="List translations pending human review for a tier+locale",
)
async def list_pending_reviews(
    locale: str = Query(..., min_length=2),
    tier: str = Query("tier_a", description="tier_a | tier_b | tier_c"),
    db: AsyncSession = Depends(get_db),
) -> PendingReviewResponse:
    tier_keys = get_tier_keys(tier)
    if not tier_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or empty tier: {tier}",
        )

    normalized_locale = normalize_locale(locale)
    result = await db.execute(
        select(LocalizationEntryModel)
        .where(
            LocalizationEntryModel.locale == normalized_locale,
            LocalizationEntryModel.translation_key.in_(sorted(tier_keys)),
        )
        .order_by(LocalizationEntryModel.translation_key.asc())
    )
    rows = result.scalars().all()

    entries = [
        PendingReviewItem(
            key=row.translation_key,
            locale=row.locale,
            status=row.status,
            text=row.text,
            updated_at=row.updated_at,
        )
        for row in rows
        if not is_status_ready_for_tier_a(row.status)
    ]

    return PendingReviewResponse(
        tier=tier,
        locale=normalized_locale,
        total=len(entries),
        entries=entries,
    )
