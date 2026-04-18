# Live Audio Guide — Content Pipeline

## 1. Обзор пайплайна

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ИСТОЧНИК: City Seeder (guide_knowledge_cards)             │
│     guide_points (poi + connector) + guide_edges + guide_zones              │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Стадия 1: DRAFT GENERATION │  полная автоматизация
                    │   BFS-оркестратор + io.net   │  ~76 000 блоков
                    │   LLM batch (параллельно)    │  ≈ 24–36 ч на MVP
                    └──────────────┬──────────────┘
                                   │  generation_status: pending → draft
                    ┌──────────────▼──────────────┐
                    │  Стадия 2: COHERENCE         │  автоматизация с LLM
                    │  VALIDATION                  │  попарная + сквозная
                    │  LLM-валидатор               │  coherence_score 1–5
                    └──────┬───────────────┬───────┘
                           │ score ≥ 4     │ score < 4
                           │               │  (до 3 retry → needs_manual_review)
             draft → validated      draft → needs_manual_review
                           │               │
                    ┌──────▼───────────────▼───────┐
                    │   Стадия 3: MANUAL REVIEW     │  точечный ручной QA
                    │   Admin UI (Review API)       │  только needs_manual_review
                    │   + batch accept ≥ 4.5        │  + топ-POI / вступления
                    └──────────────┬────────────────┘
                                   │  generation_status: reviewed
                    ┌──────────────▼──────────────┐
                    │  Стадия 4: AUDIO SYNTHESIS   │  batch ElevenLabs TTS
                    │  ElevenLabs → FFmpeg → S3    │  synthesizing → synthesized
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  PRODUCTION: CDN-аудио       │
                    │  guide_content_blocks        │
                    │  audio_url ≠ null            │
                    └─────────────────────────────┘
```

### Объём контента для MVP (5 городов)

| Параметр | Значение |
|----------|----------|
| Городов | 5 (Москва, Париж, Барселона, Стамбул, Шанхай) |
| Зон | ~15 (2–4 на город) |
| POI-точек на зону | ~50 |
| Connector-точек на зону | ~30 |
| Итого точек | ~1 200 |
| Голосов × языков | 4 style_group × 2 языка = 8 комбинаций |
| Блоков на точку (полный: main × 2 detail + bonus × 2 detail + recap × 1) | (2+2+1) × 8 = **40** |
| Переходов (ребро × 3 варианта; всегда standard) | ~4 соседа × 2 направления × 3 варианта = 24 блока/точку |
| Итого контентных блоков (полный: brief + standard) | ~1 200 × (40 + 24) ≈ **76 800** |
| Zone_transition блоков (~15 зон × 2 направления × 8) | ~240 |
| **Итого (полный)** | **~77 040 блоков** |
| **MVP (только standard для main/bonus/recap)** | ~1 200 × (24 + 24) + 240 ≈ **~57 840 блоков** |

> **Рекомендация MVP:** генерировать только `standard` detail_level для main и bonus (÷2 относительно полного набора). Recap всегда standard. Итого ~57 840 блоков. `Brief` добавить в следующей итерации после валидации продукта.

---

## 2. Модель данных

Пайплайн работает исключительно с уже существующими таблицами из `ARCHITECTURE.md`. Новых таблиц не требуется.

### Используемые таблицы

| Таблица | Роль в пайплайне |
|---------|-----------------|
| `guide_knowledge_cards` | Входные данные для промтов (wikipedia_summary, wikidata_facts, google_place_data, street_name) |
| `guide_points` | Список точек для генерации; point_type определяет шаблон промта |
| `guide_edges` | Структура графа; определяет какие transition-блоки нужны |
| `guide_zones` | Метаданные зоны (theme, name) — попадают в промт как контекст |
| `guide_voices` | style_group + language → параметры промта; elevenlabs_voice_id → синтез |
| `guide_content_blocks` | Основная таблица: текст, статус, оценка, аудио URL; содержит `zone_id` (денормализовано) и `detail_level` |
| `guide_content_jobs` | Трекинг job-ов по стадиям (job_type: generate_drafts / validate / synthesize) |

### Жизненный цикл `generation_status`

```
pending
  │
  ├─ [Стадия 1: LLM генерирует текст]
  ▼
draft
  │
  ├─ [Стадия 2: LLM-валидатор проверяет связность]
  │
  Для transition/zone_transition:
  ├─ score ≥ 4.0 ─────────────────────────────► validated
  ├─ score 3.5–3.99 (retry 1–3) ─────────────► draft (перегенерация)
  │   └─ после 3 retry < 4.0 ───────────────► needs_manual_review
  └─ score < 3.5 (сразу) ────────────────────► needs_manual_review

  Для main/bonus/recap:
  ├─ score ≥ 3.5 ─────────────────────────────► validated
  └─ score < 3.5 ─────────────────────────────► needs_manual_review
                                                │
  [Стадия 3: ручной ревью] ◄──────────────────┘
  accept / edit / regenerate
       │
       ▼
    reviewed
       │
       ├─ [Стадия 4: TTS]
       ▼
  synthesizing ──► synthesized
       │
       └─ при ошибке ──► failed
```

### Поля `guide_content_blocks`, задействованные пайплайном

```python
# Заполняются на Стадии 1
text_script            # сгенерированный LLM текст
generation_status      # pending → draft
generated_at           # timestamp генерации
language               # явный язык блока
detail_level           # brief | standard; добавлено: нужен для различения версий нарратива
zone_id                # UUID зоны; добавлено: денормализован для S3-ключа, передаётся при вставке
variant_index          # 0/1/2 для transition-блоков

# Заполняются на Стадии 2
coherence_score        # 1.0–5.0, от LLM-валидатора
generation_status      # draft → validated | needs_manual_review

# Заполняются на Стадии 3
review_notes           # комментарий редактора
reviewed_by            # login редактора
reviewed_at            # timestamp
generation_status      # needs_manual_review → reviewed

# Заполняются на Стадии 4
audio_url              # CDN URL итогового файла
audio_duration_seconds # длительность в секундах
synthesized_at         # timestamp синтеза
generation_status      # reviewed → synthesizing → synthesized
```

### Прогресс job в `guide_content_jobs.progress_json`

```json
{
  "total": 4800,
  "processed": 1240,
  "draft": 1180,
  "failed": 60,
  "retry_count": 42,
  "current_bfs_level": 3,
  "bfs_total_levels": 8
}
```

---

## 3. Система промт-шаблонов

### 3.1. Базовая параметризация

Каждый промт параметризуется по четырём осям:

| Ось | Значения | Влияние на промт |
|-----|----------|-----------------|
| `style_group` | academic / friendly / dramatic / minimal | Тон, лексика, структура |
| `language` | en / ru | Язык вывода + культурный регистр |
| `detail_level` | brief / standard | Длина нарратива |
| `content_type` | main / bonus / transition / zone_transition / recap | Шаблон и формат JSON |

### 3.2. Описание персонажей в промтах

```python
# src/guide/application/content_pipeline/prompt_templates.py

