# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Travel Buddy AI** is an AI-powered trip planning system:
- **Backend:** FastAPI + PostgreSQL with LLM integration (io.net or Anthropic)
- **iOS App:** SwiftUI native client (iOS 16+)
- **Features:** Multi-day itineraries, POI selection, route optimization, freemium gating

Core flow: `User Input → Backend API → LLM Processing → POI Selection → Route Optimization → iOS Display`

## Essential Commands

### Backend

**Development:**
```bash
make install              # Install Python dependencies
make dev                  # Run API locally with hot reload (without Docker)
make up                   # Start Docker containers (API + PostgreSQL)
make down                 # Stop containers
make logs                 # View Docker logs (follow mode)
```

**Database:**
```bash
make db-migrate msg="..." # Generate new Alembic migration
make db-upgrade           # Apply database migrations
make db-downgrade         # Rollback last migration
make seed-pois            # Seed database with example POIs
docker compose down -v    # Fresh database (removes volumes)
```

**Testing:**
```bash
make test                              # Run all tests
pytest tests/test_foo.py -v            # Run specific file
pytest tests/test_foo.py::test_bar -v  # Run specific test
pytest -k "test_macro" -v              # Pattern match
pytest --tb=short                      # Shorter tracebacks
```

**External Service Checks:** (manual integration verification, not pytest)
```bash
make check-externals      # Check all external APIs (LLM, Google Places, Routes)
make check-llm            # Check LLM / IO.NET connectivity only
make check-google-places  # Check Google Places API only
make check-google-routes  # Check Google Routes API only
```

**Cleanup:**
```bash
make clean                # Remove __pycache__, *.pyc, .pytest_cache, *.egg-info
```

### iOS

```bash
open "ios/Travell Buddy.xcodeproj"  # Open in Xcode, then ⌘R to run
```

## Architecture

### Backend Layers (Clean Architecture)

```
src/
├── api/           # HTTP endpoints (FastAPI routers)
├── application/   # Business logic orchestration
├── domain/        # Core models (Pydantic schemas)
├── infrastructure/# External integrations (LLM, Google APIs, DB)
├── auth/          # JWT, providers, auth service
└── i18n/          # Localization middleware
```

**Trip Planning Pipeline** (`src/application/trip_planner.py`):
1. **MacroPlanner** - LLM generates day structure (time blocks, themes)
2. **POIPlanner** - Selects actual places from Google Places
3. **RouteOptimizer** - Orders POIs for efficient walking routes
4. **TripCritic** - Validates and reports issues

**Key Application Components:**
- `trip_planner.py` - Main orchestrator
- `route_optimizer.py` / `smart_route_optimizer.py` - Travel optimization
- `district_planner.py` - Geographic clustering by neighborhoods
- `day_editor.py` - AI Studio day editing (add/remove/replace POIs)
- `place_replacement_service.py` - POI replacement alternatives
- `poi_agent.py` - POI Curator agent (agentic planning)
- `trip_chat.py` - Natural language trip updates

### iOS Architecture (MVVM)

```
ios/Travell Buddy/
├── TripPlanning/      # Trip views and view models
├── Chat/              # Chat interface
├── Services/          # AuthManager, AuthGatingManager, SavedTripsManager
├── Networking/        # API clients and DTOs
├── Features/          # PlaceDetails, RouteBuilding, TripSummary
└── Views/             # Reusable UI components
```

**Key View Models:**
- `TripPlanViewModel` - Trip display, day selection, itinerary refresh
- `ChatViewModel` - Trip planning chat interface
- `AIStudioViewModel` - Day editing (add/remove/replace POIs, batched changes)
- `EditDayViewModel` - Legacy day editing (being replaced by AI Studio)

**Managers & Services:**
- `AuthManager.shared` - Authentication state, login/logout, token refresh
- `AuthGatingManager.shared` - Freemium gating logic (`isDayLocked`, `isMapLocked`)
- `SavedTripsManager.shared` - Saved trips persistence
- `ReplacePlaceManager` - Timeline POI replacement state machine

