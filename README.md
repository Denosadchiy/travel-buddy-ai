# Trip Planning API

Backend API for AI-powered trip planning. This service handles user inputs, chat interactions, and generates optimized travel itineraries.

## Architecture

The backend is organized in 4 layers:

1. **HTTP/API Layer** (`src/api/`) - FastAPI routers and endpoints
2. **Application/Services Layer** (`src/application/`) - Business logic orchestrators
3. **Domain Layer** (`src/domain/`) - Core business models (Pydantic)
4. **Infrastructure Layer** (`src/infrastructure/`) - Database, LLM client, external APIs

## Tech Stack

- **Python 3.11+**
- **FastAPI** - Modern async web framework
- **SQLAlchemy 2.0** - Async ORM
- **PostgreSQL** - Database
- **Pydantic v2** - Data validation and settings
- **Alembic** - Database migrations
- **Anthropic Claude** - LLM provider (configurable)

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Anthropic API key (for LLM features)

### Environment Setup

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and add your Anthropic API key:
```bash
ANTHROPIC_API_KEY=your_key_here
```

### Running with Docker (Recommended)

Start the API and PostgreSQL:
```bash
make up
```

The API will be available at [http://localhost:8000](http://localhost:8000)

View logs:
```bash
make logs
```

Stop containers:
```bash
make down
```

### Running Locally (Development)

1. Install dependencies:
```bash
make install
```

2. Start PostgreSQL (or use Docker for just the DB):
```bash
docker-compose up -d db
```

3. Run database migrations:
```bash
make db-upgrade
```

4. Seed example POIs:
```bash
make seed-pois
```

5. Start the API:
```bash
make dev
```

## Database Migrations

Create a new migration:
```bash
make db-migrate msg="description of changes"
```

Apply migrations:
```bash
make db-upgrade
```

Rollback last migration:
```bash
make db-downgrade
```

## API Documentation

Once running, visit:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### i18n Infrastructure Endpoints

Available under `/api/i18n`:
- `/runtime` - active locale resolution + budget/runtime settings
- `/budget/preview` - dry-run budget guard check
- `/budget/alerts` - app-side budget alert state by day/month usage ratio
- `/translations/upsert` - create/update persistent translation entry
- `/translations/entry` - fetch exact key+locale entry
- `/translations/resolve` - fetch with fallback chain resolution
- `/translations/runtime` - serve translation or fallback + enqueue async translation job (`screen` supported)
- `/translations/missing` - list keys missing in target locale
- `/translations/queue/stats` - async translation queue counters
- `/translations/queue/requeue` - force retry of latest blocked/failed job by key+locale
- `/translations/status` - status transition (`mt -> reviewed -> approved`)
- `/translations/review/pending` - list entries pending human review for tier+locale
- `/metrics` - i18n observability snapshot (fallback rates, top missing keys, queue reasons)
- `/rollout` - per-locale rollout matrix and enabled locales

### Async Translation Pipeline (Step 4)

- Background worker is started with API lifespan when:
  - `I18N_TRANSLATION_WORKER_ENABLED=true`
- Runtime endpoint behavior:
  - if translation exists in DB -> localized value is returned
  - if missing -> fallback text is returned immediately and translation is queued
- Translation provider modes:
  - `I18N_TRANSLATION_PROVIDER=echo` (default, zero-cost test mode)
  - `I18N_TRANSLATION_PROVIDER=google` (uses Google Cloud Translation API)

### Quality Workflow (Step 5)

- Tier A strings require manual review before serving localized content:
  - controlled by `I18N_TIER_A_REQUIRE_MANUAL_REVIEW=true`
- Glossary term overrides for brand vocabulary are applied to MT output:
  - controlled by `I18N_GLOSSARY_OVERRIDES_ENABLED=true`
- Reviewer flow:
  - fetch pending review list via `/api/i18n/translations/review/pending`
  - transition status via `/api/i18n/translations/status`

### Observability & Rollout (Step 6)

- Runtime observability:
  - fallback rate by locale
  - fallback hits by locale+screen
  - top missing keys
  - queue reason distribution
- Budget alerts:
  - `/api/i18n/budget/alerts`
  - thresholds: `I18N_BUDGET_ALERT_DAY_RATIO`, `I18N_BUDGET_ALERT_MONTH_RATIO`
- Per-locale rollout feature flags:
  - `I18N_ROLLOUT_ENFORCED`
  - `I18N_ROLLOUT_ENABLED_LOCALES`
  - inspect via `/api/i18n/rollout`

## Testing

Run unit and integration tests:
```bash
make test
```

Run i18n coverage and tier audit:
```bash
make i18n-audit
```

Run strict check for CI (fails if Tier A keys are missing/invalid):
```bash
make i18n-check-tier-a
```

Seed persistent translation storage from JSON files:
```bash
make i18n-seed-storage
```

### External Service Integration Checks

The project includes manual integration check scripts to verify connectivity with external services (io.net LLM, Google Places API, Google Routes API). These are **not** part of the normal pytest suite and are designed for manual verification.

Run all external service checks:
```bash
make check-externals
```

Or run individual checks:
```bash
make check-llm               # Check LLM / IO.NET connectivity
make check-google-places     # Check Google Places API
make check-google-routes     # Check Google Routes API
```

**What these checks do:**

- **`check-llm`**: Sends a minimal test request to the configured LLM provider (io.net or Anthropic) and verifies it responds correctly. Uses minimal tokens for cost efficiency.

- **`check-google-places`**: Searches for cafes/breakfast places in Paris using the Google Places API. Verifies that POIs are returned with coordinates and can be cached to the database.

- **`check-google-routes`**: Calculates a route between two well-known Paris landmarks (Eiffel Tower → Louvre) using the Google Routes API. Verifies travel time, distance, and polyline data are returned.

**Requirements:**
- These checks require valid API keys configured in your `.env` file
- The database must be running (for `check-google-places`)
- Each check uses minimal API calls to avoid unnecessary costs

## Project Structure

```
.
├── src/
│   ├── api/              # FastAPI routers
│   ├── application/      # Service layer
│   ├── domain/           # Domain models
│   ├── infrastructure/   # DB, LLM client, external APIs
│   ├── config.py         # Configuration
│   └── main.py           # FastAPI app entrypoint
├── alembic/              # Database migrations
├── scripts/              # Utility scripts
├── tests/                # Test suite
├── docker-compose.yml    # Docker setup
├── Dockerfile            # API container
└── requirements.txt      # Python dependencies
```

## Development Commands

See all available commands:
```bash
make help
```
