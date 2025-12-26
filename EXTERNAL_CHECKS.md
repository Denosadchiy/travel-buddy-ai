# External Service Integration Checks

This document describes the manual integration check scripts for verifying connectivity with external services.

## Overview

The integration check scripts are located in `scripts/` and are designed to:
- Verify external API connectivity (io.net LLM, Google Places, Google Routes)
- Use minimal API calls to avoid unnecessary costs
- Provide clear, human-readable output
- Return proper exit codes (0 = success, 1 = failure)

**Important:** These are **not** part of the pytest suite. They are manual verification tools.

## Usage

### Check All Services

```bash
make check-externals
```

This runs all three checks in sequence and reports overall success/failure.

### Individual Checks

```bash
make check-llm               # LLM / io.net connectivity
make check-google-places     # Google Places API
make check-google-routes     # Google Routes API
```

Or run directly:

```bash
python -m scripts.check_llm_ionet
python -m scripts.check_google_places
python -m scripts.check_google_routes
```

## Check Details

### 1. LLM / IO.NET Check (`check_llm_ionet.py`)

**What it does:**
- Uses the existing `get_trip_chat_llm_client()` factory
- Sends a minimal test request (max 32 tokens)
- Verifies response contains expected "PING_OK" string
- Respects configured `LLM_PROVIDER` (ionet or anthropic)

**Example output (SUCCESS):**

```
🔄 Testing LLM connectivity...
   Provider: ionet
   Model: Mistral-Nemo-Instruct-2407
   Base URL: https://api.intelligence.io.solutions/api/v1/
✅ LLM / IONET check: OK
   Response: PING_OK
```

**Example output (FAILURE - missing API key):**

```
❌ LLM / IO.NET check: FAILED
   Reason: IONET_API_KEY not configured
   Set the IONET_API_KEY environment variable
```

**Example output (FAILURE - connection error):**

```
🔄 Testing LLM connectivity...
   Provider: ionet
   Model: Mistral-Nemo-Instruct-2407
   Base URL: https://api.intelligence.io.solutions/api/v1/
❌ LLM / IONET check: FAILED
   Reason: HTTPError: 401 Unauthorized
```

---

### 2. Google Places Check (`check_google_places.py`)

**What it does:**
- Uses the existing `CompositePOIProvider` (DB + Google Places)
- Searches for cafes/breakfast in Paris
- Limits results to 5 to minimize API usage
- Verifies POIs have coordinates
- Shows which POIs came from Google vs DB cache

**Example output (SUCCESS):**

```
🔄 Testing Google Places API connectivity...
   Base URL: https://maps.googleapis.com/maps/api/place/textsearch/json
   Test city: Paris
   Categories: cafe, breakfast

✅ Google Places check: OK
   Found 5 candidates:

   1. Café de Flore
      Category: cafe
      Rating: 4.3
      Location: 172 Boulevard Saint-Germain, 75006 Paris
      Coordinates: 48.854, 2.3325
      Rank Score: 14.3

   2. Hollybelly 5
      Category: cafe
      Rating: 4.4
      Location: 5 Rue Lucien Sampaix, 75010 Paris
      Coordinates: 48.8715, 2.3611
      Rank Score: 14.4

   3. La Caféothèque
      Category: cafe
      Rating: 4.2
      Location: 52 Rue de l'Hôtel de Ville, 75004 Paris
      Coordinates: 48.8556, 2.3574
      Rank Score: 13.2

   4. Breakfast in America
      Category: cafe
      Rating: 4.1
      Location: 4 Rue Malher, 75004 Paris
      Coordinates: 48.8544, 2.3618
      Rank Score: 13.1

   5. Le Peloton Café
      Category: cafe
      Rating: 4.5
      Location: 17 Rue du Pont Louis-Philippe, 75004 Paris
      Coordinates: 48.8547, 2.3599
      Rank Score: 15.5
```

**Example output (FAILURE - missing API key):**

```
❌ Google Places check: FAILED
   Reason: GOOGLE_MAPS_API_KEY not configured
   Set the GOOGLE_MAPS_API_KEY environment variable
```

**Example output (FAILURE - no results):**

```
🔄 Testing Google Places API connectivity...
   Base URL: https://maps.googleapis.com/maps/api/place/textsearch/json
   Test city: Paris
   Categories: cafe, breakfast
❌ Google Places check: FAILED
   Reason: No POI candidates returned
   This could mean:
   - API key is invalid
   - API quota exceeded
   - Network connectivity issues
```

---

### 3. Google Routes Check (`check_google_routes.py`)

**What it does:**
- Uses `GoogleMapsTravelTimeProvider` directly
- Calculates route from Eiffel Tower to Louvre in Paris
- Verifies duration, distance, and polyline data
- Performs sanity check on distance (should be 2-8 km)

**Example output (SUCCESS):**

```
🔄 Testing Google Routes API connectivity...
   Base URL: https://routes.googleapis.com/directions/v2:computeRoutes
   Test route: Eiffel Tower → Louvre (Paris)
   Origin: Eiffel Tower (48.8584, 2.2945)
   Destination: Louvre (48.8606, 2.3376)

✅ Google Routes check: OK
   Duration: 12 minutes
   Distance: 4250 meters (4.25 km)
   Polyline: a~l~Fjk~uOwHJy@P...
```

**Example output (FAILURE - missing API key):**

```
❌ Google Routes check: FAILED
   Reason: GOOGLE_MAPS_API_KEY not configured
   Set the GOOGLE_MAPS_API_KEY environment variable
```

**Example output (FAILURE - API error):**