**API Clients:**
- `TripPlanningAPIClient` - Unauthenticated calls (trip creation, planning)
- `AuthenticatedAPIClient` - JWT-authenticated calls (user data, saved trips)

### Place Replacement System

Two distinct workflows for replacing POIs in itinerary:

**1. AI Studio In-Place Replacement** (via `AIStudioViewModel`):
- User opens AI Studio → taps "Заменить" button on place card
- `toggleReplacement(for:)` expands alternatives inline
- `loadReplacementAlternatives(for:)` fetches up to 3 alternatives
- `replacePlace(from:to:)` adds pending change
- Changes batched and applied via `applyAllChanges()` → Backend Day Editor API
- Auto-refresh itinerary on success via `onChangesApplied` callback

**2. Timeline Bottom Sheet Replacement** (via `ReplacePlaceManager`):
- User taps "..." on activity card → "Заменить место"
- `startReplace(for:dayIndex:stopIndex:)` triggers search (with duplicate protection)
- State machine: `.idle` → `.finding` → `.selecting`
- `ReplaceOptionsBottomSheet` shows alternatives
- `selectOption(_:onConfirm:)` replaces activity locally (optimistic update)
- Currently uses mock alternatives; backend integration pending

**Race Condition Protection:**
- Separate `onCancelReplace` callback (not `onTapReplace`)
- Duplicate call protection in `startReplace()`
- State checks prevent concurrent replace flows

## Important Workflows

### Trip Planning Flow

1. **User Input** → `ChatViewModel` processes user message
2. **Trip Creation** → `POST /api/trips` creates trip record
3. **Planning** → `POST /api/trips/{id}/plan` triggers pipeline:
   - MacroPlanner: LLM generates day structure (themes, time blocks)
   - POI Preferences: LLM extracts user preferences from chat
   - POIPlanner: For each day → POI selection (LLM ranking) + district assignment
   - RouteOptimizer: For each day → optimize travel order within districts
   - TripCritic: Validate itinerary, report issues
4. **Response** → iOS displays itinerary in `TripPlanView`

### AI Studio Day Editing Flow

1. User opens AI Studio for a day → `AIStudioView` + `AIStudioViewModel`
2. ViewModel loads day state: `loadDay()` → `syncLocalStateFromServer()`
3. User makes changes:
   - Add POI: Search → select result → `addPlace()`
   - Remove POI: Tap trash icon → `removePlace()`
   - Replace POI: Tap "Заменить" → expand alternatives → select → `replacePlace()`
4. Changes tracked in `pendingChanges` array (not applied immediately)
5. User taps "Применить изменения" → `applyAllChanges()`:
   - Processes each `PendingChange` sequentially
   - Calls Day Editor backend API for each change
   - Backend updates itinerary with `flag_modified()` for SQLAlchemy tracking
6. Success → `onChangesApplied` callback → `TripPlanViewModel.refreshItinerary()`
7. Auto-dismiss AI Studio after 0.5s → User sees updated itinerary

**Critical Backend Pattern:**
```python
# day_editor.py - Ensure SQLAlchemy detects JSONB changes
from sqlalchemy.orm.attributes import flag_modified

days_data[day_index] = updated_day.model_dump(mode='json')
flag_modified(itinerary_model, 'days')  # ← Required for JSONB updates
await db.commit()
db.expire_all()  # ← Force fresh query
```

### Freemium Gating Flow

1. `AuthGatingManager.shared` checks auth state + trip metadata
2. For guests (`AuthManager.shared.isLoggedIn == false`):
   - `isDayLocked(dayIndex)` → locks Day 2+ (shows lock icon)
   - `isMapLocked(tripId)` → locks route map (shows auth prompt)
