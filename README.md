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

## Testing

Run unit and integration tests:
```bash
make test
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