VOICE_PERSONAS = {
    "academic": {
        "en": (
            "You are a knowledgeable historian and academic guide. "
            "Your tone is calm, precise, and intellectually rich. "
            "Use historical context, architectural terms, and factual depth. "
            "Avoid colloquialisms. Write as if lecturing a curious, educated traveller."
        ),
        "ru": (
            "Ты — эрудированный историк и академический гид. "
            "Твой тон спокойный, точный, интеллектуально насыщенный. "
            "Используй исторический контекст, архитектурные термины и глубину фактов. "
            "Избегай разговорных выражений. Пиши, как будто ведёшь лекцию для образованного путешественника."
        ),
    },
    "friendly": {
        "en": (
            "You are a warm, witty local friend who knows every hidden corner of the city. "
            "Your tone is conversational, enthusiastic, and personal — share insider tips, "
            "local legends, and the kind of stories only a true local would know. "
            "Use contractions, light humour, and vivid comparisons."
        ),
        "ru": (
            "Ты — тёплый, остроумный друг-местный, который знает каждый уголок города. "
            "Твой тон разговорный, живой и личный — делись инсайдерскими историями и легендами, "
            "которые знают только настоящие местные. Используй сокращения и яркие сравнения."
        ),
    },
    "dramatic": {
        "en": (
            "You are a captivating storyteller — think of yourself as a documentary narrator. "
            "Build suspense, use vivid sensory language, and bring history to life cinematically. "
            "Every place has a dramatic story; find it and tell it with atmosphere and intrigue."
        ),
        "ru": (
            "Ты — захватывающий сторителлер, как нарратор документального фильма. "
            "Нагнетай саспенс, используй яркие образы и оживляй историю кинематографично. "
            "У каждого места есть драматическая история — найди её и расскажи с атмосферой и интригой."
        ),
    },
    "minimal": {
        "en": (
            "You are a concise, no-nonsense guide. Deliver only the most essential and "
            "interesting facts. No filler, no padding. "
            "Think of it as a sharp caption, not an essay."
        ),
        "ru": (
            "Ты — лаконичный гид без лишних слов. Только самые важные и интересные факты. "
            "Никакой воды. Думай об этом как о ёмкой подписи, а не эссе."
        ),
    },
}

WORD_COUNTS = {
    "main":    {"brief": "60–80",   "standard": "120–160"},
    "bonus":   {"brief": "40–60",   "standard": "80–110"},
    "transition": {"brief": "15–25", "standard": "15–25"},   # одинаково, transition всегда короткий
    "zone_transition": {"brief": "20–35", "standard": "20–35"},
    "recap":   {"brief": "15–25",   "standard": "15–25"},
}
```

### 3.3. Формирование контекста точки

```python
def build_point_context(
    point: GuidePoint,
    card: KnowledgeCard,
    zone: GuideZone,
    neighbor_narratives: dict[UUID, str],   # уже сгенерированные нарративы соседей
    language: str,
) -> str:
    """Формирует блок контекста для подстановки в промт."""

    ctx_parts = []

    # Основные данные точки
    ctx_parts.append(f"Place name: {point.name or 'unnamed connector point'}")
    ctx_parts.append(f"Zone: {zone.name} ({zone.theme or 'mixed'} theme), {zone.city_name}")

    # Карточка знаний
    if card.card_type == "poi":
        if card.wikipedia_summary:
            ctx_parts.append(f"Wikipedia: {card.wikipedia_summary[:800]}")
        if card.wikidata_facts:
            facts = card.wikidata_facts
            fact_lines = []
            for k, v in facts.items():
                if v:
                    fact_lines.append(f"  {k}: {v}")
            if fact_lines:
                ctx_parts.append("Known facts:\n" + "\n".join(fact_lines))
        if card.google_place_data:
            summary = (card.google_place_data.get("editorial_summary") or {}).get("overview", "")
            if summary:
                ctx_parts.append(f"Google summary: {summary}")
    elif card.card_type == "street_context":
        ctx_parts.append(f"Street: {card.street_name or 'unnamed street'}")
        ctx_parts.append("This is a connector point on a pedestrian path (no named POI).")

    # Нарративы соседей (для избежания повторов)
    if neighbor_narratives:
        ctx_parts.append("Nearby points already narrated (avoid repeating these themes):")
        for neighbor_name, narrative_excerpt in neighbor_narratives.items():
            ctx_parts.append(f"  — {neighbor_name}: «{narrative_excerpt[:120]}...»")

    return "\n\n".join(ctx_parts)
```

### 3.4. Промт: `main` нарратив (POI)

```python
MAIN_NARRATIVE_PROMPT = """\
{persona_description}

You are recording an audio guide segment for a walking tour app.
The listener is physically standing near this place RIGHT NOW.

{point_context}

Write the MAIN narrative for this place.

Requirements:
- Length: {word_count} words
- Language: {language_name}
- Write for LISTENING, not reading (no bullet points, no headers, no lists)
- Use vivid, sensory language — what the listener can see, smell, hear around them
- Do NOT mention "according to Wikipedia" or cite sources by name
- End with a natural pause point (a complete thought, not mid-story)
- Do NOT suggest "now let's move on" — transitions are handled separately

Respond in JSON:
{{
  "text_script": "<the narrative text>",
  "themes_covered": ["<theme1>", "<theme2>"],
  "suggested_bonus_hook": "<one sentence tease for bonus content, in {language_name}>"
}}
"""
```

### 3.5. Промт: `main` нарратив (connector)

```python
CONNECTOR_NARRATIVE_PROMPT = """\
{persona_description}

You are recording an audio guide segment for a walking tour app.
The listener is walking along a street between two points of interest.

{point_context}

Write a SHORT connector narrative — a brief observation about this street/neighbourhood
that bridges the listener between notable places.

Requirements:
- Length: {word_count} words (keep it tight — this is a walking bridge, not a lecture)
- Language: {language_name}
- Focus on: street character, architecture style, local life visible from this spot,
  or a brief historical/cultural snippet about this street
- Do NOT invent specific historical facts not in the context
- Sound natural for someone walking past

Respond in JSON:
{{
  "text_script": "<the connector narrative>",
  "themes_covered": ["<theme1>"]
}}
"""
```

### 3.6. Промт: `bonus` контент

```python
BONUS_CONTENT_PROMPT = """\
{persona_description}

The listener has paused near this place and wants to hear more.
They have already heard the main narrative. Now give them the BONUS content —
deeper details, a hidden story, an unusual fact, or a personal anecdote.

{point_context}
Main narrative already played:
«{main_narrative_text}»

Requirements:
- Length: {word_count} words
- Language: {language_name}
- Do NOT repeat anything from the main narrative
- Reveal something surprising, counter-intuitive, or rarely known
- Can be more personal and anecdotal than main content

Respond in JSON:
{{
  "text_script": "<bonus content text>"
}}
"""
```

### 3.7. Промт: `transition` переходная фраза

Генерируется **3 варианта** за один вызов LLM (variant_index 0/1/2):

```python
TRANSITION_PROMPT = """\
{persona_description}

Write THREE distinct spoken transition phrases for an audio walking guide.

The listener is walking:
FROM: {from_point_name} ({from_themes})
TOWARD: {to_point_name}

Context of FROM point (last 2 sentences of its narrative):
«{from_narrative_tail}»

Context of TO point (first 2 sentences of its narrative):
«{to_narrative_head}»

Requirements:
- Each phrase: 15–25 words, {language_name}
- Each variant must sound distinctly different in opening and approach
- Reference the FROM place naturally (acknowledge leaving it)
- Build curiosity or anticipation for the TO place
- Do NOT say "now let's go to" or "next we will see" (too robotic)
- Contractions and natural speech OK
- Maintain {style_description} throughout

Respond in JSON:
{{
  "variants": [
    {{"text_script": "<variant 0>"}},
    {{"text_script": "<variant 1>"}},
    {{"text_script": "<variant 2>"}}
  ]
}}
"""
```

### 3.8. Промт: `zone_transition`

```python
ZONE_TRANSITION_PROMPT = """\
{persona_description}

The listener is physically crossing from one neighbourhood into another.

FROM zone: {from_zone_name} — theme: {from_zone_theme}
TO zone: {to_zone_name} — theme: {to_zone_theme}

Write a zone transition phrase that:
- Acknowledges the character of the zone being left (1 sentence)
- Frames the new zone with anticipation (1–2 sentences)
- Total: 20–35 words, {language_name}
- Sounds like a natural guide transition, not a GPS announcement

Respond in JSON:
{{
  "text_script": "<zone transition text>"
}}
"""
```

### 3.9. Промт: `recap` (возврат после паузы)

> **Примечание:** recap генерируется один раз per (point × voice × language), без учёта detail_level.
> `detail_level` для recap в БД всегда = `'standard'` (recap всегда короткий, 15–25 слов).
> Генерируется для КАЖДОЙ точки (poi и connector), после main-нарратива (нужен main_text как контекст).

```python
RECAP_PROMPT = """\
{persona_description}

The listener has just resumed their audio guide after a pause.
Briefly re-orient them with a 1–2 sentence recap.

Last point visited: {last_point_name}
Last main narrative (excerpt): «{last_narrative_excerpt}»

Requirements:
- 15–25 words, {language_name}
- Opens with something like "We left off at..." or equivalent in style
- Do NOT restart the main narrative — just orient and hand off
- Sound warm and welcoming, not mechanical

Respond in JSON:
{{
  "text_script": "<recap text>"
}}
"""
```

---

## 4. Стадия 1: Draft Generation

### 4.1. Точка входа

```bash
# CLI
python -m src.guide.application.content_pipeline.draft_generator \
    --zone-id <UUID> \
    --voice-ids <UUID1,UUID2,...> \   # если не указано — все активные голоса
    --languages en,ru \
    --force-regenerate false          # force_regenerate=True: обновляет даже блоки со статусом != pending
                                      # force_regenerate=False (default): пропускает блоки с уже существующим draft/validated/reviewed