3. User attempts locked action → `PendingIntent` saved → Auth sheet shown
4. After auth → `processPendingIntent()` executes saved action

## Configuration

Copy `.env.example` to `.env` and configure:

### Required API Keys
```bash
# LLM Provider (choose one)
LLM_PROVIDER=ionet                    # "ionet" or "anthropic"
IONET_API_KEY=...                     # io.net API key
# ANTHROPIC_API_KEY=...               # Alternative: Anthropic Claude

# Google Maps (required for POI search and routing)
GOOGLE_MAPS_API_KEY=...
```

### LLM Model Configuration

**io.net models** (requires full vendor prefix):
```bash
TRIP_CHAT_MODEL=mistralai/Mistral-Nemo-Instruct-2407      # Chat interface
TRIP_PLANNING_MODEL=meta-llama/Llama-3.3-70B-Instruct    # Planning/routing
```

**Anthropic models** (alternative):
```bash
TRIP_CHAT_MODEL=claude-3-5-haiku-20241022
TRIP_PLANNING_MODEL=claude-3-5-sonnet-20241022
```

### LLM Integration Flags (All Enabled by Default)

**IMPORTANT:** All LLM integrations are **mandatory by default** for maximum quality:

```bash
USE_LLM_FOR_POI_SELECTION=true              # LLM selects/ranks POIs (vs deterministic)
USE_LLM_FOR_DISTRICT_PLANNING=true          # LLM assigns POIs to districts
ENABLE_AGENTIC_PLANNING=true                # Full POI Curator + Route Engineer pipeline
```

**LLM modules in pipeline:**
1. **Macro Planning** - Day structure generation
2. **POI Preferences** - User profile extraction
3. **POI Selection** - Intelligent POI ranking (per day)
4. **District Planning** - Geographic clustering (per day)
5. **Route Optimization** - Travel order optimization (per day)

**Cost:** ~11 LLM calls per 3-day trip (~$0.02-0.04 with io.net)
**Safety:** All modules have timeout protection and deterministic fallbacks

### Routing & Optimization

```bash
ENABLE_SMART_ROUTING=true               # District-based geographic clustering
TRAVEL_TIME_PROVIDER=google_maps        # "google_maps" or "simple" (heuristic)
ENABLE_DAILY_ROUTE_OPTIMIZATION=true    # Reorder blocks to minimize travel
ENABLE_TRAVEL_HOP_LIMIT=true            # Limit max travel between POIs
MAX_TRAVEL_MINUTES_PER_HOP=40          # Maximum travel time per hop

# District Clustering Parameters
CLUSTER_CELL_SIZE_KM=1.5               # Grid cell size for clustering
MAX_POI_RADIUS_KM=15.0                 # Max distance from city center
MIN_POIS_PER_DISTRICT=5                # Minimum POIs to form district
MAX_DISTRICTS_PER_CITY=8               # Maximum districts per city
SMART_ROUTING_MIN_RATING=4.5           # Minimum POI rating filter
```

### Authentication & Freemium

```bash
FREEMIUM_ENABLED=false                 # true in production
GUEST_MAX_TRIPS=1                      # Max trips before auth required

JWT_SECRET_KEY=CHANGE_IN_PRODUCTION
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
```

**Freemium Restrictions (when enabled):**
- Guests: See only Day 1, limited to 1 trip
- Authenticated: Full access to all days, unlimited trips

### Database

```bash
DATABASE_URL=postgresql+asyncpg://tripplanner:tripplanner@localhost:5433/tripplanner
```

