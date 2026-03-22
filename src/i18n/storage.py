"""
Persistent translation storage service.

Step-3 focus:
- Store translated values in DB with status/source hash metadata
- Resolve values by locale fallback chain
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.i18n.quality import is_valid_status_transition
from src.infrastructure.models import LocalizationEntryModel


class TranslationStatus(str, Enum):
    """Translation lifecycle status."""

    DRAFT = "draft"
    MT = "mt"
    REVIEWED = "reviewed"
    APPROVED = "approved"


@dataclass(frozen=True)
class ResolvedTranslation:
    """Translation resolution result with fallback metadata."""

    key: str
    requested_locale: str
    resolved_locale: str
    is_fallback: bool
    text: str
    status: str
    source_hash: Optional[str]
    source_language: str


def normalize_locale(locale: Optional[str]) -> str:
    """Normalize locale code to lowercase BCP-47-ish format."""
    value = (locale or "").strip().replace("_", "-").lower()
    return value


def normalize_key(key: str) -> str:
    """Normalize translation key."""
    return (key or "").strip()


def make_source_hash(source_text: str) -> str:
    """Create deterministic hash of source text."""
    return sha256(source_text.encode("utf-8")).hexdigest()


def build_locale_fallback_chain(
    requested_locale: str,
    fallback_language: Optional[str] = None,
) -> list[str]:
    """
    Build locale fallback chain.

    Example:
    - requested `ru-RU`, fallback `en`
    - returns `["ru-ru", "ru", "en"]`
    """
    chain: list[str] = []

    normalized_requested = normalize_locale(requested_locale)
    if normalized_requested:
        chain.append(normalized_requested)
        if "-" in normalized_requested:
            base = normalized_requested.split("-", 1)[0]
            if base and base not in chain:
                chain.append(base)

    normalized_fallback = normalize_locale(
        fallback_language or settings.i18n_fallback_language
    )
    if normalized_fallback and normalized_fallback not in chain:
        chain.append(normalized_fallback)

    return chain


class TranslationStorageService:
    """Async service for persistent localization entries."""

    @staticmethod
    async def get_entry(
        db: AsyncSession,
        *,
        key: str,
        locale: str,
    ) -> Optional[LocalizationEntryModel]:
        translation_key = normalize_key(key)
        normalized_locale = normalize_locale(locale)
        if not translation_key or not normalized_locale:
            return None

        result = await db.execute(
            select(LocalizationEntryModel).where(
                LocalizationEntryModel.translation_key == translation_key,
                LocalizationEntryModel.locale == normalized_locale,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_entry(
        db: AsyncSession,
        *,
        key: str,
        locale: str,
        text: str,
        status: Optional[TranslationStatus] = None,
        source_hash: Optional[str] = None,
        source_text: Optional[str] = None,
        source_language: Optional[str] = None,
    ) -> LocalizationEntryModel:
        """
        Insert or update a translation entry.
        """
        translation_key = normalize_key(key)
        normalized_locale = normalize_locale(locale)
        normalized_source_language = normalize_locale(
            source_language or settings.i18n_source_language
        )
        normalized_status: Optional[str] = None
        if status is not None:
            normalized_status = (
                status.value if isinstance(status, TranslationStatus) else str(status)
            )

        if not translation_key:
            raise ValueError("key must not be empty")
        if not normalized_locale:
            raise ValueError("locale must not be empty")
        if not normalized_source_language:
            raise ValueError("source_language must not be empty")
        if not text:
            raise ValueError("text must not be empty")
        if (
            normalized_status is not None
            and normalized_status not in {item.value for item in TranslationStatus}
        ):
            raise ValueError(f"invalid status: {normalized_status}")

        effective_source_hash = source_hash
        if not effective_source_hash and source_text is not None:
            effective_source_hash = make_source_hash(source_text)

        existing = await TranslationStorageService.get_entry(
            db,
            key=translation_key,
            locale=normalized_locale,
        )

        if existing is not None:
            next_status = normalized_status or existing.status
            if (
                existing.status != next_status
                and not is_valid_status_transition(existing.status, next_status)
            ):
                raise ValueError(
                    "invalid status transition: "
                    f"{existing.status} -> {next_status}"
                )
            existing.text = text
            existing.status = next_status
            existing.source_hash = effective_source_hash
            existing.source_language = normalized_source_language
            await db.flush()
            return existing

        next_status = normalized_status or TranslationStatus.DRAFT.value
        created = LocalizationEntryModel(
            translation_key=translation_key,
            locale=normalized_locale,
            source_language=normalized_source_language,
            text=text,
            status=next_status,
            source_hash=effective_source_hash,
        )
        db.add(created)
        await db.flush()
        return created

    @staticmethod
    async def transition_entry_status(
        db: AsyncSession,
        *,
        key: str,
        locale: str,
        status: TranslationStatus,
    ) -> LocalizationEntryModel:
        """
        Transition translation status using quality workflow rules.
        """
        entry = await TranslationStorageService.get_entry(
            db,
            key=key,
            locale=locale,
        )
        if entry is None:
            raise ValueError("translation entry not found")

        target_status = status.value if isinstance(status, TranslationStatus) else str(status)
        if target_status not in {item.value for item in TranslationStatus}:
            raise ValueError(f"invalid status: {target_status}")
        if not is_valid_status_transition(entry.status, target_status):
            raise ValueError(
                f"invalid status transition: {entry.status} -> {target_status}"
            )

        entry.status = target_status
        await db.flush()
        return entry

    @staticmethod
    async def resolve_entry(
        db: AsyncSession,
        *,
        key: str,
        locale: str,
        fallback_language: Optional[str] = None,
    ) -> Optional[ResolvedTranslation]:
        """
        Resolve a translation by locale fallback chain.
        """
        translation_key = normalize_key(key)
        if not translation_key:
            return None

        chain = build_locale_fallback_chain(locale, fallback_language=fallback_language)
        if not chain:
            return None

        result = await db.execute(
            select(LocalizationEntryModel).where(
                LocalizationEntryModel.translation_key == translation_key,
                LocalizationEntryModel.locale.in_(chain),
            )
        )
        rows = result.scalars().all()
        by_locale = {row.locale: row for row in rows}

        requested_locale = normalize_locale(locale)
        for candidate in chain:
            entry = by_locale.get(candidate)
            if entry is not None:
                return ResolvedTranslation(
                    key=translation_key,
                    requested_locale=requested_locale or candidate,
                    resolved_locale=entry.locale,
                    is_fallback=entry.locale != requested_locale,
                    text=entry.text,
                    status=entry.status,
                    source_hash=entry.source_hash,
                    source_language=entry.source_language,
                )

        return None

    @staticmethod
    async def get_missing_keys(
        db: AsyncSession,
        *,
        target_locale: str,
        source_locale: Optional[str] = None,
    ) -> list[str]:
        """
        Return keys that exist in source_locale but are missing in target_locale.
        """
        normalized_target = normalize_locale(target_locale)
        normalized_source = normalize_locale(
            source_locale or settings.i18n_source_language
        )

        if not normalized_target:
            raise ValueError("target_locale must not be empty")
        if not normalized_source:
            raise ValueError("source_locale must not be empty")

        source_result = await db.execute(
            select(LocalizationEntryModel.translation_key).where(
                LocalizationEntryModel.locale == normalized_source
            )
        )
        source_keys = {row[0] for row in source_result.all()}

        target_result = await db.execute(
            select(LocalizationEntryModel.translation_key).where(
                LocalizationEntryModel.locale == normalized_target
            )
        )
        target_keys = {row[0] for row in target_result.all()}

        return sorted(source_keys - target_keys)


translation_storage_service = TranslationStorageService()
