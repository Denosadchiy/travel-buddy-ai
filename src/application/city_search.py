"""
City search service backed by the `cities` table.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.models import CityModel

logger = logging.getLogger(__name__)


def normalize_city_query(query: str) -> str:
    """Normalize query for stable matching and caching."""
    cleaned = query.strip().lower()
    # Normalize all dash variants and collapse separators.
    cleaned = re.sub(r"[\u2010-\u2015\-]+", " ", cleaned)
    cleaned = cleaned.replace("ё", "е")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _transliterate_cyrillic(text: str) -> str:
    # Minimal transliteration to improve matching against name_ascii.
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "i",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
        "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
        "ю": "yu", "я": "ya",
    })
    return text.translate(table)


def normalize_ascii_query(query: str) -> str:
    transliterated = _transliterate_cyrillic(query)
    ascii_query = (
        unicodedata.normalize("NFKD", transliterated)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    ascii_query = re.sub(r"\s+", " ", ascii_query).strip()
    return ascii_query


def _contains_cyrillic(value: str) -> bool:
    return any(_is_cyrillic_char(ch) for ch in value)


_RUSSIAN_CYRILLIC_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def _is_cyrillic_char(ch: str) -> bool:
    return "\u0400" <= ch <= "\u04FF"


def _russian_cyrillic_ratio(value: str) -> float:
    cyr = [ch.lower() for ch in value if _is_cyrillic_char(ch)]
    if not cyr:
        return 0.0
    russian = sum(1 for ch in cyr if ch in _RUSSIAN_CYRILLIC_CHARS)
    return russian / len(cyr)


def _pick_best_cyrillic_alternate(
    alternate_names: list[str],
    query: str | None = None,
    canonical_ascii_name: str | None = None,
) -> str | None:
    candidates = [alt for alt in alternate_names if _contains_cyrillic(alt)]
    if not candidates:
        return None

    normalized_query = normalize_city_query(query or "")
    normalized_query_ascii = normalize_ascii_query(normalized_query) if normalized_query else ""
    canonical_ascii = normalize_ascii_query(canonical_ascii_name or "")

    if not normalized_query:
        # Prefer names that look closest to standard Russian Cyrillic.
        def score_without_query(alt: str) -> tuple[float, float, int]:
            alt_ascii = normalize_ascii_query(alt)
            canonical_similarity = (
                SequenceMatcher(a=alt_ascii, b=canonical_ascii).ratio() if canonical_ascii else 0.0
            )
            return (_russian_cyrillic_ratio(alt), canonical_similarity, -len(alt))

        return max(candidates, key=score_without_query)

    def score(alt: str) -> float:
        alt_normalized = normalize_city_query(alt)
        alt_ascii = normalize_ascii_query(alt_normalized)
        s = _russian_cyrillic_ratio(alt) * 140

        if _contains_cyrillic(normalized_query):
            if alt_normalized == normalized_query:
                s += 600
            elif alt_normalized.startswith(normalized_query):
                s += 420
            elif normalized_query in alt_normalized:
                s += 300
            s += SequenceMatcher(a=alt_normalized, b=normalized_query).ratio() * 100
        else:
            if alt_ascii == normalized_query_ascii:
                s += 520
            elif alt_ascii.startswith(normalized_query_ascii):
                s += 360
            elif normalized_query_ascii and normalized_query_ascii in alt_ascii:
                s += 260
            s += SequenceMatcher(a=alt_ascii, b=normalized_query_ascii).ratio() * 95

        if canonical_ascii:
            s += SequenceMatcher(a=alt_ascii, b=canonical_ascii).ratio() * 55
        # Penalize long, noisy variants like "город N" when query is concise.
        s -= max(0, len(alt_normalized) - len(normalized_query)) * 0.2
        return s

    return max(candidates, key=score)


def pick_localized_name(
    name: str,
    name_ascii: str,
    alternate_names: list[str],
    lang: str,
    query: str | None = None,
) -> str:
    language = (lang or "").lower()
    if language.startswith("en"):
        return name_ascii or name
    if language.startswith("ru"):
        best_ru = _pick_best_cyrillic_alternate(
            alternate_names,
            query=query,
            canonical_ascii_name=name_ascii or name,
        )
        if best_ru:
            return best_ru
    return name


@dataclass(frozen=True)
class CitySearchItem:
    id: int
    name: str
    localized_name: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    population: int


class _TTLCache:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._storage: dict[str, tuple[datetime, list[CitySearchItem]]] = {}

    def get(self, key: str) -> Optional[list[CitySearchItem]]:
        entry = self._storage.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        if datetime.utcnow() >= expires_at:
            self._storage.pop(key, None)
            return None
        return payload

    def set(self, key: str, payload: list[CitySearchItem]) -> None:
        self._storage[key] = (datetime.utcnow() + self.ttl, payload)

    def clear(self) -> None:
        self._storage.clear()


class CitySearchService:
    def __init__(self):
        self._search_cache = _TTLCache(ttl_seconds=24 * 60 * 60)
        self._popular_cache = _TTLCache(ttl_seconds=24 * 60 * 60)

    def clear_cache(self) -> None:
        self._search_cache.clear()
        self._popular_cache.clear()

    async def search(
        self,
        db: AsyncSession,
        query: str,
        lang: str = "en",
        limit: int = 7,
    ) -> list[CitySearchItem]:
        normalized = normalize_city_query(query)
        if len(normalized) < 2:
            return []

        normalized_ascii = normalize_ascii_query(normalized)
        cache_key = f"city_search:{normalized}:{lang}:{limit}"
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return cached

        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            try:
                results = await self._search_postgres(db, normalized, normalized_ascii, lang, limit)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("Postgres city search fallback due to error: %s", exc)
                results = await self._search_generic(db, normalized, normalized_ascii, lang, limit)
        else:
            results = await self._search_generic(db, normalized, normalized_ascii, lang, limit)

        self._search_cache.set(cache_key, results)
        return results

    async def popular(
        self,
        db: AsyncSession,
        lang: str = "en",
        limit: int = 10,
    ) -> list[CitySearchItem]:
        cache_key = f"city_popular:{lang}:{limit}"
        cached = self._popular_cache.get(cache_key)
        if cached is not None:
            return cached

        stmt = (
            select(CityModel)
            .order_by(desc(CityModel.population), CityModel.name_ascii.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        results = [self._to_item(city, lang) for city in rows]
        self._popular_cache.set(cache_key, results)
        return results

    async def _search_postgres(
        self,
        db: AsyncSession,
        normalized: str,
        normalized_ascii: str,
        lang: str,
        limit: int,
    ) -> list[CitySearchItem]:
        ascii_query = normalized_ascii or normalized
        prefix = f"{normalized}%"
        prefix_ascii = f"{ascii_query}%"
        contains = f"%{normalized}%"
        contains_ascii = f"%{ascii_query}%"

        alt_text = func.lower(func.coalesce(func.array_to_string(CityModel.alternate_names, ","), ""))
        prefix_score = case(
            (func.lower(CityModel.name_ascii).like(prefix_ascii), 300),
            (func.lower(CityModel.name).like(prefix), 260),
            (alt_text.like(prefix), 240),
            else_=0,
        )
        contains_score = case(
            (alt_text.like(contains), 220),
            (func.lower(CityModel.name_ascii).like(contains_ascii), 180),
            (func.lower(CityModel.name).like(contains), 170),
            else_=0,
        )
        sim_ascii = func.similarity(func.lower(CityModel.name_ascii), ascii_query)
        sim_name = func.similarity(func.lower(CityModel.name), normalized)
        sim_alt = func.similarity(alt_text, normalized)
        best_similarity = func.greatest(sim_ascii, sim_name, sim_alt)

        stmt = (
            select(CityModel)
            .where(
                or_(
                    func.lower(CityModel.name_ascii).like(prefix_ascii),
                    func.lower(CityModel.name).like(prefix),
                    alt_text.like(contains),
                    func.lower(CityModel.name_ascii).like(contains_ascii),
                    best_similarity >= 0.28,
                )
            )
            .order_by(
                desc(prefix_score),
                desc(contains_score),
                desc(best_similarity),
                desc(CityModel.population),
                CityModel.name_ascii.asc(),
            )
            .limit(max(limit * 5, 30))
        )
        rows = (await db.execute(stmt)).scalars().all()
        return self._dedupe([self._to_item(city, lang, query=normalized) for city in rows], limit)

    async def _search_generic(
        self,
        db: AsyncSession,
        normalized: str,
        normalized_ascii: str,
        lang: str,
        limit: int,
    ) -> list[CitySearchItem]:
        ascii_query = normalized_ascii or normalized
        rows = (await db.execute(select(CityModel))).scalars().all()

        def matches(city: CityModel) -> bool:
            name = (city.name or "").lower()
            name_ascii = (city.name_ascii or "").lower()
            alternates = [alt.lower() for alt in (city.alternate_names or [])]
            return (
                normalized in name
                or ascii_query in name_ascii
                or any(normalized in alt for alt in alternates)
                or any(ascii_query in normalize_ascii_query(alt) for alt in alternates)
            )

        rows = [city for city in rows if matches(city)]

        def rank(city: CityModel) -> tuple[float, int]:
            name = (city.name or "").lower()
            name_ascii = (city.name_ascii or "").lower()
            alt = ",".join(city.alternate_names or []).lower()
            prefix_bonus = 1.0 if (
                name.startswith(normalized)
                or name_ascii.startswith(ascii_query)
                or alt.startswith(normalized)
            ) else 0.0

            contains_bonus = 0.0
            if normalized in name:
                contains_bonus += 0.8
            if ascii_query in name_ascii:
                contains_bonus += 0.9
            if normalized in alt:
                contains_bonus += 1.2

            alt_best_similarity = max(
                (
                    SequenceMatcher(a=normalize_city_query(alt_item), b=normalized).ratio()
                    for alt_item in (city.alternate_names or [])
                ),
                default=0.0,
            )
            similarity = max(
                SequenceMatcher(a=name, b=normalized).ratio(),
                SequenceMatcher(a=name_ascii, b=ascii_query).ratio(),
                alt_best_similarity,
            )
            return (prefix_bonus + contains_bonus + similarity, city.population or 0)

        rows.sort(key=rank, reverse=True)
        return self._dedupe([self._to_item(city, lang, query=normalized) for city in rows], limit)

    def _to_item(self, city: CityModel, lang: str, query: str | None = None) -> CitySearchItem:
        localized = pick_localized_name(
            name=city.name,
            name_ascii=city.name_ascii,
            alternate_names=city.alternate_names or [],
            lang=lang,
            query=query,
        )
        return CitySearchItem(
            id=city.geoname_id,
            name=city.name,
            localized_name=localized,
            country=city.country_name,
            country_code=city.country_code,
            latitude=float(city.latitude),
            longitude=float(city.longitude),
            population=city.population or 0,
        )

    @staticmethod
    def _dedupe(items: list[CitySearchItem], limit: int) -> list[CitySearchItem]:
        unique: dict[int, CitySearchItem] = {}
        for item in items:
            if item.id not in unique:
                unique[item.id] = item
            if len(unique) >= limit:
                break
        return list(unique.values())


city_search_service = CitySearchService()
