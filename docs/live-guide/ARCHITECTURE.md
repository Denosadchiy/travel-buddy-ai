# Live Audio Guide — Backend Architecture

## 1. Обзор системы

```
┌─────────────────────────────────────────────────────────────────┐
│                        iOS Client                                │
│  Core Location → Navigation Engine → Audio Player → Q&A UI      │
└───────┬─────────────────┬──────────────────┬────────────────────┘
        │ REST/SSE         │ Heartbeat         │ Audio chunks (SSE)
        ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (src/guide/)                    │
│                                                                   │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Zones/   │  │  Session &   │  │ Streaming    │               │
│  │ Coverage │  │  Billing     │  │ Q&A Pipeline │               │
│  │ Router   │  │  Router      │  │ Router       │               │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘               │
│       │               │                  │                        │
│  ┌────▼───────────────▼──────────────────▼──────────────────┐   │
│  │               Application Layer                            │   │
│  │  NavigationEngine │ SessionManager │ BillingService │      │   │
│  │  ContentPipeline  │ QAPipeline     │ City Seeder    │      │   │
│  └────┬──────────────────────────────────────────────────────┘   │
│       │                                                            │
│  ┌────▼──────────────────────────────────────────────────────┐   │
│  │              Infrastructure Layer                           │   │
│  │  PostgreSQL+PostGIS │ ElevenLabs │ STT │ S3/CDN │ IAP     │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

City Seeder (batch, offline):
  Google Places API → DBSCAN Zones → OSMnx Graph → Wikipedia/Wikidata
  → PostgreSQL → LLM Narratives (io.net) → TTS (ElevenLabs) → S3/CDN
```

**Новый модуль:** `src/guide/` — самодостаточный вертикаль, аналогично `src/hotels/`.

```
src/guide/
├── api/
│   ├── router.py          # Client API
│   └── admin_router.py    # Admin/internal API
├── application/
│   ├── navigation_engine.py
│   ├── session_manager.py
│   ├── qa_pipeline.py
│   ├── billing_service.py
│   ├── content_pipeline.py
│   └── seeder/
│       ├── orchestrator.py
│       ├── zone_discovery.py
│       ├── point_placement.py
│       ├── graph_builder.py
│       └── knowledge_collector.py
├── domain/
│   └── schemas.py
└── infrastructure/
    ├── elevenlabs_client.py
    ├── stt_client.py
    ├── s3_client.py
    └── iap_validator.py
```

Регистрация в `src/main.py`:
```python
from src.guide.api.router import guide_router
from src.guide.api.admin_router import guide_admin_router
app.include_router(guide_router, prefix="/api")
app.include_router(guide_admin_router, prefix="/api")
```

---

## 2. Модель данных (PostgreSQL + PostGIS)

### Предварительные требования

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()
```

### DDL

```sql
-- Города
CREATE TABLE guide_cities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR NOT NULL,           -- "Paris"
    name_local  VARCHAR,                    -- "Париж"
    country     VARCHAR NOT NULL,
    center      GEOMETRY(Point, 4326) NOT NULL,  -- PostGIS точка
    timezone    VARCHAR NOT NULL DEFAULT 'UTC',
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_cities_center ON guide_cities USING GIST(center);

-- Туристические зоны (полигоны покрытия)
CREATE TABLE guide_zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_id     UUID NOT NULL REFERENCES guide_cities(id) ON DELETE CASCADE,
    name        VARCHAR NOT NULL,           -- "Le Marais"
    description TEXT,
    theme       VARCHAR,                    -- "historic", "bohemian", "waterfront"
    boundary    GEOMETRY(Polygon, 4326) NOT NULL,  -- зона покрытия
    poi_count   INTEGER NOT NULL DEFAULT 0,
    point_count INTEGER NOT NULL DEFAULT 0,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_zones_boundary ON guide_zones USING GIST(boundary);
CREATE INDEX idx_guide_zones_city_id  ON guide_zones(city_id);

-- Гео-точки (узлы графа)
-- point_type: 'poi' — значимый объект; 'connector' — промежуточная точка на пешеходном пути
CREATE TABLE guide_points (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id          UUID NOT NULL REFERENCES guide_zones(id) ON DELETE CASCADE,
    location         GEOMETRY(Point, 4326) NOT NULL,
    trigger_radius_m INTEGER NOT NULL DEFAULT 25,  -- радиус триггера (метры)
    point_type       VARCHAR NOT NULL DEFAULT 'poi',
    name             VARCHAR,                -- название POI (для основных точек)
    google_place_id  VARCHAR,               -- Google Places ID
    osm_node_id      BIGINT,               -- OSM-узел (для связующих точек)
    is_approved      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(zone_id, google_place_id),
    UNIQUE(zone_id, osm_node_id)
);
CREATE INDEX idx_guide_points_location ON guide_points USING GIST(location);
CREATE INDEX idx_guide_points_zone_id  ON guide_points(zone_id);
CREATE INDEX idx_guide_points_type     ON guide_points(zone_id, point_type);

-- Рёбра графа (направленные связи между точками)
CREATE TABLE guide_edges (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_point_id UUID NOT NULL REFERENCES guide_points(id) ON DELETE CASCADE,
    to_point_id   UUID NOT NULL REFERENCES guide_points(id) ON DELETE CASCADE,
    distance_m    FLOAT NOT NULL,          -- пешеходное расстояние
    walk_seconds  INTEGER NOT NULL,        -- расчётное время перехода
    bearing_deg   FLOAT,                   -- направление A→B (0–360°)
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(from_point_id, to_point_id)
);
CREATE INDEX idx_guide_edges_from ON guide_edges(from_point_id);
CREATE INDEX idx_guide_edges_to   ON guide_edges(to_point_id);

-- Карточки знаний (собирает City Seeder, входные данные для LLM-нарративов)
-- card_type: 'poi' (основная) | 'street_context' (для connector-точек, см. §4)
CREATE TABLE guide_knowledge_cards (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    point_id           UUID NOT NULL UNIQUE REFERENCES guide_points(id) ON DELETE CASCADE,
    card_type          VARCHAR NOT NULL DEFAULT 'poi',  -- poi | street_context
    google_place_data  JSONB,              -- Place Details response (для poi)
    street_name        VARCHAR,            -- название улицы (для street_context)
    wikipedia_summary  TEXT,              -- первый параграф статьи
    wikidata_facts     JSONB,             -- структурированные факты
    enriched_at        TIMESTAMPTZ
);

-- Голосовые персонажи гида
-- style_group: academic | friendly | dramatic | minimal (один персонаж на стиль)
-- Один голос на комбинацию (style_group × language) — UNIQUE constraint.
-- Это позволяет группировать языковые варианты одного персонажа.
CREATE TABLE guide_voices (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 VARCHAR NOT NULL,       -- "Historian EN", "Local Friend RU"
    style_group          VARCHAR NOT NULL,       -- academic | friendly | dramatic | minimal
    language             VARCHAR NOT NULL DEFAULT 'en',  -- en | ru
    elevenlabs_voice_id  VARCHAR NOT NULL,
    preview_audio_url    VARCHAR,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(style_group, language)               -- один ElevenLabs voice per стиль × язык
);

