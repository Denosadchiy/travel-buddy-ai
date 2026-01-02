"""
RouteTrace - Структура для объяснения решений при выборе POI и построении маршрута.

Цель: обеспечить прозрачность ("explainability") всего пайплайна генерации маршрута.
Каждый шаг (фильтрация, скоринг, выбор) логируется в RouteTrace, который затем
может быть передан клиенту для отображения "почему выбрано это место".
"""
from __future__ import annotations

from datetime import datetime, date, time
from enum import Enum
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field


class SelectionStage(str, Enum):
    """Этапы выбора POI."""
    CANDIDATE_GENERATION = "candidate_generation"
    FILTERING = "filtering"
    SCORING = "scoring"
    RANKING = "ranking"
    FINAL_SELECTION = "final_selection"
    ROUTE_OPTIMIZATION = "route_optimization"


class FilterReason(str, Enum):
    """Причины фильтрации POI."""
    OUTSIDE_RADIUS = "outside_radius"
    WRONG_BLOCK_TYPE = "wrong_block_type"
    ALREADY_USED = "already_used"
    EXCLUDED_KEYWORD = "excluded_keyword"
    LOW_RATING = "low_rating"
    BUDGET_MISMATCH = "budget_mismatch"
    CATEGORY_MISMATCH = "category_mismatch"
    OPENING_HOURS = "opening_hours"


class ScoringFactor(str, Enum):
    """Факторы, влияющие на score POI."""
    CATEGORY_MATCH = "category_match"
    TAG_OVERLAP = "tag_overlap"
    RATING = "rating"
    BUDGET_ALIGNMENT = "budget_alignment"
    HOTEL_PROXIMITY = "hotel_proximity"
    TRAVEL_TIME_PENALTY = "travel_time_penalty"
    DIVERSITY_BONUS = "diversity_bonus"
    LLM_PREFERENCE = "llm_preference"


class POIScoringBreakdown(BaseModel):
    """Детализация расчёта score для одного POI."""
    poi_id: UUID = Field(description="ID POI")
    poi_name: str = Field(description="Название POI для читаемости")

    # Баллы по каждому фактору
    factors: dict[ScoringFactor, float] = Field(
        default_factory=dict,
        description="Баллы по каждому фактору скоринга"
    )

    # Итоговый score
    total_score: float = Field(description="Итоговый score")

    # Человекочитаемое объяснение
    explanation: Optional[str] = Field(
        default=None,
        description="Краткое объяснение почему POI получил такой score"
    )


class POIFilteredOut(BaseModel):
    """Информация об отфильтрованном POI."""
    poi_id: UUID = Field(description="ID отфильтрованного POI")
    poi_name: str = Field(description="Название POI")
    reason: FilterReason = Field(description="Причина фильтрации")
    details: Optional[str] = Field(
        default=None,
        description="Дополнительные детали (например: 'distance: 18.5km, max: 15km')"
    )


class BlockSelectionTrace(BaseModel):
    """Трейс выбора POI для одного блока."""
    day_number: int = Field(ge=1, description="Номер дня")
    block_index: int = Field(ge=0, description="Индекс блока в дне")
    block_type: str = Field(description="Тип блока (meal, activity, etc.)")
    block_theme: Optional[str] = Field(default=None, description="Тема блока")

    # Входные данные
    desired_categories: list[str] = Field(
        default_factory=list,
        description="Желаемые категории для этого блока"
    )

    # Этап 0: Вызовы провайдеров (новое)
    provider_calls: list[ProviderCallTrace] = Field(
        default_factory=list,
        description="Детали вызовов провайдеров POI"
    )

    # Этап 1: Кандидаты
    candidates_fetched: int = Field(
        default=0,
        description="Сколько кандидатов было получено из провайдеров"
    )
    candidates_sources: dict[str, int] = Field(
        default_factory=dict,
        description="Количество кандидатов по источникам (db, google, etc.)"
    )

    # Этап 2: Фильтрация (расширенная)
    filter_rules_applied: list[FilterRuleTrace] = Field(
        default_factory=list,
        description="Детали применения правил фильтрации"
    )
    candidates_after_filter: int = Field(
        default=0,
        description="Сколько кандидатов осталось после фильтрации"
    )
    filtered_out: list[POIFilteredOut] = Field(
        default_factory=list,
        description="Список отфильтрованных POI с причинами (образцы до 10)"
    )

    # Этап 3: Ранжирование (новое)
    ranking_trace: Optional[RankingTrace] = Field(
        default=None,
        description="Детали ранжирования кандидатов"
    )

    # Этап 3 (старое поле, оставляем для обратной совместимости)
    scoring_breakdown: list[POIScoringBreakdown] = Field(
        default_factory=list,
        description="Детализация скоринга для топ-N кандидатов"
    )

    # Этап 4: Финальный выбор (расширенный)
    selected_poi_id: Optional[UUID] = Field(
        default=None,
        description="ID выбранного POI"
    )
    selected_poi_name: Optional[str] = Field(
        default=None,
        description="Название выбранного POI"
    )
    selection_reason: Optional[str] = Field(
        default=None,
        description="Человекочитаемое объяснение выбора"
    )
    selection_alternatives: list[SelectionAlternative] = Field(
        default_factory=list,
        description="Топ-3 альтернативы (кроме выбранного)"
    )

    # Метаданные
    selection_method: str = Field(
        default="deterministic",
        description="Метод выбора: 'deterministic' или 'llm'"
    )