# Admin API (запускает async background task)
POST /api/guide/admin/content/generate
{
  "zone_id": "...",
  "voice_ids": null,
  "force_regenerate": false
}
→ { "job_id": "...", "blocks_queued": 4800 }
```

### 4.2. BFS-оркестратор

**Ключевая идея:** при генерации нарратива для точки N в промт подставляются уже готовые нарративы её соседей. BFS гарантирует, что когда мы обрабатываем точку N, нарративы её уже посещённых соседей (уровни 0..N-1) уже существуют.

```python
# src/guide/application/content_pipeline/draft_generator.py

import asyncio
from uuid import UUID

async def generate_zone_drafts(
    zone_id: UUID,
    voice_ids: list[UUID],
    languages: list[str],
    job_id: UUID,
    db: AsyncSession,
) -> None:
    """BFS-обход графа зоны с параллельной генерацией на каждом уровне."""

    points = await db.fetch_active_points(zone_id)
    edges   = await db.fetch_edges(zone_id)

    # Строим adjacency map: point_id → [neighbor_ids]
    adj: dict[UUID, list[UUID]] = {p.id: [] for p in points}
    for e in edges:
        adj[e.from_point_id].append(e.to_point_id)

    # Центральная точка — ближайшая к центроиду зоны
    zone = await db.fetch_zone(zone_id)
    start_point = _find_central_point(points, zone.centroid)

    # BFS (без deque — обрабатываем целыми уровнями)
    visited: set[UUID] = {start_point.id}
    current_level: list[UUID] = [start_point.id]

    # Кэш: point_id → {"main": text, "name": str}  (для передачи в промты соседей)
    narrative_cache: dict[UUID, dict] = {}

    bfs_level = 0
    total_levels = _estimate_bfs_depth(points, adj)

    while current_level:
        await _update_job_progress(
            job_id, db,
            current_bfs_level=bfs_level,
            bfs_total_levels=total_levels,
        )

        # Параллелизация: точки одного уровня без общих соседей → параллельно
        independent_groups = _split_independent(current_level, adj)

        for group in independent_groups:
            tasks = [
                _generate_point_all_voices(
                    point_id=pid,
                    voice_ids=voice_ids,
                    languages=languages,
                    zone=zone,
                    narrative_cache=narrative_cache,
                    db=db,
                )
                for pid in group
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for pid, result in zip(group, results):
                if isinstance(result, Exception):
                    await _mark_point_failed(pid, voice_ids, languages, db)
                else:
                    narrative_cache[pid] = result  # {"main_en": "...", "main_ru": "...", "name": "..."}

        # Формируем следующий уровень BFS
        next_level: list[UUID] = []
        for pid in current_level:
            for neighbor_id in adj.get(pid, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    next_level.append(neighbor_id)

        current_level = next_level
        bfs_level += 1

    # После main/bonus — генерируем transition блоки для всех рёбер
    await _generate_all_transitions(zone_id, voice_ids, languages, narrative_cache, db)

    await _finalize_job(job_id, db, status="complete")


def _split_independent(
    point_ids: list[UUID],
    adj: dict[UUID, list[UUID]],
) -> list[list[UUID]]:
    """
    Делит точки одного BFS-уровня на независимые группы:
    две точки «зависимы», если одна является соседом другой.
    Независимые группы можно генерировать параллельно без риска
    того, что промт одной ссылается на нарратив другой (его ещё нет).
    """
    # Простой жадный раскрас: добавляем точку в группу, если у неё нет
    # соседей уже добавленных в эту группу.
    groups: list[list[UUID]] = []
    assigned: set[UUID] = set()

    for pid in point_ids:
        placed = False
        for group in groups:
            group_set = set(group)
            neighbors = set(adj.get(pid, []))
            if not (group_set & neighbors):  # нет общих соседей
                group.append(pid)
                assigned.add(pid)
                placed = True
                break
        if not placed:
            groups.append([pid])
            assigned.add(pid)

    return groups
```

### 4.3. Генерация одной точки

```python
async def _generate_point_all_voices(
    point_id: UUID,
    voice_ids: list[UUID],
    languages: list[str],
    zone: GuideZone,
    narrative_cache: dict,
    db: AsyncSession,
) -> dict:
    """Генерирует main + bonus для всех голосов × языков одной точки."""

    point = await db.fetch_point(point_id)
    card  = await db.fetch_knowledge_card(point_id)
    neighbors = await db.fetch_neighbors(point_id)  # guide_points

    result_cache = {"name": point.name}

    for voice in await db.fetch_voices(voice_ids):
        for language in languages:
            persona = VOICE_PERSONAS[voice.style_group][language]

            # Нарративы уже сгенерированных соседей (из кэша)
            neighbor_narratives = {
                narrative_cache[n.id]["name"]: narrative_cache[n.id].get(f"main_{language}", "")
                for n in neighbors
                if n.id in narrative_cache
            }

            # Формируем контекст
            point_context = build_point_context(
                point, card, zone, neighbor_narratives, language
            )

            # Определяем шаблон промта
            template = (
                CONNECTOR_NARRATIVE_PROMPT
                if point.point_type == "connector"
                else MAIN_NARRATIVE_PROMPT
            )

            # MVP: можно передать detail_levels=["standard"] для экономии
            for detail_level in ("brief", "standard"):
                word_count = WORD_COUNTS["main"][detail_level]

                response = await _llm_generate_with_retry(
                    prompt=template.format(
                        persona_description=persona,
                        point_context=point_context,
                        word_count=word_count,
                        language_name=_language_name(language),
                        style_description=voice.style_group,
                    ),
                    expected_keys=["text_script"],
                    max_retries=3,
                )

                # Сохраняем блок в БД (upsert по partial UNIQUE idx_guide_content_uq_no_edge)
                await db.upsert_content_block(
                    GuideContentBlock(
                        point_id=point_id,
                        zone_id=zone.id,       # добавлено: денормализован для S3-ключа
                        voice_id=voice.id,
                        language=language,
                        detail_level=detail_level,  # добавлено: нужен для различения brief/standard
                        content_type="main",
                        variant_index=0,
                        text_script=response["text_script"],
                        generation_status="draft",
                        generated_at=utcnow(),
                    ),
                    conflict_index="idx_guide_content_uq_no_edge",
                    update_fields=["text_script", "generation_status", "generated_at"],
                )

                # Кэшируем для передачи соседям (только standard, первый голос)
                if detail_level == "standard" and voice == voice_ids[0]:
                    result_cache[f"main_{language}"] = response["text_script"][:300]

            # Bonus (MVP: только standard; brief добавить в следующей итерации)
            for detail_level in ("brief", "standard"):
                main_text = await db.get_content_text(
                    point_id, voice.id, language, "main", detail_level=detail_level
                )
                bonus_response = await _llm_generate_with_retry(
                    prompt=BONUS_CONTENT_PROMPT.format(
                        persona_description=persona,
                        point_context=point_context,
                        main_narrative_text=main_text[:400],
                        word_count=WORD_COUNTS["bonus"][detail_level],
                        language_name=_language_name(language),
                    ),
                    expected_keys=["text_script"],
                    max_retries=3,
                )
                await db.upsert_content_block(
                    GuideContentBlock(
                        point_id=point_id,
                        zone_id=zone.id,
                        voice_id=voice.id,
                        language=language,
                        detail_level=detail_level,
                        content_type="bonus",
                        variant_index=0,
                        text_script=bonus_response["text_script"],
                        generation_status="draft",
                        generated_at=utcnow(),
                    ),
                    conflict_index="idx_guide_content_uq_no_edge",
                    update_fields=["text_script", "generation_status", "generated_at"],
                )

            # Recap — генерируется один раз per (voice × language), detail_level всегда 'standard'
            # Нужен main_text standard как контекст для промта
            main_text_standard = await db.get_content_text(
                point_id, voice.id, language, "main", detail_level="standard"
            )
            recap_response = await _llm_generate_with_retry(
                prompt=RECAP_PROMPT.format(
                    persona_description=persona,
                    last_point_name=point.name or "this location",
                    last_narrative_excerpt=main_text_standard[:200],
                    language_name=_language_name(language),
                ),
                expected_keys=["text_script"],
                max_retries=3,
            )
            await db.upsert_content_block(
                GuideContentBlock(
                    point_id=point_id,
                    zone_id=zone.id,
                    voice_id=voice.id,
                    language=language,
                    detail_level="standard",  # recap всегда standard
                    content_type="recap",
                    variant_index=0,
                    text_script=recap_response["text_script"],
                    generation_status="draft",
                    generated_at=utcnow(),
                ),
                conflict_index="idx_guide_content_uq_no_edge",
                update_fields=["text_script", "generation_status", "generated_at"],
            )

    return result_cache
```

### 4.4. Генерация transition-блоков

```python
async def _generate_all_transitions(
    zone_id: UUID,
    voice_ids: list[UUID],
    languages: list[str],
    narrative_cache: dict,
    db: AsyncSession,
) -> None:
    """Генерирует transition-блоки для всех рёбер зоны × голос × язык."""
    edges = await db.fetch_edges(zone_id)

    # Параллельно по рёбрам (между рёбрами нет зависимостей)
    semaphore = asyncio.Semaphore(10)  # max 10 параллельных LLM вызовов

    tasks = [
        _generate_edge_transitions(
            edge, voice_ids, languages, narrative_cache, db, semaphore
        )
        for edge in edges
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _generate_edge_transitions(
    edge: GuideEdge,
    voice_ids: list[UUID],
    languages: list[str],
    narrative_cache: dict,
    db: AsyncSession,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        from_point = await db.fetch_point(edge.from_point_id)
        to_point   = await db.fetch_point(edge.to_point_id)

        from_narrative = narrative_cache.get(edge.from_point_id, {})
        to_narrative   = narrative_cache.get(edge.to_point_id, {})

        for voice in await db.fetch_voices(voice_ids):
            for language in languages:
                persona = VOICE_PERSONAS[voice.style_group][language]

                from_text = from_narrative.get(f"main_{language}", "")
                to_text   = to_narrative.get(f"main_{language}", "")

                response = await _llm_generate_with_retry(
                    prompt=TRANSITION_PROMPT.format(
                        persona_description=persona,
                        from_point_name=from_point.name or "current location",
                        from_themes=", ".join(from_narrative.get("themes", [])),
                        to_point_name=to_point.name or "next location",
                        from_narrative_tail=_tail(from_text, sentences=2),
                        to_narrative_head=_head(to_text, sentences=2),
                        language_name=_language_name(language),
                        style_description=voice.style_group,
                    ),
                    expected_keys=["variants"],
                    max_retries=3,
                )

                # 3 варианта → 3 блока с variant_index 0/1/2
                # transition: detail_level всегда 'standard' (длина фиксирована)
                zone_id = await db.get_zone_id_for_point(edge.from_point_id)  # денормализован для S3-ключа
                for idx, variant in enumerate(response.get("variants", [])[:3]):
                    await db.upsert_content_block(
                        GuideContentBlock(
                            point_id=edge.from_point_id,
                            zone_id=zone_id,  # добавлено: нужен для _build_s3_key
                            voice_id=voice.id,
                            language=language,
                            detail_level="standard",  # transitions всегда standard
                            content_type="transition",
                            edge_id=edge.id,
                            variant_index=idx,
                            text_script=variant["text_script"],
                            generation_status="draft",
                            generated_at=utcnow(),
                        ),
                        conflict_index="idx_guide_content_uq_with_edge",  # edge_id IS NOT NULL
                        update_fields=["text_script", "generation_status", "generated_at"],
                    )
```

### 4.5. Retry-логика при невалидном ответе LLM

```python
async def _llm_generate_with_retry(
    prompt: str,
    expected_keys: list[str],
    max_retries: int = 3,
) -> dict:
    """Вызов LLM с retry при невалидном JSON или отсутствии ожидаемых полей."""

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            raw = await llm_client.complete(
                prompt=prompt,
                model=settings.guide_narrative_model,
                max_tokens=600,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(raw)

            # Проверка наличия обязательных полей
            for key in expected_keys:
                if key not in parsed:
                    raise ValueError(f"Missing key '{key}' in LLM response")

            # Проверка длины text_script (не пустой)
            if "text_script" in parsed and len(parsed["text_script"].strip()) < 20:
                raise ValueError("text_script too short")

            return parsed

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            if attempt < max_retries - 1:
                # Добавляем инструкцию исправить предыдущую ошибку в следующий промт
                prompt += f"\n\n[Previous attempt failed: {e}. Please ensure valid JSON with all required keys.]"
                await asyncio.sleep(0.5 * (attempt + 1))  # экспоненциальный backoff

    # После max_retries неудач — пишем заглушку-маркер для ручного ревью
    logger.error(f"LLM generation failed after {max_retries} attempts: {last_error}")
    raise GenerationError(f"Failed after {max_retries} retries: {last_error}")
```

### 4.6. Rate limiting и управление очередью

```python
# Настройки в src/config.py (Pydantic Settings)
guide_narrative_model: str = "meta-llama/Llama-3.3-70B-Instruct"
guide_content_max_parallel_llm: int = 20    # max параллельных LLM вызовов
guide_content_llm_rpm_limit: int = 60       # requests per minute (io.net limit)
guide_content_llm_timeout_seconds: int = 30

# Реализация через asyncio.Semaphore + token bucket
_llm_semaphore = asyncio.Semaphore(settings.guide_content_max_parallel_llm)
_rpm_limiter = TokenBucketRateLimiter(
    rate=settings.guide_content_llm_rpm_limit,
    per_seconds=60
)

async def llm_complete_rate_limited(prompt: str, **kwargs) -> str:
    async with _llm_semaphore:
        await _rpm_limiter.acquire()
        return await llm_client.complete(prompt=prompt, **kwargs)
```

---

## 5. Стадия 2: Coherence Validation

```python
# Пороги по типу контента — единый источник истины для валидатора
COHERENCE_THRESHOLDS = {
    "transition": 4.0,       # строже: клей между нарративами, от качества зависит бесшовность
    "zone_transition": 4.0,
    "main": 3.5,             # мягче: каждый блок самодостаточен
    "bonus": 3.5,
    "recap": 3.5,
}
```

### 5.1. Попарная валидация переходов

Запускается после завершения Стадии 1 (или вручную через API).

```
Для каждого guide_content_blocks WHERE content_type='transition' AND generation_status='draft':

  Формируем «тройку»:
    [последние 2 предл. нарратива A (main, same voice/lang)]
    + [transition text A→B]
    + [первые 2 предл. нарратива B (main, same voice/lang)]

  → LLM-валидатор → coherence_score 1.0–5.0

  Если score ≥ 4.0 → generation_status = 'validated'
  Если 3.5 ≤ score < 4.0 → retry (до 3 раз, каждый раз перегенерируем transition)
  Если score < 3.5 → generation_status = 'needs_manual_review'
  Если после 3 retry score всё ещё < 4.0 → 'needs_manual_review'
```

#### Промт LLM-валидатора

```python
COHERENCE_VALIDATION_PROMPT = """\
You are a quality validator for an audio walking guide.
Evaluate the smoothness of this narrative sequence:

[END OF POINT A — last 2 sentences]:
«{narrative_a_tail}»

[TRANSITION PHRASE A→B]:
«{transition_text}»

[START OF POINT B — first 2 sentences]:
«{narrative_b_head}»

Rate on a scale of 1.0–5.0 across these four dimensions:

1. SEMANTIC COHERENCE — Does the transition logically connect A to B?
   Are there awkward topic jumps or contradictions?

2. STYLE CONSISTENCY — Does the transition match the tone and register of both narrations?
   (Voice style: {style_group}, Language: {language})

3. SPATIAL ACCURACY — Does the transition phrase make physical sense for someone
   walking from A toward B? (bearing: {bearing_description})

4. NO REPETITION — Does the transition avoid repeating facts/phrases from A's narrative?

Respond in JSON:
{{
  "semantic_coherence": <1.0–5.0>,
  "style_consistency": <1.0–5.0>,
  "spatial_accuracy": <1.0–5.0>,
  "no_repetition": <1.0–5.0>,
  "overall_score": <weighted average: semantic×0.35 + style×0.25 + spatial×0.25 + no_rep×0.15>,
  "issues": "<brief description of main problem, or 'none'>",
  "suggested_fix": "<one-sentence suggestion for improvement, or 'none'>"
}}
"""
```

#### Алгоритм попарной валидации

```python
# src/guide/application/content_pipeline/coherence_validator.py

async def validate_zone_transitions(
    zone_id: UUID,
    language: str | None,
    job_id: UUID,
    db: AsyncSession,
) -> None:
    """Попарная валидация всех transition-блоков зоны."""

    blocks = await db.fetch_content_blocks(
        zone_id=zone_id,
        content_type="transition",
        generation_status="draft",
        language=language,
    )

    semaphore = asyncio.Semaphore(15)
    tasks = [
        _validate_transition_block(block, db, semaphore)
        for block in blocks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await _finalize_validation_job(job_id, db, results)


async def _validate_transition_block(
    block: GuideContentBlock,
    db: AsyncSession,
    semaphore: asyncio.Semaphore,
    retry_count: int = 0,
) -> None:
    async with semaphore:
        edge = await db.fetch_edge(block.edge_id)
        voice = await db.fetch_voice(block.voice_id)

        # Получаем нарративы соседних точек (тот же голос, тот же язык)
        narrative_a = await db.get_content_text(
            edge.from_point_id, block.voice_id, block.language, "main"
        )
        narrative_b = await db.get_content_text(
            edge.to_point_id, block.voice_id, block.language, "main"
        )

        bearing_desc = _bearing_to_description(edge.bearing_deg)

        response = await llm_client.complete(
            prompt=COHERENCE_VALIDATION_PROMPT.format(
                narrative_a_tail=_tail(narrative_a, sentences=2),
                transition_text=block.text_script,
                narrative_b_head=_head(narrative_b, sentences=2),
                style_group=voice.style_group,
                language=block.language,
                bearing_description=bearing_desc,
            ),
            model=settings.guide_qa_model,   # быстрая модель для валидации
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        score_data = json.loads(response)
        overall = float(score_data.get("overall_score", 0))

        # Обновляем coherence_score в БД
        await db.update_content_block(block.id, coherence_score=overall)

        if overall >= 4.0:
            await db.update_content_block(block.id, generation_status="validated")

        elif retry_count < 3:
            # Перегенерируем transition с подсказкой
            fix_hint = score_data.get("suggested_fix", "")
            new_text = await _regenerate_transition(block, edge, fix_hint, db)
            await db.update_content_block(
                block.id,
                text_script=new_text,
                generation_status="draft",
                generated_at=utcnow(),
            )
            # Рекурсивная повторная валидация
            await _validate_transition_block(
                block, db, semaphore, retry_count=retry_count + 1
            )

        else:
            # После 3 попыток — на ручной ревью
            await db.update_content_block(
                block.id,
                generation_status="needs_manual_review",
                review_notes=f"Auto-validation failed after 3 retries. Last score: {overall:.1f}. Issue: {score_data.get('issues', '')}",
            )
```

### 5.2. Валидация main/bonus блоков

Для `main` и `bonus` блоков проводится упрощённая самостоятельная валидация (без тройки):

```python
STANDALONE_VALIDATION_PROMPT = """\
You are a quality validator for an audio walking guide.
Evaluate this {content_type} narrative for the place: {point_name}

Narrative:
«{text_script}»

Voice style: {style_group}, Language: {language}

Rate on a scale of 1.0–5.0:
1. FACTUAL PLAUSIBILITY — Does the content avoid obvious factual errors?
2. STYLE ADHERENCE — Does it match the {style_group} voice persona?
3. AUDIO READINESS — Is it written for listening (no lists, no "see diagram", natural sentences)?
4. LENGTH APPROPRIATENESS — Is it the right length for {content_type} content?

Respond in JSON:
{{
  "factual_plausibility": <1.0–5.0>,
  "style_adherence": <1.0–5.0>,
  "audio_readiness": <1.0–5.0>,
  "length_appropriateness": <1.0–5.0>,
  "overall_score": <simple average>,
  "issues": "<main issue or 'none'>"
}}
"""
```

Порог: `overall_score ≥ 3.5` → `validated`; ниже → `needs_manual_review` (значение из `COHERENCE_THRESHOLDS["main"]`).

### 5.3. Сквозная валидация «прогулки»

После попарной валидации — опциональная (рекомендованная) сквозная проверка:

```python
async def validate_walk_sequences(
    zone_id: UUID,
    language: str,
    voice_id: UUID,
    db: AsyncSession,
    num_walks: int = 5,
    walk_length: int = 6,
) -> None:
    """
    Генерирует num_walks случайных маршрутов по графу,
    собирает цепочку нарративов и оценивает сквозную связность.
    """
    points = await db.fetch_active_points(zone_id)
    edges  = await db.fetch_edges(zone_id)
    adj    = _build_adj(edges)

    for _ in range(num_walks):
        # Случайный связный путь из walk_length точек
        path = _random_walk(points, adj, length=walk_length)

        # Собираем цепочку: main_A → transition_A→B → main_B → transition_B→C → ...
        chain_parts = []
        for i, point_id in enumerate(path):
            main_text = await db.get_content_text(point_id, voice_id, language, "main")
            chain_parts.append(f"[{i+1}. {await db.get_point_name(point_id)}]\n{main_text}")
            if i < len(path) - 1:
                trans = await db.get_best_transition(point_id, path[i+1], voice_id, language)
                if trans:
                    chain_parts.append(f"[→ transition]\n{trans.text_script}")

        full_chain = "\n\n".join(chain_parts)

        response = await llm_client.complete(
            prompt=WALK_VALIDATION_PROMPT.format(
                chain=full_chain[:4000],  # cap at 4K chars
                style_group=voice.style_group,
                language=language,
            ),
            model=settings.guide_qa_model,
            max_tokens=400,
            response_format={"type": "json_object"},
        )

        result = json.loads(response)
        if result.get("overall_score", 5) < 3.5:
            # LLM возвращает имена точек → сопоставляем с point_id через кэш
            point_name_to_id = {p.name: p.id for p in points}
            for problem_name in result.get("problem_points", []):
                pid = point_name_to_id.get(problem_name)
                if pid:
                    await db.flag_blocks_for_review(
                        point_id=pid,
                        zone_id=zone_id,
                        voice_id=voice_id,
                        language=language,
                        note=f"Walk validation: {result.get('main_issue', '')}",
                    )
```

#### Промт сквозной валидации

```python
WALK_VALIDATION_PROMPT = """\
You are evaluating a complete audio walking tour sequence.
Voice style: {style_group}, Language: {language}

Here is the full narration chain a listener would hear while walking:

{chain}

Evaluate the overall listening experience:
1. NARRATIVE CONTINUITY — Does the whole walk feel like one coherent story?
   Are there jarring topic jumps between points?
2. NO REDUNDANCY — Are there facts/phrases repeated across multiple points?
3. THEMATIC PROGRESSION — Is there a natural arc or build-up across the walk?
4. ENGAGEMENT — Would a listener want to keep walking to hear what comes next?

Respond in JSON:
{{
  "narrative_continuity": <1.0–5.0>,
  "no_redundancy": <1.0–5.0>,
  "thematic_progression": <1.0–5.0>,
  "engagement": <1.0–5.0>,
  "overall_score": <average>,
  "main_issue": "<description or 'none'>",
  "problem_points": ["<point name>", ...]
}}
"""
```

---

## 6. Стадия 3: Manual Review

### 6.1. Приоритизация очереди ревью

Очередь `needs_manual_review` сортируется по приоритету:

```python
REVIEW_PRIORITY = {
    # По типу контента (от высшего к низшему)
    "content_type": {
        "main":            1,   # вступительные блоки — самые заметные
        "zone_transition": 2,
        "transition":      3,
        "bonus":           4,
        "recap":           5,
    },
    # По типу точки
    "point_type": {
        "poi":       1,
        "connector": 2,
    },
}

# SQL для отсортированной очереди (псевдокод):
-- cb.zone_id используется напрямую (денормализовано), JOIN guide_points только для name/point_type
SELECT cb.*, gp.name, gp.point_type, gv.name as voice_name
FROM guide_content_blocks cb
JOIN guide_points gp ON cb.point_id = gp.id
JOIN guide_voices gv ON cb.voice_id = gv.id
WHERE cb.generation_status = 'needs_manual_review'
  AND cb.zone_id = $zone_id  -- прямой фильтр по денормализованному zone_id (без дополнительного JOIN)
ORDER BY
    CASE cb.content_type
        WHEN 'main' THEN 1 WHEN 'zone_transition' THEN 2
        WHEN 'transition' THEN 3 WHEN 'bonus' THEN 4 ELSE 5
    END,
    CASE gp.point_type WHEN 'poi' THEN 1 ELSE 2 END,
    cb.coherence_score ASC NULLS LAST  -- сначала самые проблемные
```

### 6.2. Инструменты ревьюера

**1. Список с фильтрами (GET /api/guide/admin/content/review)**

Фильтры: `zone_id`, `status` (needs_manual_review / validated), `language`, `voice_id`, `content_type`, `min_score`, `max_score`.

Ответ содержит полный контекст: текст блока, оценка, комментарий автовалидатора, краткий excerpt соседних нарративов (для transition-блоков).

**2. Три действия с блоком (PUT /api/guide/admin/content/{block_id}/review)**

| action | Поведение |
|--------|-----------|
| `approve` | `generation_status → reviewed`, `reviewed_by`, `reviewed_at` |
| `edit` | Обновляет `text_script`, `generation_status → reviewed` |
| `regenerate` | `generation_status → pending`, ставит в очередь LLM (с опциональной инструкцией через `review_notes`) |

**3. Quick TTS preview**

Перед апрувом редактор может прослушать синтез:
```
POST /api/guide/admin/content/{block_id}/preview-tts
Response: { audio_url: "<presigned S3 URL, expires 1h>", duration_s: float }
```
Синтез через ElevenLabs (обычный `synthesize_batch`), файл кладётся в `s3://bucket/guide/preview/{block_id}.mp3`.

**4. Batch accept**

Блоки с `coherence_score ≥ 4.5` можно принять массово:
```
POST /api/guide/admin/content/batch-approve
{ "zone_id": "...", "min_score": 4.5, "language": "en" }
Response: { "approved_count": 342 }
```

### 6.3. Ожидаемый объём ручной работы

При типичном распределении coherence_score:
- ~85% блоков → `validated` автоматически (score ≥ 4.0)
- ~15% → `needs_manual_review`

Для MVP (~57 840 блоков) ≈ 8 700 блоков на ревью. При batch accept с порогом 4.5 из них:
- ~60% (coherence_score 4.0–4.49) → уже на ревью, но большинство требуют просто подтверждения
- ~40% (score < 4.0) → требуют edit или regenerate

**Практическая оценка времени:** ~2–3 минуты на блок с edit/regenerate, ~10 секунд на approve/batch-accept → ~80–100 человеко-часов на полный MVP при наличии удобного UI.

---

## 7. Стадия 4: Audio Synthesis

### 7.1. Batch TTS

```python
# src/guide/application/content_pipeline/audio_synthesizer.py

async def synthesize_zone(
    zone_id: UUID,
    voice_ids: list[UUID] | None,
    job_id: UUID,
    db: AsyncSession,
) -> None:
    """Синтезирует аудио для всех reviewed блоков зоны."""

    blocks = await db.fetch_content_blocks(
        zone_id=zone_id,
        generation_status="reviewed",
        voice_ids=voice_ids,
    )

    # Обновляем статус на synthesizing массово
    await db.bulk_update_status(
        [b.id for b in blocks], "synthesizing"
    )

    semaphore = asyncio.Semaphore(settings.guide_tts_max_parallel)
    tasks = [
        _synthesize_block(block, db, semaphore, job_id)
        for block in blocks
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    await _finalize_job(job_id, db)


async def _synthesize_block(
    block: GuideContentBlock,
    db: AsyncSession,
    semaphore: asyncio.Semaphore,
    job_id: UUID,
) -> None:
    async with semaphore:
        voice = await db.fetch_voice(block.voice_id)

        try:
            # 1. ElevenLabs TTS
            audio_bytes = await elevenlabs_client.synthesize_batch(
                text=block.text_script,
                voice_id=voice.elevenlabs_voice_id,
                output_format="mp3_44100_128",
            )

            # 2. FFmpeg постобработка
            processed_bytes = await ffmpeg_pipeline(
                audio_bytes,
                normalize_lufs=-16.0,    # loudness normalization
                add_silence_end_ms=400,  # пауза в конце сегмента
                fade_out_ms=150,         # плавный fade-out
            )

            # 3. S3 upload
            s3_key = _build_s3_key(block)
            cdn_url = await s3_client.upload_audio(
                key=s3_key,
                data=processed_bytes,
                content_type="audio/mpeg",
            )

            # 4. Определяем длительность
            duration_s = await get_audio_duration(processed_bytes)

            # 5. Обновляем БД
            await db.update_content_block(
                block.id,
                audio_url=cdn_url,
                audio_duration_seconds=duration_s,
                generation_status="synthesized",
                synthesized_at=utcnow(),
            )
            await _update_job_progress(job_id, db, increment=1)

        except Exception as e:
            logger.error(f"TTS failed for block {block.id}: {e}")
            await db.update_content_block(block.id, generation_status="failed")
```

### 7.2. S3 path scheme

```
guide/audio/{zone_id}/{point_id}/{voice_id}/{language}/{content_type}_{variant}.mp3

Примеры:
  guide/audio/abc.../def.../ghi.../en/main_0.mp3
  guide/audio/abc.../def.../ghi.../en/bonus_0.mp3
  guide/audio/abc.../def.../ghi.../en/transition_0.mp3   (edge = указан в block.edge_id)
  guide/audio/abc.../def.../ghi.../en/transition_1.mp3
  guide/audio/abc.../def.../ghi.../en/transition_2.mp3
  guide/audio/abc.../def.../ghi.../ru/main_0.mp3
  guide/audio/abc.../def.../ghi.../en/zone_transition_0.mp3

Preview (Стадия 3):
  guide/preview/{block_id}.mp3  (TTL: 24h, затем удаляется lifecycle policy)
```

```python
def _build_s3_key(block: GuideContentBlock) -> str:
    return (
        f"guide/audio/{block.zone_id}/{block.point_id}/"
        f"{block.voice_id}/{block.language}/"
        f"{block.content_type}_{block.variant_index}.mp3"
    )
```

### 7.3. FFmpeg постобработка

```python
async def ffmpeg_pipeline(
    audio_bytes: bytes,
    normalize_lufs: float = -16.0,
    add_silence_end_ms: int = 400,
    fade_out_ms: int = 150,
) -> bytes:
    """
    Цепочка ffmpeg фильтров:
    1. loudnorm — нормализация громкости до -16 LUFS (совместимость с подкастами)
    2. apad — добавить тишину в конец (естественная пауза между сегментами)
    3. afade=type=out — плавный fade-out в конце
    """
    cmd = [
        "ffmpeg", "-i", "pipe:0",
        "-af", (
            f"loudnorm=I={normalize_lufs}:TP=-1.5:LRA=11,"
            f"apad=pad_dur={add_silence_end_ms}ms,"
            f"afade=type=out:duration={fade_out_ms}ms"
        ),
        "-c:a", "libmp3lame", "-b:a", "128k",
        "-f", "mp3", "pipe:1"
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=audio_bytes)
    if proc.returncode != 0:
        raise FFmpegError(stderr.decode())
    return stdout
```

### 7.4. QA аудио (автоматические проверки)

```python
async def qa_audio_block(block: GuideContentBlock, audio_bytes: bytes) -> list[str]:
    """Возвращает список предупреждений (пустой = OK)."""
    warnings = []

    duration = await get_audio_duration(audio_bytes)
    block.audio_duration_seconds = duration

    # Проверка длительности по типу контента
    EXPECTED_DURATION = {
        "main":            (15, 90),    # 15–90 сек
        "bonus":           (10, 60),
        "transition":      (3, 20),
        "zone_transition": (5, 25),
        "recap":           (3, 15),
    }
    min_s, max_s = EXPECTED_DURATION.get(block.content_type, (1, 120))
    if duration < min_s:
        warnings.append(f"Duration {duration:.1f}s < min {min_s}s")
    if duration > max_s:
        warnings.append(f"Duration {duration:.1f}s > max {max_s}s")

    # Проверка на тишину в начале (> 0.5 сек = проблема TTS)
    silence_start = await detect_leading_silence(audio_bytes, threshold_db=-40)
    if silence_start > 0.5:
        warnings.append(f"Leading silence {silence_start:.2f}s detected")

    return warnings
```

**Spot-check:** для каждой зоны после синтеза выбирается 5 случайных блоков (по одному из каждого content_type), их аудио-URL логируется в `guide_content_jobs.progress_json["spot_check_urls"]` для прослушивания командой.

### 7.5. Rate limits ElevenLabs

| Параметр | Значение |
|----------|----------|
| `guide_tts_max_parallel` | 10 (concurrent requests) |
| ElevenLabs Starter (default) | 2 concurrent, 10K chars/month |
| ElevenLabs Creator | 5 concurrent |
| ElevenLabs Business | 20 concurrent |
| Рекомендуется для MVP | **Creator** или **Business** |

---

## 8. API-спецификация контентного пайплайна

Все эндпоинты требуют admin-роли. Префикс: `/api/guide/admin/`.

### 8.1. Запуск стадий

**`POST /api/guide/admin/content/generate`**
```
Request: {
  zone_id: UUID,
  voice_ids: [UUID] | null,        -- null = все активные голоса
  languages: ["en", "ru"] | null,  -- null = все
  force_regenerate: bool           -- перегенерировать уже существующие draft-блоки
}
Response: { job_id: UUID, blocks_queued: int }
```

**`POST /api/guide/admin/content/validate`**
```
Request: {
  zone_id: UUID,
  language: str | null,
  include_walk_validation: bool    -- запустить сквозную валидацию маршрутов
}
Response: { job_id: UUID, blocks_queued: int }
```

**`POST /api/guide/admin/content/synthesize`**
```
Request: {
  zone_id: UUID,
  voice_ids: [UUID] | null,
  force_resynthesize: bool         -- перезаписать существующее аудио
}
Response: { job_id: UUID, files_queued: int }
```

### 8.2. Мониторинг jobs

**`GET /api/guide/admin/content/jobs?zone_id=&job_type=&status=`**
```
Response: {
  jobs: [
    {
      id, job_type, status, zone_name, language, voice_name,
      progress: {
        total, processed, draft, validated, needs_manual_review,
        reviewed, synthesized, failed,
        current_bfs_level, bfs_total_levels
      },
      error_message, created_at, completed_at
    }
  ]
}
```

**`GET /api/guide/admin/content/jobs/{job_id}`**
```
Response: <детальный JobView с progress_json>
```

### 8.3. Статус контента зоны

**`GET /api/guide/admin/content/status?zone_id=`**
```
Response: {
  zone_id, zone_name,
  by_status: {
    pending: int, draft: int, validated: int,
    needs_manual_review: int, reviewed: int,
    synthesizing: int, synthesized: int, failed: int
  },
  by_voice: [
    {
      voice_id, voice_name, language,
      total: int, synthesized: int, ready_pct: float,
      avg_coherence_score: float
    }
  ],
  by_content_type: {
    main: { total, synthesized },
    bonus: { total, synthesized },
    transition: { total, synthesized },
    zone_transition: { total, synthesized }
  },
  is_ready_for_production: bool  -- true если 100% synthesized
}
```

### 8.4. Manual Review API

**`GET /api/guide/admin/content/review`**
```
Query: zone_id, status (needs_manual_review | validated | all),
       language, voice_id, content_type,
       min_score, max_score,
       limit=50, offset=0

Response: {
  total: int,
  blocks: [
    {
      id, point_id, point_name, point_type,
      content_type, edge_id, variant_index,
      language, voice_id, voice_name, style_group,
      text_script, generation_status,
      coherence_score, review_notes, reviewed_by, reviewed_at,
      -- Контекст для transition-блоков:
      context?: {
        from_point_name, from_narrative_tail: str,
        to_point_name, to_narrative_head: str,
        bearing_description: str
      }
    }
  ]
}
```

**`PUT /api/guide/admin/content/{block_id}/review`**
```
Request: {
  action: "approve" | "edit" | "regenerate",
  edited_text: str | null,
  review_notes: str | null,
  regenerate_instruction: str | null  -- подсказка для LLM при regenerate
}
Response: { block_id, generation_status, reviewed_at, coherence_score }
```

**`POST /api/guide/admin/content/{block_id}/preview-tts`**
```
Response: { audio_url: str, duration_s: float, expires_in_seconds: 3600 }
```

**`POST /api/guide/admin/content/batch-approve`**
```
Request: {
  zone_id: UUID,
  min_score: float,  -- 4.5 рекомендуется
  language: str | null,
  content_types: [str] | null
}
Response: { approved_count: int, skipped_count: int }
```

---

## 9. Мониторинг и метрики

### 9.1. Операционные метрики пайплайна

| Метрика | Как собирается | Где смотреть |
|---------|---------------|-------------|
| Блоков в статусе X | COUNT в guide_content_blocks | GET /content/status |
| % needs_manual_review | count(nmr) / count(total) × 100 | /content/status |
| Avg coherence_score | AVG(coherence_score) WHERE status='validated' | /content/status |
| LLM retry rate | count(attempt>1) / count(total) | guide_content_jobs.progress_json |
| TTS failure rate | count(failed) / count(synthesizing+synthesized) | /content/status |
| Pipeline latency | completed_at - created_at per job | /content/jobs |

### 9.2. Dashboard-запрос (агрегат по зоне)

```sql
-- cb.zone_id денормализован — JOIN guide_points не нужен для агрегата
SELECT
    z.name AS zone_name,
    COUNT(cb.id) AS total_blocks,
    COUNT(cb.id) FILTER (WHERE cb.generation_status = 'synthesized') AS synthesized,
    ROUND(
        COUNT(cb.id) FILTER (WHERE cb.generation_status = 'synthesized')::numeric
        / NULLIF(COUNT(cb.id), 0) * 100, 1
    ) AS ready_pct,
    COUNT(cb.id) FILTER (WHERE cb.generation_status = 'needs_manual_review') AS needs_review,
    ROUND(AVG(cb.coherence_score) FILTER (WHERE cb.coherence_score IS NOT NULL), 2) AS avg_score,
    COUNT(cb.id) FILTER (WHERE cb.generation_status = 'failed') AS failed
FROM guide_content_blocks cb
JOIN guide_zones z ON cb.zone_id = z.id  -- используем денормализованный zone_id, без JOIN guide_points
WHERE cb.zone_id = $zone_id
GROUP BY z.name;
```

### 9.3. Алерты

| Условие | Действие |
|---------|----------|
| `failed > 5%` total blocks в job | Остановить job, уведомить |
| `needs_manual_review > 20%` | Уведомить команду (порог промта, возможно стоит пересмотреть) |
| `avg_coherence_score < 3.5` по зоне | Уведомить — возможно проблема с knowledge_cards |
| TTS error rate > 2% | Проверить ElevenLabs API key и лимиты |
| Job застрял > 2 часов без прогресса | Уведомить + автоперезапуск |

---

## 10. Оценка стоимости

### 10.1. Допущения

| Параметр | Значение |
|----------|----------|
| Блоков всего (MVP, standard only) | ~57 840 |
| Блоков всего (full, brief + standard) | ~77 040 |
| Средняя длина text_script | 150 слов ≈ 1 000 токенов (input + output) |
| Валидации (попарные) | ~24 000 transition-блоков × 1 вызов |
| io.net модель | `meta-llama/Llama-3.3-70B-Instruct` |
| io.net цена | ~$0.40 / 1M токенов (вход+выход) |
| ElevenLabs | Creator: $22/мес, 100K chars; Business: $99/мес, 500K chars |
| Средняя длина синтеза | 150 слов ≈ 900 символов |

> **Базовый расчёт: MVP (только standard).** Brief-версию добавлять после валидации продукта.

### 10.2. Стадия 1 (Draft Generation)

```
MVP (только standard для main/bonus/recap):
  main/bonus/recap (standard):  ~28 800 блоков × 1 000 токенов = 28.8M токенов
  recap (standard, каждая точка × 8 голосов):  уже включён выше
  transition (3 варианта за 1 вызов): ~9 600 вызовов × 600 токенов = 5.8M токенов
  zone_transition: ~30 вызовов × 400 токенов = 0.01M токенов
  ─────────────────────────────────────────────────────
  Итого генерация:   ~34.6M токенов × $0.40/1M = $13.84

Retry overhead (~10% retries):
  +3.5M токенов = $1.40
─────────────────────────────────────────────────────────────────
Стадия 1 итого: ~$15 (MVP standard only)
[Стадия 1, полный brief+standard: ~$21]
```

### 10.3. Стадия 2 (Coherence Validation)

```
Попарная валидация transition: ~35 000 блоков × 600 токенов = 21M токенов
Standalone валидация main/bonus: ~22 000 блоков × 400 токенов = 8.8M токенов
Walk validation (75 прогулок × 4 000 токенов): 0.3M токенов
Retry overhead валидации (~5 попыток):
  ~35 000 × 0.15 × 2 retries × 600 токенов = 6.3M токенов
─────────────────────────────────────────────────────────────────
Стадия 2 итого: ~36.4M токенов × $0.40/1M = ~$15
```

### 10.4. Стадия 4 (Audio Synthesis)

```
ElevenLabs символов:
  57 840 блоков × 900 символов = 52M символов

ElevenLabs Business ($99/мес, 500K chars/мес):
  52M / 500K = 104 месяца — нереально в рамках одного плана

→ Использовать API напрямую (pay-per-use):
  ElevenLabs API: $0.15 / 1K символов (Multilingual v2)
  52M символов = 52 000 × $0.15 = $7 800

Оптимизация: генерировать аудио только для 1 детального уровня (standard),
  brief — тот же текст, только обрезать? Нет, brief/standard — разные скрипты.
  Но можно отложить brief до явного запроса.

→ Если синтезировать только standard (÷2): ~$3 900

Preview TTS (Стадия 3, ~2 000 preview-запросов × 900 символов):
  1.8M символов = $270
─────────────────────────────────────────────────────────────────
Стадия 4 итого: ~$4 200 (только standard) — $7 800 (full)
```

### 10.5. Сводная таблица

| Стадия | Сервис | Стоимость (MVP, standard) | Стоимость (full, brief+standard) |
|--------|--------|--------------------------|---------------------------------|
| 1. Draft Generation | io.net LLM | ~$15 | ~$21 |
| 2. Coherence Validation | io.net LLM | ~$15 | ~$15 |
| 3. Manual Review preview TTS | ElevenLabs | ~$270 | ~$270 |
| 4. Audio Synthesis | ElevenLabs | ~$3 900 | ~$7 800 |
| **Итого** | | **~$4 200** | **~$8 100** |

> **Рекомендация:** запустить MVP только с `standard` detail_level (~$4 200 итого), добавить `brief` в следующей итерации после валидации продукта. LLM-стадии (1+2) составляют всего ~$30 для MVP — основная стоимость сосредоточена в TTS.

### 10.6. Оценка по одной зоне

| Показатель | Значение |
|------------|----------|
| Блоков на зону | ~3 850 |
| LLM (генерация + валидация) | ~$2.50 |
| TTS (standard) | ~$260 |
| **Итого одна зона** | **~$262** |

Стоимость добавления нового города (4 зоны) ≈ $1 050 — что комфортно для масштабирования после MVP.

---

## 11. Файловая структура модуля

```
src/guide/application/content_pipeline/
├── __init__.py
├── draft_generator.py          # BFS-оркестратор, генерация main/bonus/recap/transition
├── coherence_validator.py      # Попарная + сквозная валидация
├── review_service.py           # Manual review: approve/edit/regenerate/batch-approve
├── audio_synthesizer.py        # Batch TTS, FFmpeg, S3 upload
├── prompt_templates.py         # Все промты, VOICE_PERSONAS, WORD_COUNTS, COHERENCE_THRESHOLDS
├── prompt_builder.py           # build_point_context() и форматировщики
└── utils.py                    # _tail(), _head(), _bearing_to_description(), etc.
```

Точки входа регистрируются в `src/guide/api/admin_router.py` как background tasks:

```python
# admin_router.py (фрагмент)
from src.guide.application.content_pipeline.draft_generator import generate_zone_drafts
from src.guide.application.content_pipeline.coherence_validator import validate_zone_transitions
from src.guide.application.content_pipeline.audio_synthesizer import synthesize_zone

@router.post("/content/generate")
async def start_generation(
    req: ContentGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    job = await db.create_content_job(
        zone_id=req.zone_id, job_type="generate_drafts", language=req.language
    )
    background_tasks.add_task(
        generate_zone_drafts,
        zone_id=req.zone_id,
        voice_ids=req.voice_ids or await db.fetch_active_voice_ids(),
        languages=req.languages or ["en", "ru"],
        job_id=job.id,
        db=db,
    )
    return {"job_id": job.id, "blocks_queued": await db.count_pending_blocks(req.zone_id)}
```