-- Контентные блоки (текст + аудио на точку × голос × язык × уровень детализации)
-- content_type: 'main' | 'bonus' | 'transition' | 'zone_transition' | 'recap'
-- Для transition/zone_transition: edge_id указывает направленное ребро A→B
-- variant_index: несколько вариантов переходных фраз (0,1,2) для разнообразия
-- language хранится явно (отдельно от voice_id), т.к. один голос может озвучивать
-- несколько языков в перспективе, а generation_status/review проходит per-language.
--
-- generation_status pipeline:
--   pending → draft → validated → needs_manual_review → reviewed → synthesizing → synthesized → failed
--   • draft: LLM сгенерировал текст
--   • validated: прошла автовалидация (transitions: coherence_score ≥ 4.0; main/bonus/recap: ≥ 3.5)
--   • needs_manual_review: ниже порога или флаг от редактора
--   • reviewed: прошёл ручной ревью
--   • synthesizing / synthesized: TTS-этап
--
-- detail_level: brief | standard — определяет длину/детализацию нарратива.
-- Навигационный движок выбирает контент по session.detail_level.
-- Для transitions, zone_transition и recap detail_level всегда 'standard' (длина фиксирована).
--
-- zone_id денормализован из guide_points.zone_id. Заполняется при вставке.
-- Используется для: (1) формирования S3-ключа, (2) фильтрации в admin API,
-- (3) агрегированных запросов контент-статуса по зоне без JOIN.
CREATE TABLE guide_content_blocks (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    point_id               UUID NOT NULL REFERENCES guide_points(id) ON DELETE CASCADE,
    zone_id                UUID NOT NULL REFERENCES guide_zones(id),  -- добавлено: денормализован для S3-ключа и фильтрации без JOIN
    voice_id               UUID NOT NULL REFERENCES guide_voices(id),
    language               VARCHAR NOT NULL DEFAULT 'en',  -- явный язык, независим от voice
    detail_level           VARCHAR NOT NULL DEFAULT 'standard',  -- добавлено: brief | standard; нужен для различения версий нарратива
    content_type           VARCHAR NOT NULL,
    edge_id                UUID REFERENCES guide_edges(id),
    variant_index          INTEGER NOT NULL DEFAULT 0,
    text_script            TEXT NOT NULL,
    audio_url              VARCHAR,            -- CDN URL (null до синтеза)
    audio_duration_seconds FLOAT,
    generation_status      VARCHAR NOT NULL DEFAULT 'pending',
    coherence_score        FLOAT,              -- автооценка связности 1–5 (от LLM-валидатора)
    review_notes           TEXT,              -- комментарий редактора
    reviewed_by            VARCHAR,           -- user login редактора
    reviewed_at            TIMESTAMPTZ,
    generated_at           TIMESTAMPTZ,
    synthesized_at         TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Индекс включает detail_level: уникальный блок на точку × голос × язык × уровень × тип × вариант
CREATE INDEX idx_guide_content_lookup
    ON guide_content_blocks(point_id, voice_id, language, detail_level, content_type, variant_index);
CREATE INDEX idx_guide_content_edge
    ON guide_content_blocks(edge_id, voice_id, language, detail_level);  -- добавлен detail_level для выбора правильной версии
CREATE INDEX idx_guide_content_zone
    ON guide_content_blocks(zone_id);  -- добавлено: быстрый доступ к блокам зоны без JOIN
-- Два partial UNIQUE индекса обеспечивают идемпотентность:
-- повторный запуск генерации обновляет существующие блоки через ON CONFLICT.
-- PostgreSQL ON CONFLICT работает с partial indexes при указании constraint name.
CREATE UNIQUE INDEX idx_guide_content_uq_no_edge
    ON guide_content_blocks(point_id, voice_id, language, detail_level, content_type, variant_index)
    WHERE edge_id IS NULL;  -- для блоков без edge (main, bonus, recap)
CREATE UNIQUE INDEX idx_guide_content_uq_with_edge
    ON guide_content_blocks(point_id, voice_id, language, detail_level, content_type, edge_id, variant_index)
    WHERE edge_id IS NOT NULL;  -- для блоков с edge (transition, zone_transition)
CREATE INDEX idx_guide_content_status
    ON guide_content_blocks(generation_status);

-- Задания контентного пайплайна (отдельно от guide_seed_jobs для детального трекинга)
-- job_type: generate_drafts | validate | synthesize
CREATE TABLE guide_content_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id       UUID NOT NULL REFERENCES guide_zones(id),
    job_type      VARCHAR NOT NULL,
    status        VARCHAR NOT NULL DEFAULT 'running',  -- running | complete | failed
    voice_id      UUID REFERENCES guide_voices(id),
    language      VARCHAR,
    progress_json JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX idx_guide_content_jobs_zone ON guide_content_jobs(zone_id, status);

-- Сессии гида
-- visited_point_ids и qa_history вынесены в отдельные таблицы (§2.1.2, §2.1.3):
--   guide_session_visits  — история посещений с типом контента
--   guide_session_qa      — история Q&A для LLM-контекста
-- Это позволяет эффективно делать агрегаты и избегает раздувания строки.
CREATE TABLE guide_sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id),
    zone_id              UUID NOT NULL REFERENCES guide_zones(id),
    voice_id             UUID NOT NULL REFERENCES guide_voices(id),
    language             VARCHAR NOT NULL DEFAULT 'en',
    detail_level         VARCHAR NOT NULL DEFAULT 'standard',  -- brief | standard
    status               VARCHAR NOT NULL DEFAULT 'active',    -- active | paused | ended
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at             TIMESTAMPTZ,
    total_seconds_billed INTEGER NOT NULL DEFAULT 0,
    last_heartbeat_at    TIMESTAMPTZ,
    last_known_location  GEOMETRY(Point, 4326),
    exit_reason          VARCHAR,                              -- manual | balance_empty | out_of_zone
    -- Поля для post-session feedback
    rating               SMALLINT CHECK (rating BETWEEN 1 AND 5),
    review_text          TEXT
);
CREATE INDEX idx_guide_sessions_user_id ON guide_sessions(user_id);
CREATE INDEX idx_guide_sessions_status  ON guide_sessions(status) WHERE status != 'ended';

-- GPS-лог сессии
-- Решение по хранению: храним ВСЕ точки (не только 20 последних).
-- Обоснование: для post-session аналитики (тепловые карты, популярные маршруты,
-- оптимизация триггер-радиусов) исторические треки ценны. Размер умеренный:
-- 1 точка/5 сек × 30 мин сессии ≈ 360 строк × ~50 байт ≈ 18 КБ на сессию.
-- Для навигации используются последние N точек через ORDER BY recorded_at DESC LIMIT 5.
-- Партиционирование по месяцу рекомендуется при > 100K сессий/месяц.
CREATE TABLE guide_session_gps_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES guide_sessions(id) ON DELETE CASCADE,
    lat          FLOAT NOT NULL,
    lng          FLOAT NOT NULL,
    heading_deg  FLOAT,             -- курс устройства (компас), если доступен
    speed_mps    FLOAT,             -- рассчитанная скорость (м/с)
    accuracy_m   FLOAT,             -- точность GPS (метры)
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_gps_log_session
    ON guide_session_gps_log(session_id, recorded_at DESC);

