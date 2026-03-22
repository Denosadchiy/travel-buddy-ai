"""
Runtime budget guardrails for machine translation.

Step-0 goal: provide a hard safety layer so translation API calls can be
introduced without accidental overspending.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from src.config import settings


@dataclass(frozen=True)
class TranslationBudgetSnapshot:
    """Current machine-translation budget state."""

    day_key: str
    month_key: str
    day_used_chars: int
    month_used_chars: int
    day_limit_chars: int
    month_limit_chars: int
    machine_translation_enabled: bool
    budget_guard_enabled: bool

    @property
    def day_remaining_chars(self) -> int:
        return max(0, self.day_limit_chars - self.day_used_chars)

    @property
    def month_remaining_chars(self) -> int:
        return max(0, self.month_limit_chars - self.month_used_chars)


class InMemoryTranslationBudgetGuard:
    """
    In-memory guard for machine-translation character limits.

    Notes:
    - Process-local only (single instance).
    - For multi-instance production, move counters to Redis/Postgres.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._day_key = self._current_day_key()
        self._month_key = self._current_month_key()
        self._day_used_chars = 0
        self._month_used_chars = 0

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _current_day_key(cls) -> str:
        return cls._now_utc().strftime("%Y-%m-%d")

    @classmethod
    def _current_month_key(cls) -> str:
        return cls._now_utc().strftime("%Y-%m")

    def _rollover_locked(self) -> None:
        day_key = self._current_day_key()
        month_key = self._current_month_key()

        if day_key != self._day_key:
            self._day_key = day_key
            self._day_used_chars = 0

        if month_key != self._month_key:
            self._month_key = month_key
            self._month_used_chars = 0

    def _preview_locked(self, char_count: int) -> tuple[bool, str]:
        if not settings.i18n_machine_translation_enabled:
            return False, "machine_translation_disabled"

        if not settings.i18n_budget_guard_enabled:
            return True, "ok"

        if self._day_used_chars + char_count > settings.i18n_max_chars_per_day:
            return False, "daily_budget_exceeded"

        if self._month_used_chars + char_count > settings.i18n_max_chars_per_month:
            return False, "monthly_budget_exceeded"

        return True, "ok"

    @staticmethod
    def _validate_char_count(char_count: int) -> None:
        if char_count < 0:
            raise ValueError("char_count must be >= 0")

    def preview(self, char_count: int) -> tuple[bool, str]:
        """Check if translation is allowed without consuming budget."""
        self._validate_char_count(char_count)
        with self._lock:
            self._rollover_locked()
            return self._preview_locked(char_count)

    def reserve(self, char_count: int) -> tuple[bool, str]:
        """
        Atomically check and consume translation budget.

        Returns:
            (allowed, reason)
        """
        self._validate_char_count(char_count)
        with self._lock:
            self._rollover_locked()
            allowed, reason = self._preview_locked(char_count)
            if not allowed:
                return False, reason

            if settings.i18n_budget_guard_enabled:
                self._day_used_chars += char_count
                self._month_used_chars += char_count
            return True, "ok"

    def snapshot(self) -> TranslationBudgetSnapshot:
        """Read current budget state."""
        with self._lock:
            self._rollover_locked()
            return TranslationBudgetSnapshot(
                day_key=self._day_key,
                month_key=self._month_key,
                day_used_chars=self._day_used_chars,
                month_used_chars=self._month_used_chars,
                day_limit_chars=settings.i18n_max_chars_per_day,
                month_limit_chars=settings.i18n_max_chars_per_month,
                machine_translation_enabled=settings.i18n_machine_translation_enabled,
                budget_guard_enabled=settings.i18n_budget_guard_enabled,
            )


_budget_guard = InMemoryTranslationBudgetGuard()


def get_translation_budget_guard() -> InMemoryTranslationBudgetGuard:
    """Get singleton budget guard instance."""
    return _budget_guard