```
🔄 Testing Google Routes API connectivity...
   Base URL: https://routes.googleapis.com/directions/v2:computeRoutes
   Test route: Eiffel Tower → Louvre (Paris)
   Origin: Eiffel Tower (48.8584, 2.2945)
   Destination: Louvre (48.8606, 2.3376)
❌ Google Routes check: FAILED
   Reason: HTTPError: 403 Forbidden

   Stack trace:
   [detailed traceback...]
```

**Example output (WARNING - unusual distance):**

```
🔄 Testing Google Routes API connectivity...
   Base URL: https://routes.googleapis.com/directions/v2:computeRoutes
   Test route: Eiffel Tower → Louvre (Paris)
   Origin: Eiffel Tower (48.8584, 2.2945)
   Destination: Louvre (48.8606, 2.3376)

✅ Google Routes check: OK
   Duration: 18 minutes
   Distance: 9500 meters (9.50 km)
   Polyline: a~l~Fjk~uOwHJy@P...

⚠️  Warning: Distance seems unusual for this route
   Expected: 2000-8000m
   Got: 9500m
```

---

## Running All Checks Together

When you run `make check-externals`, all three checks run in sequence:

**Example output (ALL PASS):**

```
============================================
Checking External Service Integrations
============================================

🔄 Testing LLM connectivity...
   Provider: ionet
   Model: Mistral-Nemo-Instruct-2407
   Base URL: https://api.intelligence.io.solutions/api/v1/
✅ LLM / IONET check: OK
   Response: PING_OK

🔄 Testing Google Places API connectivity...
   Base URL: https://maps.googleapis.com/maps/api/place/textsearch/json
   Test city: Paris
   Categories: cafe, breakfast

✅ Google Places check: OK
   Found 5 candidates:

   1. Café de Flore
      [details...]

🔄 Testing Google Routes API connectivity...
   Base URL: https://routes.googleapis.com/directions/v2:computeRoutes
   Test route: Eiffel Tower → Louvre (Paris)
   Origin: Eiffel Tower (48.8584, 2.2945)
   Destination: Louvre (48.8606, 2.3376)

✅ Google Routes check: OK
   Duration: 12 minutes
   Distance: 4250 meters (4.25 km)
   Polyline: a~l~Fjk~uOwHJy@P...

============================================
✅ All external service checks passed!
============================================
```

**Example output (ONE FAILS):**

If any check fails, the command stops at that point with a non-zero exit code.

```
============================================
Checking External Service Integrations
============================================

🔄 Testing LLM connectivity...
   Provider: ionet
   Model: Mistral-Nemo-Instruct-2407
   Base URL: https://api.intelligence.io.solutions/api/v1/
✅ LLM / IONET check: OK
   Response: PING_OK

🔄 Testing Google Places API connectivity...
   Base URL: https://maps.googleapis.com/maps/api/place/textsearch/json
   Test city: Paris
   Categories: cafe, breakfast
❌ Google Places check: FAILED
   Reason: GOOGLE_MAPS_API_KEY not configured
   Set the GOOGLE_MAPS_API_KEY environment variable
make: *** [check-externals] Error 1
```

---

## Configuration Requirements

Before running these checks, ensure your `.env` file is properly configured:

### For LLM Checks

```bash
# Choose provider
LLM_PROVIDER=ionet  # or "anthropic"

# IO.NET configuration (if using ionet)
IONET_API_KEY=your_ionet_api_key_here
IONET_BASE_URL=https://api.intelligence.io.solutions/api/v1/
TRIP_CHAT_MODEL=Mistral-Nemo-Instruct-2407
TRIP_PLANNING_MODEL=meta-llama/Llama-3.3-70B-Instruct

# Anthropic configuration (if using anthropic)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### For Google Checks

```bash
# Google Maps Platform
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Google Places API
GOOGLE_PLACES_BASE_URL=https://maps.googleapis.com/maps/api/place/textsearch/json
GOOGLE_PLACES_TIMEOUT_SECONDS=10

# Google Routes API
GOOGLE_ROUTES_BASE_URL=https://routes.googleapis.com/directions/v2:computeRoutes
GOOGLE_ROUTES_TIMEOUT_SECONDS=10

# Travel Time Provider
TRAVEL_TIME_PROVIDER=google_maps
```

### For Google Places Check (Database Required)

The Google Places check needs a running database:

```bash
# Start the database
docker-compose up -d db

# Or use full stack
make up
```

---

## Cost Considerations

These checks are designed to minimize API costs:

- **LLM check**: ~32 tokens (< $0.01 per run)
- **Google Places check**: 1 API call for 5 results
- **Google Routes check**: 1 API call for a single route

All checks use hardcoded test data and don't require user input.

---

## Exit Codes

All scripts return:
- **0**: Success - service is working correctly
- **1**: Failure - configuration error, API error, or unexpected response

This makes them suitable for CI/CD pipelines or automated monitoring.

---

## Troubleshooting

### "Module not found" errors

Make sure you're running from the project root:

```bash
cd /path/to/Travel\ Buddy\ Ai
python -m scripts.check_llm_ionet
```

### Database connection errors (Google Places check)

Start the database first:

```bash
docker-compose up -d db
# Wait a few seconds for PostgreSQL to start
make check-google-places
```

### API quota errors

If you hit quota limits:
- Wait for quota to reset (usually hourly/daily)
- Check your API usage in respective dashboards
- Consider using cached responses for development

### Network/timeout errors

- Check your internet connection
- Verify firewall/proxy settings
- Try increasing timeout values in `.env`