class GeneratorInputParams(BaseModel):
    """Полные входные параметры генератора маршрута."""
    # Trip context
    trip_id: UUID = Field(description="ID поездки")
    city_name: str = Field(description="Название города")
    city_center_lat: Optional[float] = Field(default=None, description="Широта центра города")
    city_center_lon: Optional[float] = Field(default=None, description="Долгота центра города")

    # Dates
    start_date: date = Field(description="Дата начала поездки")
    end_date: date = Field(description="Дата окончания поездки")
    total_days: int = Field(ge=1, description="Количество дней")

    # User preferences
    pace: str = Field(description="Темп поездки (slow/medium/fast)")
    budget: str = Field(description="Бюджет (low/medium/high)")
    interests: list[str] = Field(default_factory=list, description="Интересы пользователя")
    num_travelers: int = Field(default=1, description="Количество путешественников")

    # Daily routine
    wake_time: time = Field(description="Время пробуждения")
    sleep_time: time = Field(description="Время отхода ко сну")
    breakfast_window: tuple[time, time] = Field(description="Окно завтрака")
    lunch_window: tuple[time, time] = Field(description="Окно обеда")
    dinner_window: tuple[time, time] = Field(description="Окно ужина")

    # Search parameters
    max_radius_km: float = Field(default=20.0, description="Максимальный радиус поиска POI от центра города")
    poi_fetch_limit: int = Field(default=10, description="Лимит кандидатов POI на блок")

    # Filter thresholds
    min_rating: Optional[float] = Field(default=None, description="Минимальный рейтинг POI")

    # Provider settings
    providers_enabled: list[str] = Field(default_factory=list, description="Включенные провайдеры (db, google_places)")

    # Scoring weights (если используются)
    category_match_weight: float = Field(default=10.0, description="Вес совпадения категории")
    tag_overlap_weight: float = Field(default=2.0, description="Вес перекрытия тегов")
    budget_alignment_bonus: float = Field(default=5.0, description="Бонус за соответствие бюджету")


class CandidatePOISample(BaseModel):
    """Образец кандидата POI для trace (сокращенная версия)."""
    poi_id: UUID = Field(description="ID POI")
    name: str = Field(description="Название")
    category: Optional[str] = Field(default=None, description="Категория")
    tags: list[str] = Field(default_factory=list, description="Теги")
    rating: Optional[float] = Field(default=None, description="Рейтинг")
    lat: Optional[float] = Field(default=None, description="Широта")
    lon: Optional[float] = Field(default=None, description="Долгота")
    distance_from_center_km: Optional[float] = Field(default=None, description="Расстояние от центра города")
    rank_score: Optional[float] = Field(default=None, description="Итоговый score от провайдера")


class ProviderCallTrace(BaseModel):
    """Трейс вызова провайдера POI."""
    provider_name: str = Field(description="Название провайдера (db, google_places)")

    # Request params
    request_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Параметры запроса (city, categories, budget, limit)"
    )

    # Response
    candidates_returned: int = Field(default=0, description="Количество возвращенных кандидатов")
    latency_ms: Optional[float] = Field(default=None, description="Задержка в миллисекундах")

    # Status
    status: str = Field(default="success", description="Статус вызова (success, timeout, error)")
    error_message: Optional[str] = Field(default=None, description="Сообщение об ошибке если был")

    # Sample candidates (первые 5 для краткости)
    sample_candidates: list[CandidatePOISample] = Field(
        default_factory=list,
        description="Примеры кандидатов (до 5)"
    )


class FilterRuleTrace(BaseModel):
    """Трейс применения одного правила фильтрации."""
    rule_name: str = Field(description="Название правила фильтрации")
    dropped_count: int = Field(default=0, description="Сколько кандидатов отброшено этим правилом")

    # Примеры отброшенных (до 5)
    examples_dropped: list[POIFilteredOut] = Field(
        default_factory=list,
        description="Примеры отброшенных POI (до 5)"
    )


