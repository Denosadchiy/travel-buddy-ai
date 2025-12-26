# CLAUDE.md

Never hallucinate or fabricate information. If you're unsure about anything, you MUST explicitly state your uncertainty. Say "I don't know" rather than guessing or making assumptions. Honesty about limitations is required.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Trip Planning backend** for a travel app. It handles everything from user inputs and chat context to generating structured, optimized itineraries stored in a database.

The backend does NOT include:
- Live Guide module (separate repo)
- TTS/audio streaming
- Server-Driven UI composition
- Frontend/mobile app code

## Architecture

Three logical layers:

### 1. Backend Core
- HTTP API endpoints for mobile app
- Database connection management (Trip and POI data)
- Configuration via environment variables (DB URL, LLM endpoint, API keys)

### 2. Trip Planning Service
Components in order of data flow:
- **TripSpec Collector**: Accepts structured form inputs (city, dates, travelers, pace, budget, interests, routine, hotel location)
- **Trip Chat Assistant**: Interprets natural language via LLM, updates TripSpec
- **Trip Planner Orchestrator**: Runs the full planning pipeline
- **Macro Planner**: LLM-based high-level skeleton (days → themes → time blocks)
- **POI Planner**: Selects candidate places from POI DB per skeleton block
- **Route and Time Optimizer**: Final ordering, travel time, opening hours compliance
- **Trip Critic**: Rule-based validation (missing meals, closed POIs, long days)

### 3. LLM Layer
- Provider-agnostic LLM client (Anthropic/OpenAI)
- Two modes:
  - **Trip Chat Mode**: User message → text reply + TripSpec update (JSON)
  - **Macro Planning Mode**: TripSpec → DaySkeleton list (JSON)

## Key Domain Models

Use typed schemas (e.g., Pydantic):
- `TripSpec` - consolidated trip configuration
- `DailyRoutine` - wake/sleep times, meal windows
- `DaySkeleton` / `SkeletonBlock` - high-level day structure
- `POICandidate` - place candidates with ranking
- `ItineraryDay` / `ItineraryBlock` - final detailed schedule
- `CritiqueIssue` - validation problems per day/block

## API Endpoints (Expected)

- Create/update TripSpec (form inputs)
- Submit chat messages for a trip
- Trigger planning for a trip
- Fetch stored itinerary with critique

## Code Organization Principles

- **Layers**: HTTP → Application/Services → Domain → Infrastructure
- **Data flow**: TripSpec → Skeleton → Candidates → Itinerary → Critique
- External APIs (Maps, Places) should be abstracted and mockable
- LLM client should be mockable for tests
