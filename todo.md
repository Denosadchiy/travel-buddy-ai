# todo.md – Master prompt for Trip Planning backend (for Claude Code)

You are an AI coding assistant (Claude Code) helping to design and implement the Trip Planning backend of a travel app.

This document is your master prompt. Use it as the primary specification to:
- understand the product context,
- choose a reasonable architecture and code organization,
- scaffold the project,
- implement the first working version of the backend.


## 1. Product context

The full product has 2 major features:

1. Trip planning
   - User configures a trip via a UI form (dates, city, budget, pace, interests, etc.).
   - In the same screen, there is an embedded AI chat where the user can comment, clarify, or add constraints in natural language.
   - The system combines:
     - structured form data,
     - unstructured chat context,
     into a single TripSpec (normalized trip description).
   - Based on TripSpec, the backend generates a day-by-day itinerary:
     - which places to visit each day,
     - in what order,
     - at what times,
     - with a logical structure, timing and breaks (meals, rest).

2. Live AI Guide  
   - This is a separate module (not part of this repo) that uses location and the itinerary to talk to the user in real time.

This repository focuses only on feature 1 – Trip Planning: everything required on the backend to go from “user inputs + chat context” → “structured, optimized itinerary stored in a database”.


## 2. Scope of this backend

This project should include three logical layers:

1. Backend Core
   - HTTP API for the app (via an API gateway layer).
   - Request routing for trip planning operations.
   - Integration with database (Trip and POI data).
   - Configuration, logging, error handling.

2. Trip Planning Service
   - All domain logic related to planning a trip:
     - Collecting TripSpec from UI and chat.
     - Running a planning pipeline that builds an itinerary.
     - Validating and storing the result.

3. LLM Layer (Trip Chat and Planning)
   - Unified client to call a large language model (LLM).
   - Different prompts/modes for:
     - Trip Chat Assistant (to interpret user messages and update TripSpec).
     - Macro planning (to build a “skeleton” of the trip by days).
   - The LLM Layer should be pluggable (provider-agnostic, API keys via environment variables).
/   

## 3. High-level responsibilities

### 3.1 Backend Core

Design and implement:

- An HTTP API with endpoints for:
  - receiving form-based trip parameters from the app,
  - receiving chat messages related to a trip,
  - triggering itinerary planning for a specific trip,
  - fetching the stored itinerary for display.

- Core concerns:
  - Database connection management.
  - Configuration via environment variables (DB URL, LLM endpoint, etc.).
  - Clear separation of concerns:
    - HTTP layer (request/response),
    - Application/service layer (orchestrators),
    - Domain logic (planning, models),
    - Infrastructure (DB, LLM client, external APIs).

- No UI or frontend in this repo. The API is used by a mobile app.


### 3.2 Trip Planning Service

This is the domain brain for planning trips. Implement the following logical components as well-defined modules/classes with clear inputs/outputs:

1. TripSpec Collector (form inputs)
   - Accepts structured parameters from the UI form:
     - city, dates, number of travelers,
     - pace (slow / medium / fast),
     - budget (low / medium / high),
     - interests (e.g. food, nightlife, culture),
     - daily routine (wake/sleep, meal windows),
     - hotel location (if available).
   - Writes/updates these fields in the Trip DB.
   - TripSpec should be a well-defined domain object (a typed schema) representing the consolidated state of the trip.2. Trip Chat Assistant
   - Handles natural language messages from the embedded chat on the planning screen.
   - Uses the LLM for Trip Chat and Planning to:
     - interpret what the user wants/clarifies (e.g. “We hate museums”, “Add techno parties at night”),
     - update the TripSpec accordingly in Trip DB.
   - Should not directly build the full itinerary – its job is to shape TripSpec and give helpful textual feedback.

3. Trip Planner Orchestrator
   - Central orchestrator that, for a given trip, runs the planning pipeline:
     - loads TripSpec from DB,
     - calls Macro Planner,
     - calls POI Planner,
     - calls Route and Time Optimizer,
     - calls Trip Critic,
     - saves resulting itinerary and critique back to Trip DB.
   - This orchestrator should be callable from the API layer (e.g. /trips/{id}/plan or equivalent).

4. Macro Planner
   - Builds a high-level skeleton of the trip:
     - splits trip into days,
     - assigns themes per day (e.g. “historic center”, “parks and views”, “nightlife”),
     - defines blocks (time windows) per day: meals, activities, nightlife.
   - Uses the LLM (via the LLM Layer) to produce a structured JSON skeleton that matches predefined schemas.
   - Does not choose specific places yet.