class RankingTrace(BaseModel):
    """Трейс ранжирования кандидатов."""
    total_candidates: int = Field(default=0, description="Всего кандидатов для ранжирования")

    # Top-N (до 20)
    top_candidates: list[POIScoringBreakdown] = Field(
        default_factory=list,
        description="Топ кандидатов с детализацией score (до 20)"
    )

    # Агрегаты
    avg_score: Optional[float] = Field(default=None, description="Средний score")
    max_score: Optional[float] = Field(default=None, description="Максимальный score")
    min_score: Optional[float] = Field(default=None, description="Минимальный score")


class SelectionAlternative(BaseModel):
    """Альтернативный вариант POI."""
    poi_id: UUID = Field(description="ID POI")
    poi_name: str = Field(description="Название POI")
    rank: int = Field(description="Ранг в списке (1=лучший)")
    score: float = Field(description="Итоговый score")
    reason_not_selected: Optional[str] = Field(
        default=None,
        description="Почему НЕ выбран (если не топ-1)"
    )


class DayOptimizationTrace(BaseModel):
    """Трейс оптимизации маршрута для одного дня."""
    day_number: int = Field(ge=1, description="Номер дня")

    # До оптимизации
    original_order: list[str] = Field(
        default_factory=list,
        description="Порядок POI до оптимизации (названия)"
    )
    original_total_distance_km: Optional[float] = Field(
        default=None,
        description="Суммарное расстояние до оптимизации"
    )

    # После оптимизации
    optimized_order: list[str] = Field(
        default_factory=list,
        description="Порядок POI после оптимизации"
    )
    optimized_total_distance_km: Optional[float] = Field(
        default=None,
        description="Суммарное расстояние после оптимизации"
    )

    # Детали
    reorderable_clusters: list[list[int]] = Field(
        default_factory=list,
        description="Индексы блоков, которые могли быть переставлены"
    )
    permutations_evaluated: int = Field(
        default=0,
        description="Сколько перестановок было оценено"
    )
    optimization_applied: bool = Field(
        default=False,
        description="Была ли применена оптимизация"
    )

    # Improvement
    distance_saved_km: Optional[float] = Field(
        default=None,
        description="Сколько км было сэкономлено"
    )
    distance_saved_percent: Optional[float] = Field(
        default=None,
        description="Процент экономии расстояния"
    )


class RouteTrace(BaseModel):
    """
    Полный трейс генерации маршрута.

    Содержит всю информацию о том, как был сгенерирован маршрут:
    - Входные параметры генератора
    - Какие POI рассматривались
    - Почему некоторые были отфильтрованы
    - Как рассчитывался score
    - Почему был выбран конкретный POI
    - Как оптимизировался порядок посещения
    """
    trip_id: UUID = Field(description="ID поездки")

    # Метаданные генерации
    generation_method: str = Field(
        default="fast_draft",
        description="Метод генерации: 'fast_draft' или 'full_plan'"
    )
    generation_started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Время начала генерации"
    )
    generation_completed_at: Optional[datetime] = Field(
        default=None,
        description="Время завершения генерации"
    )

    # Входные параметры генератора (НОВОЕ - для полного trace)
    generator_input: Optional[GeneratorInputParams] = Field(
        default=None,
        description="Полные входные параметры генератора (только в debug режиме)"
    )

    # Параметры генерации (старые поля для обратной совместимости)
    city: str = Field(description="Город")
    total_days: int = Field(ge=1, description="Количество дней")
    pace: str = Field(description="Темп поездки")
    budget: str = Field(description="Бюджет")
    interests: list[str] = Field(default_factory=list, description="Интересы")

    # Трейсы по блокам
    block_traces: list[BlockSelectionTrace] = Field(
        default_factory=list,
        description="Трейсы выбора POI для каждого блока"
    )

    # Трейсы оптимизации по дням
    day_optimization_traces: list[DayOptimizationTrace] = Field(
        default_factory=list,
        description="Трейсы оптимизации маршрута по дням"
    )

    # Сводная статистика
    total_candidates_considered: int = Field(
        default=0,
        description="Всего рассмотрено кандидатов"
    )
    total_candidates_filtered: int = Field(
        default=0,
        description="Всего отфильтровано кандидатов"
    )
    total_pois_selected: int = Field(
        default=0,
        description="Всего выбрано POI"
    )

    # Источники данных
    data_sources_used: list[str] = Field(
        default_factory=list,
        description="Использованные источники данных (db, google_places, etc.)"
    )

    # LLM usage
    llm_calls_made: int = Field(
        default=0,
        description="Количество вызовов LLM"
    )
    llm_tokens_used: Optional[int] = Field(
        default=None,
        description="Использовано токенов LLM"
    )

    # Warnings и fallbacks
    warnings: list[str] = Field(
        default_factory=list,
        description="Предупреждения во время генерации"
    )
    fallbacks_used: list[str] = Field(
        default_factory=list,
        description="Использованные fallback-механизмы"
    )

    def add_block_trace(self, trace: BlockSelectionTrace) -> None:
        """Добавить трейс блока и обновить статистику."""
        self.block_traces.append(trace)
        self.total_candidates_considered += trace.candidates_fetched
        self.total_candidates_filtered += len(trace.filtered_out)
        if trace.selected_poi_id:
            self.total_pois_selected += 1

    def add_day_optimization(self, trace: DayOptimizationTrace) -> None:
        """Добавить трейс оптимизации дня."""
        self.day_optimization_traces.append(trace)

    def add_warning(self, warning: str) -> None:
        """Добавить предупреждение."""
        self.warnings.append(warning)

    def add_fallback(self, fallback: str) -> None:
        """Добавить информацию об использованном fallback."""
        self.fallbacks_used.append(fallback)

    def finalize(self) -> None:
        """Финализировать трейс (установить время завершения)."""
        self.generation_completed_at = datetime.utcnow()

    def get_block_trace(self, day_number: int, block_index: int) -> Optional[BlockSelectionTrace]:
        """Получить трейс конкретного блока."""
        for trace in self.block_traces:
            if trace.day_number == day_number and trace.block_index == block_index:
                return trace
        return None

    def get_selection_summary(self, poi_id: UUID) -> Optional[str]:
        """Получить краткое объяснение выбора POI."""
        for trace in self.block_traces:
            if trace.selected_poi_id == poi_id:
                return trace.selection_reason
        return None


