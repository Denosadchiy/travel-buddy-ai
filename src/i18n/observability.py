"""
In-memory observability for i18n runtime and rollout operations.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from src.config import settings
from src.i18n.budget import get_translation_budget_guard
from src.i18n.rollout import normalize_rollout_locale


NON_MISSING_FALLBACK_REASONS = {
    "tier_a_requires_manual_review",
    "rollout_disabled",
}


@dataclass(frozen=True)
class LocaleFallbackRate:
    locale: str
    total_requests: int
    fallback_requests: int
    fallback_rate: float


@dataclass(frozen=True)
class MissingKeyHit:
    locale: str
    key: str
    hits: int


@dataclass(frozen=True)
class ScreenFallbackHit:
    locale: str
    screen: str
    hits: int


@dataclass(frozen=True)
class CounterMetric:
    name: str
    hits: int


@dataclass(frozen=True)
class BudgetAlertState:
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


@dataclass(frozen=True)
class I18nMetricsSnapshot:
    generated_at: datetime
    locale_fallback_rates: list[LocaleFallbackRate]
    top_missing_keys: list[MissingKeyHit]
    top_fallback_screens: list[ScreenFallbackHit]
    queue_reasons: list[CounterMetric]
    sources: list[CounterMetric]
    budget_alerts: BudgetAlertState


class InMemoryI18nObservability:
    """Process-local counters for i18n runtime behavior."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._total_by_locale: Counter[str] = Counter()
        self._fallback_by_locale: Counter[str] = Counter()
        self._missing_key_hits: Counter[tuple[str, str]] = Counter()
        self._fallback_by_screen: Counter[tuple[str, str]] = Counter()
        self._queue_reason_hits: Counter[str] = Counter()
        self._source_hits: Counter[str] = Counter()

    @staticmethod
    def _normalize_screen(screen: Optional[str]) -> str:
        value = (screen or "").strip().lower()
        return value or "unknown"

    def record_runtime_result(
        self,
        *,
        key: str,
        requested_locale: str,
        is_fallback: bool,
        queue_reason: str,
        source: str,
        screen: Optional[str] = None,
    ) -> None:
        locale = normalize_rollout_locale(requested_locale)
        normalized_key = (key or "").strip()
        normalized_reason = (queue_reason or "unknown").strip().lower()
        normalized_source = (source or "unknown").strip().lower()
        normalized_screen = self._normalize_screen(screen)

        with self._lock:
            self._total_by_locale[locale] += 1
            self._source_hits[normalized_source] += 1
            self._queue_reason_hits[normalized_reason] += 1

            if is_fallback:
                self._fallback_by_locale[locale] += 1
                self._fallback_by_screen[(locale, normalized_screen)] += 1
                if (
                    normalized_key
                    and normalized_reason not in NON_MISSING_FALLBACK_REASONS
                ):
                    self._missing_key_hits[(locale, normalized_key)] += 1

    def snapshot(
        self,
        *,
        missing_limit: int = 10,
        screen_limit: int = 10,
    ) -> I18nMetricsSnapshot:
        with self._lock:
            locale_rates: list[LocaleFallbackRate] = []
            for locale, total in self._total_by_locale.items():
                fallback = self._fallback_by_locale.get(locale, 0)
                ratio = (fallback / total) if total else 0.0
                locale_rates.append(
                    LocaleFallbackRate(
                        locale=locale,
                        total_requests=total,
                        fallback_requests=fallback,
                        fallback_rate=round(ratio, 4),
                    )
                )
            locale_rates.sort(
                key=lambda item: (item.fallback_rate, item.total_requests),
                reverse=True,
            )

            top_missing = [
                MissingKeyHit(locale=locale, key=key, hits=hits)
                for (locale, key), hits in self._missing_key_hits.most_common(missing_limit)
            ]
            top_screens = [
                ScreenFallbackHit(locale=locale, screen=screen, hits=hits)
                for (locale, screen), hits in self._fallback_by_screen.most_common(screen_limit)
            ]
            queue_reasons = [
                CounterMetric(name=name, hits=hits)
                for name, hits in self._queue_reason_hits.most_common()
            ]
            sources = [
                CounterMetric(name=name, hits=hits)
                for name, hits in self._source_hits.most_common()
            ]

        return I18nMetricsSnapshot(
            generated_at=datetime.now(timezone.utc),
            locale_fallback_rates=locale_rates,
            top_missing_keys=top_missing,
            top_fallback_screens=top_screens,
            queue_reasons=queue_reasons,
            sources=sources,
            budget_alerts=get_budget_alert_state(),
        )


def get_budget_alert_state() -> BudgetAlertState:
    snapshot = get_translation_budget_guard().snapshot()
    day_ratio = (
        snapshot.day_used_chars / snapshot.day_limit_chars
        if snapshot.day_limit_chars > 0
        else 0.0
    )
    month_ratio = (
        snapshot.month_used_chars / snapshot.month_limit_chars
        if snapshot.month_limit_chars > 0
        else 0.0
    )
    day_alert = (
        snapshot.budget_guard_enabled
        and day_ratio >= settings.i18n_budget_alert_day_ratio
    )
    month_alert = (
        snapshot.budget_guard_enabled
        and month_ratio >= settings.i18n_budget_alert_month_ratio
    )
    return BudgetAlertState(
        day_used_chars=snapshot.day_used_chars,
        day_limit_chars=snapshot.day_limit_chars,
        month_used_chars=snapshot.month_used_chars,
        month_limit_chars=snapshot.month_limit_chars,
        day_usage_ratio=round(day_ratio, 4),
        month_usage_ratio=round(month_ratio, 4),
        day_alert_threshold=settings.i18n_budget_alert_day_ratio,
        month_alert_threshold=settings.i18n_budget_alert_month_ratio,
        day_alert=day_alert,
        month_alert=month_alert,
        machine_translation_enabled=snapshot.machine_translation_enabled,
        budget_guard_enabled=snapshot.budget_guard_enabled,
    )


_i18n_observability = InMemoryI18nObservability()


def get_i18n_observability() -> InMemoryI18nObservability:
    return _i18n_observability