-- История посещений точек в сессии (заменяет UUID[] visited_point_ids)
-- content_type_played: main | bonus | skipped | zone_transition
-- Преимущества отдельной таблицы vs массив: поддержка аналитики (какой контент слушают),
-- возможность хранить время посещения, нет ограничения на длину массива.
CREATE TABLE guide_session_visits (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID NOT NULL REFERENCES guide_sessions(id) ON DELETE CASCADE,
    point_id          UUID NOT NULL REFERENCES guide_points(id),
    content_type_played VARCHAR NOT NULL DEFAULT 'main',  -- main | bonus | skipped | zone_transition
    visited_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_visits_session
    ON guide_session_visits(session_id, point_id);
CREATE INDEX idx_guide_visits_point
    ON guide_session_visits(point_id);  -- для аналитики популярности точек

-- История Q&A в сессии (заменяет qa_history JSONB)
-- Хранение в отдельной таблице vs JSONB: структурированные запросы (подсчёт вопросов,
-- поиск по тексту), не раздувает строку сессии, легко читать последние N записей.
-- audio_question_url / audio_answer_url опциональны (если решим хранить аудио Q&A).
CREATE TABLE guide_session_qa (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id         UUID NOT NULL REFERENCES guide_sessions(id) ON DELETE CASCADE,
    point_id           UUID REFERENCES guide_points(id),  -- точка, около которой был вопрос
    question_text      TEXT NOT NULL,
    answer_text        TEXT NOT NULL,
    audio_question_url VARCHAR,    -- CDN URL записи вопроса (опционально)
    audio_answer_url   VARCHAR,    -- CDN URL синтезированного ответа (опционально)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_qa_session
    ON guide_session_qa(session_id, created_at DESC);

-- Пользовательские настройки гида (defaults для новых сессий)
-- Если при POST /sessions не переданы voice_id/language/detail_level —
-- берутся из этой таблицы. Обновляется после каждой сессии с явными параметрами.
CREATE TABLE guide_user_preferences (
    user_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    preferred_voice_id   UUID REFERENCES guide_voices(id),
    preferred_language   VARCHAR NOT NULL DEFAULT 'en',
    preferred_detail_level VARCHAR NOT NULL DEFAULT 'standard',
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Аналитические события (product analytics)
-- event_type: session_started | point_visited | question_asked | session_ended |
--             purchase_completed | zone_entered | balance_low | balance_empty
-- event_data: произвольный JSONB (например, для point_visited: {point_id, dist_m})
-- Индекс по (event_type, created_at) — для агрегаций типа "вопросов за день".
-- Не заменяет Mixpanel/Amplitude — дублирует ключевые события для in-house аналитики.
CREATE TABLE guide_analytics_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    session_id  UUID REFERENCES guide_sessions(id),
    event_type  VARCHAR NOT NULL,
    event_data  JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_analytics_type_time
    ON guide_analytics_events(event_type, created_at DESC);
CREATE INDEX idx_guide_analytics_session
    ON guide_analytics_events(session_id);

-- Баланс минут пользователя (в секундах для точности)
-- trial_seconds_* хранятся отдельно для учёта порядка списания: trial → purchased
CREATE TABLE guide_minute_balances (
    user_id                UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    seconds_remaining      INTEGER NOT NULL DEFAULT 0,   -- купленные секунды
    trial_seconds_granted  INTEGER NOT NULL DEFAULT 0,
    trial_seconds_used     INTEGER NOT NULL DEFAULT 0,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Транзакции минут (аудит-лог)
-- transaction_type: purchase | trial | debit | refund
-- seconds_delta: положительный = пополнение, отрицательный = списание
CREATE TABLE guide_minute_transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    session_id       UUID REFERENCES guide_sessions(id),
    transaction_type VARCHAR NOT NULL,
    seconds_delta    INTEGER NOT NULL,
    balance_after    INTEGER NOT NULL,
    package_id       VARCHAR,
    iap_purchase_id  UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_guide_transactions_user_id ON guide_minute_transactions(user_id);
CREATE INDEX idx_guide_transactions_session ON guide_minute_transactions(session_id);

-- Валидированные IAP-чеки
CREATE TABLE guide_iap_purchases (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id),
    platform                VARCHAR NOT NULL,   -- apple | google
    product_id              VARCHAR NOT NULL,
    transaction_id          VARCHAR NOT NULL UNIQUE,
    original_transaction_id VARCHAR,
    minutes_purchased       INTEGER NOT NULL,
    price_usd               FLOAT,
    validated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status                  VARCHAR NOT NULL DEFAULT 'valid'  -- valid | revoked | refunded
);
CREATE INDEX idx_guide_iap_user_id ON guide_iap_purchases(user_id);

-- Пакеты минут (справочник)
CREATE TABLE guide_packages (
    id                VARCHAR PRIMARY KEY,   -- "guide_30min"
    minutes           INTEGER NOT NULL,
    price_usd         FLOAT NOT NULL,
    apple_product_id  VARCHAR NOT NULL,
    google_product_id VARCHAR NOT NULL,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

-- Задания City Seeder (статус-трекинг)
CREATE TABLE guide_seed_jobs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_name      VARCHAR NOT NULL,
    status         VARCHAR NOT NULL DEFAULT 'running',
    -- running | awaiting_zone_approval | placing_points
    -- building_graph | collecting_knowledge | generating_content | complete | failed
    current_phase  VARCHAR,
    city_id        UUID REFERENCES guide_cities(id),
    progress_json  JSONB NOT NULL DEFAULT '{}',
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at   TIMESTAMPTZ
);
```

### Ключевые PostGIS-запросы

```sql
-- Ближайшие точки к пользователю (навигация)
SELECT id, name, point_type,
       ST_Distance(location::geography,
                   ST_SetSRID(ST_MakePoint($lng, $lat), 4326)::geography) AS dist_m
FROM guide_points
WHERE zone_id = $zone_id
  AND is_active = TRUE
ORDER BY dist_m
LIMIT 10;

-- Зоны, в которых находится пользователь
SELECT z.id, z.name, z.theme
FROM guide_zones z
WHERE ST_Contains(z.boundary,
                  ST_SetSRID(ST_MakePoint($lng, $lat), 4326))
  AND z.is_active = TRUE;

-- Зоны в радиусе N км от пользователя (для discovery)
SELECT z.id, z.name, z.city_id,
       ST_Distance(z.boundary::geography,
                   ST_SetSRID(ST_MakePoint($lng, $lat), 4326)::geography) AS dist_m
FROM guide_zones z
WHERE ST_DWithin(z.boundary::geography,
                 ST_SetSRID(ST_MakePoint($lng, $lat), 4326)::geography,
                 $radius_m)
  AND z.is_active = TRUE
ORDER BY dist_m;

-- Проверка "уже прослушано" через guide_session_visits (заменяет UUID[])
SELECT EXISTS(
    SELECT 1 FROM guide_session_visits
    WHERE session_id = $session_id AND point_id = $point_id
);

-- Последние 5 GPS-точек сессии для вычисления направления
SELECT lat, lng, heading_deg, speed_mps, recorded_at
FROM guide_session_gps_log
WHERE session_id = $session_id
ORDER BY recorded_at DESC
LIMIT 5;
```

---

## 3. API-спецификация

### 3.1. Клиентский API (`/api/guide/`) — требует JWT-аутентификации

#### Coverage & Zones

**`GET /api/guide/coverage`**
```
Query: lat, lng, radius_km=5.0
Response: {
  zones: [
    {
      id, name, theme, city_name,
      boundary_geojson: GeoJSON Polygon,
      poi_count, voice_options: [VoiceOption],
      distance_m: float,
      is_user_inside: bool
    }
  ]
}
```

**`GET /api/guide/zones/{zone_id}`**
```
Response: {
  id, name, description, theme,
  boundary_geojson, point_count,
  available_voices: [VoiceOption],
  available_languages: ["en", "ru"],
  sample_audio_url: str             -- 15-секундное превью
}
```

#### Sessions

**`POST /api/guide/sessions`**
```
Request: {
  zone_id: UUID,
  voice_id: UUID | null,       -- если null: берётся из guide_user_preferences
  language: str | null,        -- если null: берётся из guide_user_preferences
  detail_level: str | null,    -- если null: берётся из guide_user_preferences
  initial_location: {lat, lng}
}
Response: {
  session_id: UUID,
  balance_seconds: int,
  trial_seconds_remaining: int,
  preload_content: [PointContent]   -- 8 ближайших точек с CDN URL аудио
}
```
*Примечание: сервер обращается к `guide_user_preferences` при отсутствии явных параметров. После создания сессии — обновляет preferences выбранными значениями.*

**`POST /api/guide/sessions/{session_id}/heartbeat`**
```
Request: {
  seconds_active: int,             -- секунды активного рассказа (~30)
  location: {lat, lng},
  heading_deg: float | null
}
Response: {
  seconds_remaining: int,
  continue: bool,                  -- false при нулевом балансе или paused
  stop_reason: str | null,         -- "balance_empty" | "out_of_zone" | "paused"
  nearby_content: [PointContent]   -- свежий preload (если позиция изменилась > 50м)
}
```
*Если сессия в статусе `paused` — вернуть `{continue: false, stop_reason: "paused"}` без списания минут. Клиент должен явно вызвать `/resume`.*

**`POST /api/guide/sessions/{session_id}/pause`**
```
Response: { paused_at: datetime, seconds_billed_total: int }
```

**`POST /api/guide/sessions/{session_id}/resume`**
```
Response: {
  resumed_at: datetime,
  seconds_remaining: int,
  recap_content: PointContent | null    -- Предзаписанный recap-блок последней посещённой точки
    -- (content_type='recap', выбирается по voice_id + language + detail_level='standard').
    -- Если recap-блок не найден в guide_content_blocks — fallback на первые 2 предложения main.
}
```
*`recap_content` — предзаписанный recap-блок из `guide_content_blocks` для последней точки из `guide_session_visits` (последняя запись по `visited_at`). Навигационный движок переходит в состояние RESUMING (см. §5).*

**`POST /api/guide/sessions/{session_id}/end`**
```
Request: { exit_reason: "manual" | "out_of_zone" | "balance_empty" }
Response: SessionSummary
```

**`GET /api/guide/sessions/{session_id}/summary`**
```
Response: {
  session_id, zone_name, started_at, ended_at,
  duration_seconds: int,
  minutes_used: float,
  points_visited: int,
  path_geojson: GeoJSON LineString,  -- из guide_session_gps_log
  questions_asked: int,
  balance_remaining_seconds: int
}
```

**`GET /api/guide/sessions/history`** *(новый)*
```
Query: limit=20, offset=0
Response: {
  sessions: [
    {
      session_id, zone_name, city_name, started_at, ended_at,
      minutes_used, points_visited, questions_asked,
      rating: int | null
    }
  ]
}
```

**`POST /api/guide/sessions/{session_id}/rate`** *(новый)*
```
Request: { rating: int (1-5), review_text: str | null }
Response: { session_id, rating, updated_at }
```
*Обновляет `guide_sessions.rating` и `guide_sessions.review_text`. Логирует `guide_analytics_events` с `event_type='session_rated'`.*

#### Navigation

**`GET /api/guide/navigation/next`**
```
Query: session_id, lat, lng, heading_deg (optional), gps_accuracy_m
Response: {
  current_point_id: UUID | null,
  effective_detail_level: str,         -- добавлено: 'brief' | 'standard'; может отличаться от session.detail_level при высокой скорости (speed_mps ≥ 2.0 → 'brief')
  nearest_points: [
    {
      point_id, name, dist_m, bearing_deg,
      is_in_trigger_radius: bool,
      already_visited: bool,
      content: {
        main_audio_url, main_duration_s,   -- блок выбирается по effective_detail_level
        bonus_audio_url, bonus_duration_s,
        transitions: { to_point_id: audio_url }
      }
    }
  ],
  navigation_state: "INIT"|"RESUMING"|"NARRATING"|"TRANSITIONING"|"AT_BONUS"|"OUT_OF_ZONE"
}
```

#### Streaming Q&A

**`POST /api/guide/qa/ask`** — Server-Sent Events
```
Request (multipart/form-data):
  session_id: UUID
  audio: binary (WAV/M4A, max 30s, max 5MB)
  current_point_id: UUID | null

SSE Events:
  event: transcript   data: {"text": "Кто построил эту башню?"}
  event: answer_chunk data: {"text": "Эйфелева башня была построена..."}
  -- Первый аудиочанк: base64 inline (без задержки upload→CDN, цель < 2.5 сек)
  event: audio_chunk  data: {"base64": "SUQzBA...", "chunk_index": 0, "mime": "audio/mpeg"}
  -- Последующие чанки: CDN URL
  event: audio_chunk  data: {"url": "https://cdn.../chunk_1.mp3", "chunk_index": 1}
  event: done         data: {"qa_entry_id": UUID}
  event: error        data: {"code": "stt_failed", "message": "..."}
```

#### Billing & Balance

**`GET /api/guide/balance`**
```
Response: {
  seconds_remaining: int,
  minutes_remaining: float,
  trial_minutes_remaining: float,
  last_purchase_at: datetime | null
}
```

**`GET /api/guide/packages`**
```
Response: {
  packages: [
    {
      id: "guide_30min",
      minutes: 30, price_usd: 4.99,
      apple_product_id: "com.locally.guide.minutes30",
      google_product_id: "guide_30min",
      label: "Try It"
    }
  ]
}
```

**`POST /api/guide/purchases/validate`**
```
Request: {
  platform: "apple" | "google",
  receipt_data: str,       -- base64 receipt (Apple) или purchase token (Google)
  product_id: str,
  transaction_id: str
}
Response: {
  success: bool,
  minutes_credited: int,
  new_balance_seconds: int,
  transaction_id: str
}
Errors: 409 (duplicate), 400 (invalid receipt), 429 (rate limit)
```

**`POST /api/guide/purchases/refund-webhook`** *(новый)*
```
Request: {
  platform: "apple" | "google",
  transaction_id: str,
  notification_type: str  -- "REFUND" (Apple) или "CANCELED" (Google)
}
Response: { processed: bool }
```
*Вызывается App Store Server Notifications / Google RTDN. Обновляет статус покупки и корректирует баланс (см. §8).*

---

### 3.2. Admin API (`/api/guide/admin/`) — требует admin-роли в JWT

**`POST /api/guide/admin/seed`**
```
Request: { city_name: str, country: str | null }
Response: { job_id: UUID, status: "running" }
```

**`GET /api/guide/admin/seed/{job_id}`**
```
Response: {
  job_id, city_name, status, current_phase,
  progress: { zones_found, points_placed, edges_built, cards_collected },
  error_message: str | null, created_at, completed_at
}
```

**`GET /api/guide/admin/zones?city_id=&status=pending_approval`**
```
Response: { zones: [ZoneAdminView with boundary_geojson] }
```

**`PUT /api/guide/admin/zones/{zone_id}/approve`**
```
Request: { approved: bool, adjusted_boundary_geojson: GeoJSON | null }
Response: { zone_id, is_approved, approved_at }
```

**`GET /api/guide/admin/zones/{zone_id}/points`**
```
Response: {
  points: [{ id, name, point_type, lat, lng, trigger_radius_m,
              is_approved, neighbor_count, content_status }]
}
```

**`PUT /api/guide/admin/points/{point_id}`**
```
Request: { lat, lng, trigger_radius_m, is_active }
Response: PointAdminView
```

**`POST /api/guide/admin/content/generate`**
```
Request: { zone_id: UUID, voice_ids: [UUID] | null, force_regenerate: bool }
Response: { job_id: UUID, blocks_queued: int }
```

**`POST /api/guide/admin/content/synthesize`**
```
Request: { zone_id: UUID, voice_ids: [UUID] | null }
Response: { job_id: UUID, files_queued: int }
```

**`GET /api/guide/admin/content/status?zone_id=`**
```
Response: {
  total_blocks, ready, pending, failed,
  voices: [{ voice_id, name, ready_pct }]
}
```

**`GET /api/guide/admin/content/review?zone_id=&status=needs_manual_review`** *(новый)*
```
Response: {
  blocks: [
    {
      id, point_name, content_type, language, voice_name,
      text_script, coherence_score, review_notes, generation_status
    }
  ]
}
```

**`PUT /api/guide/admin/content/{block_id}/review`** *(новый)*
```
Request: {
  action: "approve" | "edit" | "regenerate",
  edited_text: str | null,      -- для action="edit"
  review_notes: str | null
}
Response: { block_id, generation_status, reviewed_at }
```
*`approve` → `generation_status='reviewed'`. `edit` → обновляет text_script, `generation_status='reviewed'`. `regenerate` → `generation_status='pending'`, ставит в очередь LLM.*

**`POST /api/guide/admin/content/validate`** *(новый)*
```
Request: { zone_id: UUID, language: str | null }
Response: { job_id: UUID, blocks_queued: int }
```
*Запускает валидацию связности для всех draft-блоков зоны. Пороги: transitions/zone_transition ≥ 4.0; main/bonus/recap ≥ 3.5. Блоки ниже порога → `needs_manual_review`.*

**`GET /api/guide/admin/analytics/dashboard`** *(новый)*
```
Query: city_id (optional), period_days=30
Response: {
  sessions_total: int,
  sessions_by_zone: [{ zone_name, count, avg_duration_min }],
  avg_session_duration_min: float,
  avg_questions_per_session: float,
  trial_to_purchase_conversion_pct: float,
  minutes_used_total: float,
  top_points: [{ point_name, visit_count }],
  revenue_usd: float
}
```

---

## 4. City Seeder — автоматическая разметка городов

### Единая CLI-команда

```bash
python -m src.guide.application.seeder.orchestrator \
    --city "Paris" --country "France"
```

Или через Admin API: `POST /api/guide/admin/seed`

### Пайплайн

```
seed(city_name)
    │
    ├─► ZoneDiscovery.discover()
    │     ├─ Google Places Nearby Search (10 типов POI, радиус 15 км):
    │     │   tourist_attraction, museum, church, historic_site,
    │     │   park, monument, art_gallery, library, landmark, palace
    │     ├─ DBSCAN кластеризация (eps=400m, min_samples=10, metric=haversine)
    │     ├─ Convex hull → PostGIS Polygon per cluster
    │     ├─ Автоименование зоны: самый значимый POI кластера (max rating×log(reviews))
    │     │   Fallback: Google Maps reverse geocoding центроида кластера → название района
    │     └─ Вставка в guide_zones (is_approved=FALSE), обновление guide_seed_jobs
    │
    ├─► [РУЧНОЕ РЕВЬЮ]
    │   Admin API: GET /admin/zones?status=pending_approval
    │              PUT /admin/zones/{id}/approve (± корректировка границы)
    │   Seeder ждёт (polling job status или webhook)
    │
    ├─► PointPlacement.place(zone_id) — для каждой утверждённой зоны
    │     ├─ Google Places Nearby Search внутри zone.boundary bbox
    │     ├─ Фильтрация: rating >= 4.0, reviews >= 50
    │     ├─ Ранжирование: score = rating × log10(reviews + 1)
    │     ├─ Top-50 POI → guide_points (type='poi')
    │     ├─ OSMnx: load_graph(bbox, network_type='walk')
    │     ├─ Интерполяция связующих точек каждые 80-100m на рёбрах графа
    │     └─ Вставка connector points → guide_points (type='connector')
    │
    ├─► GraphBuilder.build(zone_id)
    │     ├─ Загрузка всех точек зоны из БД
    │     ├─ Проекция на OSMnx граф: ox.nearest_nodes()
    │     ├─ networkx.shortest_path к k=4 ближайшим точкам per point
    │     │   (pre-filter: только точки в радиусе max_walking_distance_m по прямой)
    │     ├─ Создание направленных рёбер A→B и B→A
    │     ├─ Расчёт bearing_deg = atan2(Δlng, Δlat)
    │     └─ Bulk insert в guide_edges
    │
    └─► KnowledgeCollector.collect(zone_id)
          ├─ Для POI-точек (type='poi'):
          │   ├─ Google Place Details: name, rating, reviews, photos, editorial_summary
          │   ├─ Wikipedia API: search(name) → extract первый параграф
          │   └─ Wikidata SPARQL: built_year, architect, architectural_style, ...
          ├─ Для connector-точек (type='connector'):
          │   └─ Google Maps Reverse Geocoding → street_name
          │       Сохраняется в guide_knowledge_cards с card_type='street_context'
          │       (используется как контекст для Q&A на промежуточных точках)
          └─ Upsert guide_knowledge_cards
```

### ZoneDiscovery: алгоритм кластеризации + автоименование

```python
# zone_discovery.py
import numpy as np
from sklearn.cluster import DBSCAN
from shapely.geometry import MultiPoint

async def discover(city_name: str, center_lat: float, center_lng: float) -> list[ProposedZone]:
    pois = await google_places.nearby_search_all(
        lat=center_lat, lng=center_lng,
        radius=15000,
        types=TOURIST_POI_TYPES
    )

    coords = np.array([[p.lat, p.lng] for p in pois])
    eps_rad = settings.seeder_dbscan_eps_m / 6_371_000  # метры → радианы
    labels = DBSCAN(
        eps=eps_rad, min_samples=settings.seeder_dbscan_min_samples,
        metric='haversine'
    ).fit_predict(np.radians(coords))

    zones = []
    for cluster_id in set(labels) - {-1}:
        cluster_pois = [p for p, l in zip(pois, labels) if l == cluster_id]
        hull = MultiPoint([(p.lng, p.lat) for p in cluster_pois]).convex_hull

        # Автоименование: самый значимый POI (rating × log(reviews+1))
        anchor_poi = max(
            cluster_pois,
            key=lambda p: (p.rating or 0) * math.log10((p.user_ratings_total or 0) + 1)
        )
        zone_name = anchor_poi.name

        # Fallback: reverse geocoding центроида кластера
        if not zone_name:
            centroid = hull.centroid
            zone_name = await google_places.reverse_geocode_neighborhood(
                lat=centroid.y, lng=centroid.x
            ) or f"{city_name} Zone {cluster_id + 1}"

        zones.append(ProposedZone(
            name=zone_name,
            boundary_wkt=hull.wkt,
            poi_count=len(cluster_pois),
            top_poi_names=[p.name for p in cluster_pois[:5]]
        ))

    return zones
```

### GraphBuilder: алгоритм построения графа (с оптимизацией)

```python
# graph_builder.py
import osmnx as ox
import networkx as nx

# Производительность: для зоны 100 точек без pre-filter → 100×99 = 9900 shortest_path запросов.
# С pre-filter по прямой дистанции 300м → в среднем 10-15 кандидатов на точку → ~1200 запросов.
# Ускорение ≈ 8×. При 300 точках разница критична (90K vs ~9K запросов).
MAX_WALKING_DISTANCE_M = 300  # настраивается через seeder_max_neighbor_distance_m

async def build(zone_id: UUID) -> None:
    points = await db.fetch_active_points(zone_id)
    zone = await db.fetch_zone(zone_id)

    G = ox.graph_from_polygon(zone.boundary_shapely, network_type='walk')
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    point_nodes = {
        p.id: ox.nearest_nodes(G, p.longitude, p.latitude)
        for p in points
    }

    edges_to_insert = []
    for p in points:
        # Pre-filter: только точки в радиусе MAX_WALKING_DISTANCE_M по прямой
        # (shortest_path всегда ≥ прямой дистанции, поэтому отсев безопасен)
        nearby_points = [
            q for q in points
            if q.id != p.id
            and haversine_m(p.lat, p.lng, q.lat, q.lng) <= MAX_WALKING_DISTANCE_M
        ]

        distances = {}
        for q in nearby_points:
            try:
                dist = nx.shortest_path_length(
                    G, point_nodes[p.id], point_nodes[q.id], weight='travel_time'
                )
                distances[q.id] = dist
            except nx.NetworkXNoPath:
                continue

        for neighbor_id, travel_time in sorted(distances.items(), key=lambda x: x[1])[:4]:
            neighbor = next(q for q in points if q.id == neighbor_id)
            edges_to_insert.append(GuideEdge(
                from_point_id=p.id,
                to_point_id=neighbor_id,
                distance_m=haversine_m(p.lat, p.lng, neighbor.lat, neighbor.lng),
                walk_seconds=int(travel_time),
                bearing_deg=atan2_bearing(p.lat, p.lng, neighbor.lat, neighbor.lng)
            ))

    await db.bulk_insert_edges(edges_to_insert)
```

### Идемпотентность

- `guide_points`: UNIQUE(zone_id, google_place_id) и UNIQUE(zone_id, osm_node_id)
- `guide_edges`: UNIQUE(from_point_id, to_point_id)
- Повторный запуск seeder для того же города проверяет последний незавершённый job в `guide_seed_jobs`

---

## 5. Навигационный движок

### Стейт-машина сессии

```
          start_session()
               │
               ▼
           ┌───────┐
           │ INIT  │  intro segment (10-15s, направление ещё не определено)
           └───┬───┘
               │ direction_established() или timeout 15s
               ▼
        ┌────────────┐
        │ NARRATING  │  основной контент текущей точки
        └──┬──────┬──┘
    next() │      │ user_stopped (>2 мин)
           │      ▼
           │  ┌──────────┐
           │  │ AT_BONUS │  бонусный контент
           │  └──────────┘
           ▼
    ┌──────────────┐
    │ TRANSITIONING│  переходная фраза к следующей точке
    └──────┬───────┘
           │ arrived_at_next_point()
           ▼
        NARRATING (следующая точка)

Из любого состояния:
  pause()         → PAUSED    (минуты не списываются)
  resume()        → RESUMING  (короткий recap, затем → NARRATING)
  ask_question()  → ANSWERING → предыдущее состояние
  zone_change()   → TRANSITIONING (zone_transition контент)
  out_of_zone()   → ENDED (exit_reason='out_of_zone')
  balance=0       → ENDED (exit_reason='balance_empty')
```

**Состояние RESUMING** добавлено между `pause()` и `NARRATING`. При `resume()`:
Воспроизводится предзаписанный recap-блок (`content_type='recap'`) для последней посещённой точки
(из `guide_session_visits`, последняя запись по `visited_at`).
Выбирается по `voice_id + language + detail_level='standard'` — recap всегда фиксированной длины (15–25 слов).
Fallback: если recap-блок отсутствует в `guide_content_blocks` → берутся первые 2 предложения main-нарратива.
После воспроизведения → `NARRATING`.

### Алгоритм определения ближайшей точки и направления

```python
# navigation_engine.py
async def process_location_update(
    session: GuideSession,
    lat: float,
    lng: float,
    heading_deg: float | None,
    gps_accuracy_m: float,
    db: AsyncSession,
) -> NavigationResult:

    # 1. Запись GPS в guide_session_gps_log
    await db.execute(
        insert(GpsLog).values(
            session_id=session.id, lat=lat, lng=lng,
            heading_deg=heading_deg, accuracy_m=gps_accuracy_m
        )
    )

    # 2. Игнорировать GPS-аномалии (прыжок > 500 м за 30 сек)
    if session.last_known_location:
        if haversine_m(session.last_known_location, (lat, lng)) > 500:
            return NavigationResult(action='hold', reason='gps_anomaly')

    # 3. PostGIS: 10 ближайших активных точек
    nearest = await db.nearest_points(zone_id=session.zone_id, lat=lat, lng=lng, limit=10)

    # 4. Проверка смены зоны: ближайшие точки принадлежат другой зоне
    if nearest and nearest[0].zone_id != session.zone_id:
        new_zone_id = nearest[0].zone_id
        # Отдаём zone_transition контент (content_type='zone_transition')
        transition_block = await db.get_zone_transition_content(
            from_zone_id=session.zone_id,
            to_zone_id=new_zone_id,
            voice_id=session.voice_id,
            language=session.language,
        )
        # Обновляем session.zone_id
        await db.update_session_zone(session.id, new_zone_id)
        return NavigationResult(
            action='play_zone_transition',
            audio_url=transition_block.audio_url if transition_block else None,
            new_zone_id=new_zone_id,
        )

    if not nearest:
        return NavigationResult(action='out_of_zone')

    # 5. Точки в радиусе триггера, ещё не прослушанные
    # Используем JOIN к guide_session_visits вместо UUID-массива
    visited_ids = await db.get_visited_point_ids(session.id)
    triggered = [
        p for p in nearest
        if p.dist_m <= p.trigger_radius_m + gps_accuracy_m
        and p.id not in visited_ids
    ]
    if triggered:
        # Выбор detail_level по скорости движения
        speed = await get_current_speed(session.id, db)
        detail_level = _speed_to_detail_level(speed, session.detail_level)
        return NavigationResult(
            action='serve_main',
            point_id=triggered[0].id,
            detail_level=detail_level,
        )

    # 6. Определить направление движения
    # Берём последние 3 GPS-точки из guide_session_gps_log
    bearing = heading_deg
    if bearing is None:
        recent_gps = await db.get_recent_gps(session.id, limit=3)
        if len(recent_gps) >= 3:
            bearing = compute_bearing_from_track(recent_gps)

    if bearing is not None:
        current_point = nearest[0]
        edges = await db.get_edges_from(current_point.id)
        best_edge = min(edges, key=lambda e: angular_diff(e.bearing_deg, bearing))
        if angular_diff(best_edge.bearing_deg, bearing) < 60:
            return NavigationResult(
                action='play_transition',
                from_point_id=current_point.id,
                to_point_id=best_edge.to_point_id,
                edge_id=best_edge.id,
            )

    # 7. Пользователь стоит — hold (бонус выдаётся отдельной логикой по таймеру)
    return NavigationResult(action='hold')
```

### Адаптация темпа к скорости движения

```python
def _speed_to_detail_level(speed_mps: float, session_default: str) -> str:
    """
    Скорость влияет на выбор content_block: при высокой скорости сервер отдаёт
    brief-вариант (короткий нарратив), при низкой/стоянии — standard + bonus.
    Выбор происходит через поле guide_content_blocks.language при запросе контента.
    """
    if speed_mps >= 2.0:   # бег/транспорт → brief
        return 'brief'
    elif speed_mps < 0.5:  # стоит → standard (+ bonus будет запрошен таймером)
        return 'standard'
    return session_default  # скорость ходьбы → из настроек сессии
```

### Предзагрузка контента

При `POST /sessions` и при heartbeat (если позиция сместилась > 50 м) сервер возвращает `nearby_content` — CDN URLs аудио для 8 ближайших точек. Клиент кэширует локально, обеспечивая работу при кратковременном отсутствии интернета.

```json
{
  "nearby_content": [
    {
      "point_id": "uuid",
      "main_audio_url": "https://cdn.locally.app/guide/audio/.../main.mp3",
      "main_duration_s": 45.2,
      "bonus_audio_url": "https://cdn.locally.app/guide/audio/.../bonus.mp3",
      "transitions": {
        "uuid_neighbor_1": "https://cdn.locally.app/guide/audio/.../trans_0.mp3",
        "uuid_neighbor_2": "https://cdn.locally.app/guide/audio/.../trans_1.mp3"
      }
    }
  ]
}
```

### Edge-кейсы

| Ситуация | Поведение |
|----------|-----------|
| GPS прыжок > 500 м | Игнорировать; держать последнюю надёжную позицию |
| Пользователь стоит > 2 мин | Перейти в AT_BONUS; предложить бонусный контент |
| Возврат к прослушанной точке | JOIN к guide_session_visits: уже есть → не повторять main; предложить bonus |
| Переход между зонами | Обнаружение через смену zone_id ближайших точек → play_zone_transition |
| Пропущенный heartbeat > 65 сек | Фоновая задача → auto-pause сессии |
| Нет интернета | Рассказ продолжается из кэша; heartbeats буферизуются |
| Входящий звонок | Пауза; при возврате resume() → RESUMING → краткий recap |
| Heartbeat на paused сессию | Вернуть `{continue: false, stop_reason: "paused"}` без списания |

---

## 6. Streaming Q&A Pipeline

### Архитектура

```
Client ──(audio, max 30s)──► POST /api/guide/qa/ask (SSE)
                                       │
                           ┌───────────▼────────────┐
                           │   1. Receive audio       │  multipart/form-data
                           │   Validate: size, MIME   │
                           └───────────┬────────────┘
                                       │
                           ┌───────────▼────────────┐
                           │   2. STT                │  Deepgram nova-2 / Whisper
                           │   ~0.3–0.8 с            │
                           └───────────┬────────────┘
                                       │ transcript
                           ┌───────────▼────────────┐
                           │   3. Build LLM context  │
                           │   current_point + 2-3   │
                           │   neighbors + qa_history │
                           │   (из guide_session_qa) │
                           └───────────┬────────────┘
                                       │ prompt
                           ┌───────────▼────────────┐
                           │   4. LLM streaming      │  io.net, max_tokens=150
                           │   ~0.5–1.5 с first token│
                           └───────────┬────────────┘
                                       │ text chunks (побуквенно)
                           ┌───────────▼────────────┐
                           │   5. TTS streaming      │  ElevenLabs WebSocket
                           │   Буферизация до первого│  ~0.3–0.5 с first chunk
                           │   законченного предл.   │
                           └───────────┬────────────┘
                                       │ Чанк 0 → base64 inline (SSE, без S3)
                                       │ Чанки 1+ → upload S3 → CDN URL
                           SSE events → Client
```

**Итого до начала воспроизведения: < 2.5 сек**

Ключевые приёмы:
1. TTS начинает синтезировать первое предложение сразу после получения ~50 символов от LLM.
2. **Первый аудиочанк** отправляется клиенту как `base64` прямо в SSE-событии, минуя upload→CDN. Это устраняет ~200-500 мс задержки на загрузку в S3. Последующие чанки отдаются через CDN URL как обычно.

### Формирование LLM-контекста

```python
def build_qa_context(
    session: GuideSession,
    current_point: GuidePoint,
    neighbors: list[GuidePoint],
    knowledge_cards: dict[UUID, KnowledgeCard],
    qa_history: list[SessionQA],  # последние 5 записей из guide_session_qa
    question: str,
) -> str:
    card = knowledge_cards.get(current_point.id)

    # Fallback для connector-точек: взять knowledge_card ближайшей POI-точки.
    # Connector-точки не имеют Wikipedia/Wikidata, но у них есть street_context.
    # Если card есть и это street_context — используем её как вспомогательный контекст,
    # но основные знания берём у ближайшей POI-точки.
    if card and card.card_type == 'street_context':
        poi_card = next(
            (knowledge_cards.get(n.id) for n in neighbors if n.point_type == 'poi'),
            None,
        )
        location_context = f"On {card.street_name}. Nearby: {poi_card.point_name if poi_card else 'unknown area'}"
        main_knowledge = poi_card.wikipedia_summary if poi_card else ''
    else:
        location_context = current_point.name or ''
        main_knowledge = card.wikipedia_summary if card else 'No information available.'

    history_text = '\n'.join(
        f"Q: {qa.question_text}\nA: {qa.answer_text}"
        for qa in qa_history[-5:]
    )

    return f"""You are an audio guide. The user is near: {location_context}.

About this place:
{main_knowledge}

Nearby: {', '.join(n.name for n in neighbors[:3] if n.name)}

Previous Q&A this session:
{history_text}

User question: {question}

Answer in {session.language}, {session.detail_level} style.
Keep to 2-4 sentences (spoken audio, not text).
End with a natural bridge back to the tour narrative."""
```

### Защита и ограничения

- **Лимит вопросов пропорциональный:** max 1 вопрос на 90 секунд рассказа.
  `max_qa = max(1, session.total_seconds_billed // 90)`
  Минимум 1 вопрос доступен всегда (даже в начале сессии). При превышении → HTTP 429 с `Retry-After`.
- Max длина аудио: 30 сек / 5 МБ
- Транскрипт обрезается до 200 символов
- LLM timeout: `guide_qa_llm_timeout_seconds` (default 8 сек)
- STT failure → SSE `event: error`, клиент показывает «Не расслышал»
- LLM timeout → заглушка: «Хороший вопрос! Уточню, когда вернёмся»
- После каждого Q&A → INSERT в `guide_session_qa` + аналитическое событие `question_asked`

---

## 7. Контентный пайплайн (batch)

### Связь с City Seeder

```
guide_knowledge_cards (собраны City Seeder)
    │
    ├─► LLM batch (io.net) — генерация черновиков (guide_content_jobs: generate_drafts)
    │     Для каждой POI-точки × каждый голос × язык:
    │       main:       generate_narrative(card, voice, 'main')   → content_block (status=draft)
    │       bonus:      generate_narrative(card, voice, 'bonus')  → content_block (status=draft)
    │     Для каждого ребра × каждый голос × язык:
    │       transition: generate_transition(from, to, voice, variant=0/1/2) → status=draft
    │     Для смены зон:
    │       zone_transition: generate_zone_transition(from_zone, to_zone, voice) → status=draft
    │
    ├─► Автоматическая валидация (guide_content_jobs: validate)
    │     LLM-валидатор оценивает coherence_score (1–5) для каждого черновика
    │     transitions/zone_transition: score ≥ 4.0 → validated; < 4.0 → retry (до 3) → needs_manual_review
    │     main/bonus/recap: score ≥ 3.5 → validated; < 3.5 → needs_manual_review
    │
    ├─► [РУЧНОЙ РЕВЬЮ] Admin API: GET /admin/content/review
    │     PUT /admin/content/{id}/review (approve / edit / regenerate)
    │     status=reviewed — готово к синтезу
    │
    └─► ElevenLabs TTS batch (guide_content_jobs: synthesize)
          Для каждого content_block со статусом validated или reviewed:
            ElevenLabs.synthesize_batch(text_script, voice.elevenlabs_voice_id)
            → upload S3: guide/audio/{zone_id}/{point_id}/{voice_id}/{lang}/{type}_{variant}.mp3
            → CDN URL → UPDATE: audio_url, audio_duration_seconds,
                                 generation_status='synthesized'
```

### LLM-промпты

**Основной нарратив:**
```python
def build_narrative_prompt(point, card, voice, detail_level):
    style_desc = {
        "academic":  "scholarly, precise, rich with historical context",
        "friendly":  "warm, conversational, with local anecdotes and humor",
        "dramatic":  "vivid, story-driven, with suspense and atmosphere",
        "minimal":   "concise, essential facts only",
    }[voice.style_group]
    word_count = {"brief": "60-80", "standard": "120-160"}[detail_level]

    return f"""Write an audio guide narrative for: {point.name}
Style: {style_desc} | Language: {voice.language} | Length: {word_count} words

Knowledge:
- Wikipedia: {card.wikipedia_summary}
- Wikidata: {json.dumps(card.wikidata_facts or {})}
- Google: {card.google_place_data.get('editorial_summary', {}).get('overview', '')}

Rules: Write for listening (no lists, no headers). Use sensory language.
End at a natural pause. Never cite sources."""
```

**Переходные фразы:**
```python
def build_transition_prompt(from_point, to_point, voice, variant):
    return f"""Write a 15-25 word spoken transition phrase for an audio guide.

Walking FROM: {from_point.name} → TOWARD: {to_point.name}
Style: {voice.style_group} | Language: {voice.language} | Variant {variant+1}/3

Acknowledge leaving, build anticipation for next place.
Sound like natural speech. Avoid robotic "now let's go to..."."""
```

**Смена зоны (zone_transition):**
```python
def build_zone_transition_prompt(from_zone, to_zone, voice):
    return f"""Write a 20-35 word spoken transition for an audio guide when the visitor
walks from one area to another.

Leaving: {from_zone.name} (theme: {from_zone.theme})
Entering: {to_zone.name} (theme: {to_zone.theme})
Style: {voice.style_group} | Language: {voice.language}

Acknowledge the change of area naturally. Build interest in the new zone."""
```

---

## 8. Биллинг

### Heartbeat механизм

```
Client → POST /sessions/{id}/heartbeat {seconds_active: 30, location: {...}}
    │
    ▼
1. Проверить session.status:
   • 'paused'  → вернуть {continue: false, stop_reason: "paused"} (без списания)
   • 'ended'   → вернуть {continue: false, stop_reason: "ended"}
   • 'active'  → продолжить

2. Cap debit: min(seconds_active, heartbeat_interval + grace) = min(30, 35) = 30

3. Порядок списания: сначала trial, потом purchased.
   Atomic PostgreSQL (два UPDATE в одной транзакции):

   -- Сколько trial осталось
   SELECT trial_seconds_granted - trial_seconds_used AS trial_remaining
   FROM guide_minute_balances WHERE user_id = $user_id FOR UPDATE;

   IF trial_remaining >= $debit:
       UPDATE guide_minute_balances SET trial_seconds_used = trial_seconds_used + $debit
       WHERE user_id = $user_id;
       debit_source = 'trial'
   ELIF trial_remaining > 0:
       trial_debit = trial_remaining
       purchased_debit = $debit - trial_remaining
       UPDATE guide_minute_balances
       SET trial_seconds_used = trial_seconds_granted,  -- исчерпать trial
           seconds_remaining = seconds_remaining - purchased_debit
       WHERE user_id = $user_id AND seconds_remaining >= purchased_debit;
       debit_source = 'mixed'
   ELSE:
       UPDATE guide_minute_balances
       SET seconds_remaining = seconds_remaining - $debit
       WHERE user_id = $user_id AND seconds_remaining >= $debit
       RETURNING seconds_remaining;
       debit_source = 'purchased'

4. Если debit не прошёл (insufficient balance):
   end_session('balance_empty') → {continue: false, stop_reason: "balance_empty"}

5. Если прошёл:
   log guide_minute_transactions, update session.total_seconds_billed
   → {continue: true, seconds_remaining: N, nearby_content: [...]}
```

**Auto-pause пропущенных сессий:** фоновая задача каждые 60 сек ищет сессии с `last_heartbeat_at < NOW() - 65s AND status='active'` → переводит в `paused`. После этого любой heartbeat вернёт `stop_reason: "paused"`.

### IAP валидация

```python
# Apple
async def validate_apple(receipt_data: str, product_id: str) -> IAPResult:
    # POST https://buy.itunes.apple.com/verifyReceipt
    # Проверить: status=0, bundleId, productId, cancellationDate
    # INSERT INTO guide_iap_purchases ON CONFLICT(transaction_id) DO NOTHING
    # Если affected=0 → 409 (уже валидировалось)
    # Атомарно кредитовать секунды в guide_minute_balances

# Google Play
async def validate_google(purchase_token: str, product_id: str) -> IAPResult:
    # GET .../purchases/products/{productId}/tokens/{token} (OAuth2 service account)
    # Проверить purchaseState=0
    # consumePurchase
    # Аналогично Apple: check duplicate → credit
```

### Refund Flow

При получении refund-уведомления от Apple (App Store Server Notifications) или Google (RTDN):

```
POST /api/guide/purchases/refund-webhook
    │
    ▼
1. Найти guide_iap_purchases по transaction_id
2. Если status уже 'refunded' → 200 (идемпотентно, повторная нотификация)
3. UPDATE guide_iap_purchases SET status='refunded'
4. Рассчитать секунды к возврату: minutes_purchased × 60
5. Атомарный вычет (но не ниже 0):
   UPDATE guide_minute_balances
   SET seconds_remaining = GREATEST(0, seconds_remaining - $refund_seconds),
       updated_at = NOW()
   WHERE user_id = $user_id
   RETURNING seconds_remaining
6. INSERT INTO guide_minute_transactions (transaction_type='refund', seconds_delta=-N)
7. Если у пользователя есть активная сессия и новый баланс = 0 → auto-end сессии
```

*Примечание: вычет не уходит ниже 0 — если пользователь уже потратил больше, чем было в купленном пакете, отрицательный баланс не создаётся.*

### Fraud Protection

| Механизм | Реализация |
|----------|------------|
| Двойное кредитование | UNIQUE constraint на `guide_iap_purchases.transaction_id` |
| Накрутка heartbeat | Debit capped: `min(seconds_active, interval + grace_seconds)` |
| Злоупотребление validate | Rate limit: 10 req/hour/IP |
| Hard cap на сессию | Сессия не может списать > 7200 сек (2 часа) |
| Trial один раз | Check `trial_seconds_granted > 0` перед выдачей |
| Refund накрутка | Вычет не уходит ниже 0; idempotent по transaction_id |

---

## 9. Интеграции

### 9.1. ElevenLabs (TTS)

```python
# src/guide/infrastructure/elevenlabs_client.py

class ElevenLabsClient:
    async def synthesize_batch(self, text: str, voice_id: str) -> bytes:
        """Полный аудиофайл для контентного пайплайна."""
        # POST /v1/text-to-speech/{voice_id}
        # output_format: mp3_44100_128

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        voice_id: str,
    ) -> AsyncIterator[bytes]:
        """Streaming TTS для Q&A.
        Буферизует текст до первого законченного предложения (~50 символов),
        затем отправляет в ElevenLabs WebSocket."""
        # WebSocket /v1/text-to-speech/{voice_id}/stream-input
```

**Config:**
```bash
ELEVENLABS_API_KEY=...
ELEVENLABS_BASE_URL=https://api.elevenlabs.io
```

### 9.2. STT (Deepgram + Whisper fallback)

```python
# src/guide/infrastructure/stt_client.py

class STTClient(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str) -> str: ...

class DeepgramSTTClient(STTClient):
    # POST https://api.deepgram.com/v1/listen?model=nova-2&language={lang}

class WhisperSTTClient(STTClient):
    # POST https://api.openai.com/v1/audio/transcriptions
```

**Config:**
```bash
STT_PROVIDER=deepgram          # deepgram | whisper
DEEPGRAM_API_KEY=...
OPENAI_API_KEY=...             # для Whisper fallback
```

### 9.3. S3 / Object Storage

```python
# src/guide/infrastructure/s3_client.py (aioboto3)

async def upload_audio(key: str, data: bytes) -> str:
    """Upload mp3 → S3, вернуть CDN URL."""
    # key: guide/audio/{zone_id}/{point_id}/{voice_id}/{lang}/{type}_{variant}.mp3

async def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Временный URL для приватных файлов (Q&A чанки)."""
```

**Config:**
```bash
S3_ENDPOINT_URL=https://s3.amazonaws.com   # или Cloudflare R2
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=locally-audio-guide
CDN_BASE_URL=https://cdn.locally.app
```

### 9.4. IAP Validation

```bash
APPLE_BUNDLE_ID=com.locally.app
APPLE_SHARED_SECRET=...          # App Store Connect → App-Specific Shared Secret

GOOGLE_PLAY_PACKAGE_NAME=com.locally.app
GOOGLE_SERVICE_ACCOUNT_JSON=...  # base64-encoded service account JSON
```

### 9.5. Существующие интеграции (reuse)

- **Google Maps/Places API** — существующий клиент в `src/infrastructure/`. City Seeder использует его без изменений. Добавляется использование Reverse Geocoding для именования зон и connector-точек.
- **LLM (io.net)** — `src/infrastructure/llm_client.py` (IoNetLLMClient). Контентный пайплайн и Q&A используют с моделями `guide_narrative_model` и `guide_qa_model`.

### 9.6. Новые зависимости (requirements.txt)

```
osmnx>=1.9.0          # пешеходный граф (City Seeder)
networkx>=3.2         # граф-алгоритмы (shortest_path)
scikit-learn>=1.4     # DBSCAN кластеризация
shapely>=2.0          # геометрия (convex hull, contains)
geopandas>=0.14       # работа с GeoDataFrame
aioboto3>=12.0        # async S3
deepgram-sdk>=3.0     # STT
elevenlabs>=1.0       # TTS (официальный SDK)
wikipedia-api>=0.6    # Wikipedia summaries
```

### 9.7. Новые Config-переменные (src/config.py)

```python
# ElevenLabs
elevenlabs_api_key: str = Field(default="")
elevenlabs_base_url: str = Field(default="https://api.elevenlabs.io")

# STT
stt_provider: str = Field(default="deepgram")  # deepgram | whisper
deepgram_api_key: str = Field(default="")
openai_api_key: str = Field(default="")         # для Whisper fallback

# S3 / Object Storage
s3_endpoint_url: str = Field(default="")
s3_access_key_id: str = Field(default="")
s3_secret_access_key: str = Field(default="")
s3_bucket_name: str = Field(default="locally-audio-guide")
cdn_base_url: str = Field(default="")

# IAP
apple_bundle_id: str = Field(default="com.locally.app")
apple_shared_secret: str = Field(default="")
google_play_package_name: str = Field(default="com.locally.app")
google_service_account_json: str = Field(default="")  # base64

# Guide billing
guide_heartbeat_interval_seconds: int = Field(default=30)
guide_heartbeat_grace_seconds: int = Field(default=5)
guide_trial_minutes: int = Field(default=5)
guide_session_max_hours: int = Field(default=2)

# Guide navigation
guide_trigger_radius_default_m: int = Field(default=25)
guide_preload_point_count: int = Field(default=8)

# Guide LLM models
guide_narrative_model: str = Field(default="")  # fallback: trip_planning_model
guide_qa_model: str = Field(default="")         # fallback: trip_chat_model
guide_narrative_llm_timeout_seconds: int = Field(default=30)
guide_qa_llm_timeout_seconds: int = Field(default=8)

# City Seeder
seeder_dbscan_eps_m: float = Field(default=400.0)
seeder_dbscan_min_samples: int = Field(default=10)
seeder_min_poi_rating: float = Field(default=4.0)
seeder_min_poi_reviews: int = Field(default=50)
seeder_connector_interval_m: float = Field(default=80.0)
seeder_max_poi_per_zone: int = Field(default=50)
seeder_max_neighbor_distance_m: float = Field(default=300.0)  # GraphBuilder pre-filter
```

---

## 10. Нефункциональные требования

### Обработка ошибок и Graceful Degradation

| Сбой | Поведение |
|------|-----------|
| ElevenLabs Q&A недоступен | Вернуть текстовый ответ через SSE; клиент показывает субтитры |
| STT не распознал вопрос | SSE `event: error`; клиент предлагает повторить |
| LLM timeout в Q&A | Заглушка: «Хороший вопрос! Продолжу рассказ» |
| Пропущенный heartbeat > 65 сек | Фоновая задача → auto-pause |
| Google Places API down (Seeder) | Retry 3× exponential backoff; job → failed |
| CDN URL недоступен | Fallback на S3 presigned URL |
| Нет интернета у клиента | Рассказ из кэша; heartbeats буферизуются и отправляются при восстановлении |
| Refund при активной сессии с нулевым балансом | Auto-end сессии с exit_reason='balance_empty' |

### Логирование

Обязательные поля в каждом guide-запросе:
- `session_id`, `user_id`, `zone_id`
- `latency_ms` — для STT, LLM, TTS вызовов
- `seconds_debited`, `balance_after`, `debit_source` (trial/purchased/mixed) — в heartbeat
- `phase` — в City Seeder

### Масштабируемость

- **Навигационный движок** — stateless (вся сессия в PostgreSQL), горизонтальное масштабирование без sticky sessions
- **Heartbeat** — атомарный `UPDATE ... RETURNING` корректен при любом количестве инстансов
- **City Seeder** — один активный job на город (`SELECT FOR UPDATE` на guide_seed_jobs)
- **Контентный пайплайн** — отдельный background worker; не нагружает API-инстансы
- **Q&A SSE** — каждый запрос независимый async generator; при высокой нагрузке — перевести на выделенный WebSocket-сервер
- **guide_session_gps_log** — при > 100K сессий/месяц рассмотреть партиционирование по `recorded_at` (monthly)

### Безопасность

- **JWT auth** — все клиентские эндпоинты, используя существующий `src/auth/`
- **Admin endpoints** — отдельная проверка `role=admin` в JWT payload
- **IAP** — все транзакции только server-side; клиент не может изменить баланс
- **Refund webhook** — валидация подписи Apple/Google (HMAC или JWT) перед обработкой
- **Input validation** — Pydantic v2 для всех request-схем
- **Audio upload** — max 5 МБ, только `audio/*` MIME типы, max 30 сек

### Alembic-миграции

```
009_add_live_guide.py           — базовые таблицы (уже создан)
010_add_live_guide_normalized.py — новые нормализованные таблицы:
    guide_session_gps_log, guide_session_visits, guide_session_qa,
    guide_user_preferences, guide_analytics_events, guide_content_jobs
    + ALTER TABLE guide_sessions DROP COLUMN visited_point_ids, qa_history
    + ALTER TABLE guide_sessions ADD COLUMN rating, review_text
    + ALTER TABLE guide_content_blocks ADD COLUMN language, detail_level, zone_id, coherence_score, review_*
    + CREATE UNIQUE INDEX idx_guide_content_uq_no_edge, idx_guide_content_uq_with_edge
    + ALTER TABLE guide_knowledge_cards ADD COLUMN card_type, street_name
    + ALTER TABLE guide_voices ADD COLUMN style_group + UNIQUE constraint
```

```bash
make db-upgrade   # применить миграции
```