5. POI Planner
   - For each skeleton block that needs a place:
     - selects candidate POIs (places of interest) from the POI DB,
     - optionally enriches with external Places API (can be stubbed for now),
     - ranks them based on category, tags, rating, preferences.
   - Returns candidate lists per block, not final ordering.

6. Route and Time Optimizer
   - Converts skeleton + POI candidates into a detailed itinerary:
     - chooses one POI per block,
     - orders blocks within the day to minimize travel,
     - uses Maps Routing API (or an abstraction) to estimate travel time,
     - respects:
       - opening hours of places,
       - meal windows,
       - daily routine constraints (wake/sleep).
   - Writes final itinerary to Trip DB:
     - days,
     - ordered blocks,
     - POIs and start/end times.

7. Trip Critic
   - Performs rule-based validation of the itinerary:
     - checks for days without meals,
     - checks closed POIs at assigned times,
     - checks overly long days or long walks.
   - Records issues in a structured way (per day/block) linked to the trip.
   - Does not automatically fix the plan (MVP) but returns critique for later UI or conversational handling.


### 3.3 LLM Layer (Trip Chat and Planning)

Design a reusable LLM client and prompt patterns:

- LLM Client
  - A small abstraction that:
    - wraps calls to an external LLM API (e.g. Anthropic / OpenAI),
    - reads base URL and API key from environment variables,
    - supports:
      - plain text outputs,
      - JSON-structured outputs (for skeletons and TripSpec updates).
  - Should be easy to mock in tests.

- Trip Chat Mode
  - Prompt style for interpreting user messages and producing:
    - a short text reply to user,
    - a structured update to TripSpec (e.g. preferences, constraints).
  - The backend code should parse and apply these updates to Trip DB.

- Macro Planning Mode
  - Prompt style for generating DaySkeleton structures:
    - list of days,
    - per day — blocks (meals, activities, nightlife) with time windows and desired categories.
  - Must produce valid JSON that can be parsed into typed models.


## 4. Non-goals and boundaries

For this project:

- Do not implement:
  - Live Guide logic,
  - TTS, audio streaming,
  - Server-Driven UI composition layer (Narrator/UI Composer),
  - cross-feature conversation orchestration for the whole product.

- Minimal conversation:
  - It is acceptable if Trip Chat Assistant focuses mainly on:
    - understanding trip-related messages,
    - suggesting clarifications,
    - updating TripSpec.
  - You do not need to implement a generic multi-topic chat.- Assume:
  - The mobile app handles UI rendering.
  - A broader “Conversation Orchestrator” may be added later. For now, the API can be rather direct:
    - endpoint(s) for form updates → TripSpec Collector,
    - endpoint(s) for chat messages → Trip Chat Assistant,
    - endpoint(s) for planning → Trip Planner Orchestrator.


## 5. Architectural and code style guidelines

When creating the project:

- Use clean separation of layers:
  - HTTP/API layer (framework-specific).
  - Application/services layer (orchestrators, agents).
  - Domain layer (TripSpec, Itinerary, skeletons, POI candidates, critique).
  - Infrastructure layer (DB, LLM client, external APIs abstraction).

- Make domain models explicit and typed (e.g. Pydantic or similar):
  - TripSpec, DailyRoutine, DaySkeleton, SkeletonBlock, POICandidate, ItineraryDay, ItineraryBlock, CritiqueIssue, etc.

- Focus on:
  - readability,
  - testability (mock LLM and external APIs),
  - small, composable functions and classes.

- Prefer:
  - clear, documented methods over “magic” metaprogramming,
  - explicit data flow between components (TripSpec → Skeleton → Candidates → Itinerary → Critique).

- It is acceptable to:
  - start with simple heuristics in Route and Time Optimizer,
  - use stubbed/mocked versions of Maps/Places APIs in early versions.


## 6. Implementation priorities for initial version

When you start generating code, prioritize the following:

1. LLM client abstraction (Trip Chat + Macro Planning modes).
2. Domain schemas for TripSpec, skeleton, candidates, itinerary, critique.
3. TripSpec Collector (form inputs):
   - ability to create/update TripSpec in DB.
4. Trip Chat Assistant:
   - endpoint(s) to accept chat messages and update TripSpec via LLM.
5. Trip Planner Orchestrator + Macro Planner (LLM-based):
   - basic pipeline from TripSpec → DaySkeleton list.
6. POI Planner (simple DB-based selection):
   - even if POI DB is small or partially stubbed.
7. Route and Time Optimizer (simple heuristic):
   - simple time assignment and ordering logic.
8. Trip Critic (rule-based checks).
9. Minimal HTTP API endpoints:
   - create/update TripSpec,
   - submit chat messages for a trip,
   - trigger planning for a trip,
   - fetch stored itinerary with critique.