class RouteTraceResponse(BaseModel):
    """Response schema для RouteTrace в API."""
    trip_id: UUID
    trace: RouteTrace

    # Краткая сводка для UI
    summary: str = Field(
        default="",
        description="Краткая сводка генерации для отображения пользователю"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                "trace": {
                    "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                    "generation_method": "fast_draft",
                    "city": "Paris",
                    "total_days": 3,
                    "pace": "medium",
                    "budget": "medium",
                    "interests": ["food", "culture"],
                    "total_candidates_considered": 150,
                    "total_candidates_filtered": 95,
                    "total_pois_selected": 18,
                    "data_sources_used": ["db", "google_places"],
                    "llm_calls_made": 1,
                    "warnings": [],
                    "fallbacks_used": []
                },
                "summary": "Рассмотрено 150 мест, выбрано 18 лучших для вашего маршрута."
            }
        }


def create_selection_explanation(
    poi_name: str,
    scoring: POIScoringBreakdown,
    block_type: str,
) -> str:
    """
    Создать человекочитаемое объяснение выбора POI.

    Args:
        poi_name: Название POI
        scoring: Детализация скоринга
        block_type: Тип блока

    Returns:
        Строка с объяснением, например:
        "Выбрано за: высокий рейтинг (4.8), соответствует бюджету, близко к предыдущему месту"
    """
    reasons = []

    factors = scoring.factors

    # Rating
    if ScoringFactor.RATING in factors and factors[ScoringFactor.RATING] >= 4.0:
        reasons.append(f"высокий рейтинг ({factors[ScoringFactor.RATING]:.1f})")

    # Category match
    if ScoringFactor.CATEGORY_MATCH in factors and factors[ScoringFactor.CATEGORY_MATCH] > 0:
        reasons.append("соответствует категории")

    # Budget
    if ScoringFactor.BUDGET_ALIGNMENT in factors and factors[ScoringFactor.BUDGET_ALIGNMENT] > 0:
        reasons.append("подходит под бюджет")

    # Hotel proximity
    if ScoringFactor.HOTEL_PROXIMITY in factors and factors[ScoringFactor.HOTEL_PROXIMITY] > -5:
        reasons.append("удобное расположение")

    # Diversity
    if ScoringFactor.DIVERSITY_BONUS in factors and factors[ScoringFactor.DIVERSITY_BONUS] > 0:
        reasons.append("разнообразие маршрута")

    # LLM preference
    if ScoringFactor.LLM_PREFERENCE in factors and factors[ScoringFactor.LLM_PREFERENCE] > 0:
        reasons.append("рекомендовано AI")

    if not reasons:
        reasons.append("лучший доступный вариант")

    return f"Выбрано за: {', '.join(reasons)}"