Database runs on port **5433** (mapped from container's 5432).

## API Documentation

When running: http://localhost:8000/docs (Swagger) or http://localhost:8000/redoc

Key endpoints:
- `POST /api/trips` - Create trip
- `POST /api/trips/{id}/plan` - Generate itinerary
- `GET /api/trips/{id}/itinerary` - Get full itinerary
- `POST /api/trips/{id}/chat` - Natural language planning
- `POST /api/day-studio/{trip_id}/days/{day_index}/...` - AI Studio editing

## Testing

pytest-asyncio is configured in **auto mode** - async tests are detected automatically.

**External service checks** (`make check-externals`) are **not** part of the pytest suite. They manually verify connectivity with io.net/Anthropic, Google Places, and Google Routes APIs for cost control.

See "Essential Commands → Testing" section for common test commands.

## Common Pitfalls & Debugging

### Backend

**JSONB field updates not persisting:**
```python
# ❌ Wrong - SQLAlchemy doesn't detect JSONB mutations
itinerary.days[0]['activities'].append(new_activity)
await db.commit()

# ✅ Correct - Use flag_modified()
from sqlalchemy.orm.attributes import flag_modified
itinerary.days[0]['activities'].append(new_activity)
flag_modified(itinerary, 'days')
await db.commit()
```

**Stale data after update:**
```python
# After modifying itinerary, force fresh query
db.expire_all()
```

**LLM calls timing out:**
- Check `*_llm_timeout_seconds` settings in config
- All LLM modules have automatic fallback to deterministic mode
- Monitor logs for "timed out, using deterministic" warnings

**io.net model names:**
- MUST include vendor prefix: `meta-llama/Llama-3.3-70B-Instruct` (not just `Llama-3.3-70B-Instruct`)
- Check `.env.example` for correct model names

### iOS

**Itinerary not refreshing after AI Studio changes:**
- Ensure `onChangesApplied` callback is set in `TripPlanView`
- Check `shouldDismiss` flag is triggered after backend success
- Verify backend returns 200 OK (not just 201/204)

**Place replacement race conditions:**
- Use `onCancelReplace` for cancel button (NOT `onTapReplace`)
- `ReplacePlaceManager.startReplace()` has duplicate protection
- Check state machine: `.idle` → `.finding` → `.selecting` → `.idle`

**Freemium locks not working:**
- Verify `FREEMIUM_ENABLED=true` in backend `.env`
- Check `AuthGatingManager.shared` state updates on login/logout
- Trip metadata must include `is_guest` flag

**API client confusion:**
- Unauthenticated endpoints (trips, planning): Use `TripPlanningAPIClient`
- Authenticated endpoints (saved trips, user data): Use `AuthenticatedAPIClient` with JWT

## Key Files Reference

**Backend:**
- `src/application/trip_planner.py` - Main planning orchestrator (MacroPlanner → POIPlanner → RouteOptimizer)
- `src/application/route_optimizer.py` - Route optimization with district planning
- `src/application/district_planner.py` - Geographic clustering (LLM or deterministic)
- `src/application/day_editor.py` - AI Studio backend (add/remove/replace POIs)
- `src/application/place_replacement_service.py` - POI replacement alternatives
- `src/application/poi_agent.py` - POI Curator agent (agentic planning)
- `src/api/trips.py` - Trip CRUD endpoints
- `src/api/day_studio.py` - AI Studio API endpoints
- `src/infrastructure/llm_client.py` - LLM provider abstraction (io.net / Anthropic)
- `src/config.py` - All configuration settings (140+ env vars)

**iOS:**
- `TripPlanning/TripPlanView.swift` - Main trip view with timeline
- `TripPlanning/TripPlanViewModel.swift` - Trip state, day selection, refresh logic
- `AIStudio/AIStudioView.swift` - Day editing interface
- `AIStudio/AIStudioViewModel.swift` - Batched changes, place replacement, search
- `Services/AuthManager.swift` - Authentication state, Google Sign-In
- `Services/AuthGatingManager.swift` - Freemium logic (day/map locking)
- `Services/ReplacePlaceManager.swift` - Place replacement state machine
- `Networking/TripPlanningAPIClient.swift` - API client (unauthenticated)
- `Networking/AuthenticatedAPIClient.swift` - API client (JWT)
- `Config/AppConfig.swift` - Base URL and app config
