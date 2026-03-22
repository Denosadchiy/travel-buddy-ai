"""
Cities API endpoints for destination autocomplete.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.city_search import city_search_service
from src.infrastructure.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cities", tags=["cities"])
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


class CitySearchResultResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    localized_name: str = Field(alias="localizedName")
    country: str
    country_code: str = Field(alias="countryCode")
    latitude: float
    longitude: float
    population: int


class CitySearchResponse(BaseModel):
    results: list[CitySearchResultResponse]


class CitySelectionRequest(BaseModel):
    query: str
    selected_city_id: int = Field(alias="selectedCityId")
    lang: Optional[str] = None


def _resolve_lang(request: Request, explicit_lang: Optional[str]) -> str:
    if explicit_lang:
        return explicit_lang
    locale = getattr(request.state, "locale", None)
    if isinstance(locale, str) and locale:
        return locale
    header_lang = request.headers.get("X-Language")
    if header_lang:
        return header_lang
    return "en"


def _looks_like_cyrillic_query(query: str) -> bool:
    return bool(_CYRILLIC_RE.search(query))


@router.get("/search", response_model=CitySearchResponse)
async def search_cities(
    request: Request,
    query: str = Query(..., min_length=1, max_length=120),
    lang: Optional[str] = Query(default=None, max_length=16),
    limit: int = Query(default=7, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> CitySearchResponse:
    resolved_lang = _resolve_lang(request, lang)
    normalized_query = query.strip()
    if len(normalized_query) < 2:
        return CitySearchResponse(results=[])

    # If user types in Cyrillic, force Russian labels even when client sends another locale.
    if _looks_like_cyrillic_query(normalized_query) and not resolved_lang.lower().startswith("ru"):
        resolved_lang = "ru"

    items = await city_search_service.search(
        db=db,
        query=normalized_query,
        lang=resolved_lang,
        limit=limit,
    )
    logger.info(
        "city_search query=%r lang=%s limit=%s results_count=%s",
        normalized_query,
        resolved_lang,
        limit,
        len(items),
    )
    return CitySearchResponse(
        results=[
            CitySearchResultResponse(
                id=item.id,
                name=item.name,
                localizedName=item.localized_name,
                country=item.country,
                countryCode=item.country_code,
                latitude=item.latitude,
                longitude=item.longitude,
                population=item.population,
            )
            for item in items
        ]
    )


@router.get("/popular", response_model=CitySearchResponse)
async def popular_cities(
    request: Request,
    lang: Optional[str] = Query(default=None, max_length=16),
    limit: int = Query(default=10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> CitySearchResponse:
    resolved_lang = _resolve_lang(request, lang)
    items = await city_search_service.popular(
        db=db,
        lang=resolved_lang,
        limit=limit,
    )
    return CitySearchResponse(
        results=[
            CitySearchResultResponse(
                id=item.id,
                name=item.name,
                localizedName=item.localized_name,
                country=item.country,
                countryCode=item.country_code,
                latitude=item.latitude,
                longitude=item.longitude,
                population=item.population,
            )
            for item in items
        ]
    )


@router.post("/selection", status_code=status.HTTP_204_NO_CONTENT)
async def log_city_selection(
    payload: CitySelectionRequest,
    request: Request,
) -> Response:
    resolved_lang = _resolve_lang(request, payload.lang)
    logger.info(
        "city_selection query=%r selected_city_id=%s lang=%s",
        payload.query,
        payload.selected_city_id,
        resolved_lang,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
