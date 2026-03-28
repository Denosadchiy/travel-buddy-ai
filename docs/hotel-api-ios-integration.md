# Hotel Picker — Backend API: iOS Integration Guide

**Version:** Stage 4 · **Date:** 2026-03-22
**Audience:** iOS developer integrating Hotel Picker screens

This document is the **single source of truth** for integrating the Hotel Picker backend into the iOS app. After reading it you will have everything needed to build all hotel screens without consulting backend code.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Base URL & Authentication](#2-base-url--authentication)
3. [Endpoints](#3-endpoints)
   - [GET /health](#31-get-apihotelshealth)
   - [POST /search](#32-post-apihotelssearch)
   - [POST /search/stream (SSE)](#33-post-apihotelssearchstream)
   - [POST /search/more](#34-post-apihotelssearchmore)
   - [POST /find](#35-post-apihotelsfind)
   - [POST /explain](#36-post-apihotelsexplain)
4. [Data Models](#4-data-models)
5. [Booking URL Deep Links](#5-booking-url-deep-links)
6. [SSE Streaming — iOS Guide](#6-sse-streaming--ios-guide)
7. [Pagination Flow](#7-pagination-flow)
8. [UI Recommendations](#8-ui-recommendations)

---

## 1. Product Overview

Hotel Picker is an AI-driven hotel recommendation engine. The user provides a city, dates, and optional free-text preferences ("quiet boutique hotel in the centre"); the backend runs a 7-phase AI pipeline and returns the top-10 most fitting hotels with personalised AI insights.

Key things iOS needs to know:

- **Full search takes 30–62 seconds.** Use the SSE streaming endpoint to show a progress bar instead of a blank screen.
- **Results arrive as a batch** (not incrementally) at the end of the pipeline.
- **Pagination is session-based**: a `session_id` from the first search unlocks the next page of 10 hotels without repeating the slow AI phases.
- **Every hotel has a ready-to-use `booking_url`** — a Booking.com deep link pre-filled with dates, guest counts, and currency. Tap → Safari → book.
- **Photos come from Booking.com CDN** (cf.bstatic.com). Up to 5 per hotel, ready to show in a horizontal scroll.

---

## 2. Base URL & Authentication

### Base URL

| Environment | URL |
|-------------|-----|
| Local dev | `http://localhost:8000` |
| Production | TBD — replace in `AppConfig.swift` |

All hotel endpoints are under `/api/hotels`.

### Authentication

**Currently: no authentication required** on hotel endpoints. All calls are open.

Future: the same JWT bearer token used for trip planning will be added. Prepare `AuthenticatedAPIClient` calls; the header will be:

```
Authorization: Bearer <access_token>
```

### Common headers

```
Content-Type: application/json
Accept: application/json
```

For SSE streaming only:
```
Accept: text/event-stream
```

---

## 3. Endpoints

### 3.1 GET /api/hotels/health

Liveness check. Use to verify the hotels module is running before showing the search UI.

**Method:** `GET`
**URL:** `/api/hotels/health`
**Request body:** none

**Response `200 OK`:**
```json
{
  "status": "ok",
  "module": "hotels"
}
```

**curl:**
```bash
curl http://localhost:8000/api/hotels/health
```

---

### 3.2 POST /api/hotels/search

Full AI hotel search pipeline. Returns top-10 hotels + metadata.

**Method:** `POST`
**URL:** `/api/hotels/search`
**Response time:** 30–62 seconds

#### Request body

All fields except `city`, `check_in`, `check_out` are optional.

```jsonc
{
  // Required
  "city": "Paris",               // string — city name in English or Russian
  "check_in": "2026-07-01",     // string — YYYY-MM-DD
  "check_out": "2026-07-05",    // string — YYYY-MM-DD

  // Guests
  "adults": 2,                  // integer, 1–30, default: 2
  "children_ages": [5, 8],      // array of integers (ages), default: []

  // Budget
  "budget_min": null,            // float | null — min price per night in currency
  "budget_max": 250.0,          // float | null — max price per night in currency

  // Currency
  "currency": "EUR",            // string, ISO 4217, default: "EUR"

  // Optional filters
  "stars_min": 4,               // integer 1–5 | null — minimum star rating
  "user_wishes": "Quiet boutique hotel in the centre, not a chain",
                                // string | null — free text for AI intent parsing
  "amenities": [                // array of Booking.com filter strings
    "facility::107",            // Free WiFi
    "facility::433"             // Pool
  ],
  "property_types": [           // array of property type filter strings
    "property_type::204"        // Hotels only
  ],
  "meal_plan": null,            // string | null — e.g. "breakfast_included"
  "free_cancellation": false,   // boolean, default: false
  "adults_only": false,         // boolean, default: false
  "pets_allowed": false         // boolean, default: false
}
```

**Amenity filter reference** (pass in `amenities` array):

| Code | Meaning |
|------|---------|
| `facility::107` | Free WiFi |
| `facility::433` | Swimming pool |
| `facility::54` | Spa & wellness |
| `facility::11` | Fitness centre |
| `facility::3` | Restaurant |
| `facility::28` | Family rooms |
| `facility::4` | Pets allowed |
| `facility::2` | Parking |
| `facility::46` | Free parking |
| `facility::17` | Airport shuttle |
| `facility::8` | 24-hour front desk |
| `room_facility::11` | Air conditioning |
| `room_facility::23` | Desk (remote work) |
| `room_facility::79` | Soundproofing |
| `room_facility::81` | Room with a view |

**Property type filter reference:**

| Code | Meaning |
|------|---------|
| `property_type::204` | Hotels |
| `property_type::201` | Apartments |
| `property_type::208` | Bed & Breakfast |
| `property_type::213` | Villas |
| `property_type::203` | Hostels |

#### Response `200 OK`

Returns a `HotelSearchResponse` (see [Data Models](#4-data-models)).

```json
{
  "hotels": [ /* array of HotelResult — up to 10 */ ],
  "notable_excluded": [ /* array of ExcludedHotel — 3–5 near-miss hotels */ ],
  "city": "Paris",
  "check_in": "2026-07-01",
  "check_out": "2026-07-05",
  "total_found": 847,
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "applied_filters_summary": "Budget ≤250/night · Score ≥7 · 2 amenity filters · Paris (847 hotels available)",
  "has_more": true
}
```

#### Error responses

| HTTP code | When | Body |
|-----------|------|------|
| 404 | City not found on Booking.com | `{"detail": "No destination found for 'XyzUnknown'"}` |
| 422 | Invalid request (bad date, adults < 1) | `{"detail": [{"loc":["body","adults"],"msg":"...","type":"..."}]}` |
| 429 | Booking.com API rate limit | `{"detail": "Booking API rate limit exceeded. Please retry in a moment."}` |
| 502 | Booking.com API error | `{"detail": "Booking API error: ..."}` |
| 504 | Pipeline timeout (>62s) | `{"detail": "Search timed out. Please try again."}` |
| 500 | Unexpected server error | `{"detail": "Internal server error"}` |

**curl example:**
```bash
curl -X POST http://localhost:8000/api/hotels/search \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Paris",
    "check_in": "2026-07-01",
    "check_out": "2026-07-05",
    "adults": 2,
    "children_ages": [5, 8],
    "budget_max": 250.0,
    "currency": "EUR",
    "user_wishes": "Romantic boutique hotel in the centre"
  }'
```

**Realistic response example:**
```json
{
  "hotels": [
    {
      "hotel_id": 1769895,
      "name": "Le Bristol Paris",
      "accommodation_type": "Hotel",
      "stars": 5,
      "is_boutique": false,
      "url": "https://www.booking.com/hotel/fr/le-bristol-paris.html",
      "booking_url": "https://www.booking.com/hotel/fr/le-bristol-paris.html?checkin=2026-07-01&checkout=2026-07-05&group_adults=2&group_children=2&selected_currency=EUR&age=5&age=8",
      "review_score": 9.4,
      "review_score_word": "Exceptional",
      "review_count": 2847,
      "category_scores": {
        "cleanliness": 9.8,
        "comfort": 9.7,
        "location": 9.5,
        "staff": 9.9,
        "value": 8.6,
        "wifi": 9.2
      },
      "segment_scores": {
        "couple": 9.6,
        "family": 9.1,
        "business": 9.3
      },
      "price_per_night": 890.0,
      "total_price": 3560.0,
      "currency": "EUR",
      "strikethrough_price": null,
      "address": "112 Rue du Faubourg Saint-Honoré, 8th arr., Paris",
      "district": "8th arrondissement",
      "distance_to_center_km": 0.9,
      "latitude": 48.8738,
      "longitude": 2.3151,
      "photos": [
        "https://cf.bstatic.com/xdata/images/hotel/max750/123456.jpg?k=...",
        "https://cf.bstatic.com/xdata/images/hotel/max750/123457.jpg?k=..."
      ],
      "key_facilities": ["Free WiFi", "Spa & Wellness", "Restaurant", "Fitness Centre", "Room Service"],
      "breakfast_included": true,
      "pets_allowed": false,
      "free_cancellation": false,
      "checkin_from": "15:00",
      "checkout_until": "12:00",
      "ai_score": 9.2,
      "ai_match_reason": "Iconic Parisian palace with intimate boutique atmosphere, steps from the Champs-Élysées — ideal for a romantic stay.",
      "ai_pros": ["Legendary Epicure restaurant with 3 Michelin stars", "Rooftop garden with panoramic views", "Award-winning couples spa"],
      "ai_cons": ["Premium pricing", "Valet parking only"],
      "ai_hidden_issues": [],
      "review_summary": "Couples consistently praise the personalised service and the magical atmosphere of the courtyard.",
      "interior_style": "classic",
      "view_quality": "city",
      "visual_cleanliness": "excellent"
    }
  ],
  "notable_excluded": [
    {
      "hotel_id": 28827,
      "name": "Hôtel de Crillon",
      "stars": 5,
      "review_score": 9.2,
      "price_per_night": 1100.0,
      "ai_score": 7.8,
      "reason": "Price ≥€1,100/night exceeds budget — otherwise an exceptional match"
    }
  ],
  "city": "Paris",
  "check_in": "2026-07-01",
  "check_out": "2026-07-05",
  "total_found": 847,
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "applied_filters_summary": "Budget ≤250/night · Score ≥7 · Paris (847 hotels available)",
  "has_more": true
}
```

---

### 3.3 POST /api/hotels/search/stream

**Same search as `/search` but with real-time progress via Server-Sent Events (SSE).**

Use this endpoint to show a progress bar during the 30–62 second wait. The final result is delivered as the last non-`done` event.

**Method:** `POST`
**URL:** `/api/hotels/search/stream`
**Request body:** Identical to `/search` (same `HotelSearchRequest`)
**Response:** `text/event-stream`

#### Event sequence

```
event: progress
data: {"phase": 1, "message": "Analyzing your preferences…", "progress": 0.05}

event: progress
data: {"phase": 2, "message": "Searching hotels in Paris…", "progress": 0.15}

event: progress
data: {"phase": 3, "message": "Collecting hotel details…", "progress": 0.35}

event: progress
data: {"phase": 4, "message": "Analyzing guest reviews…", "progress": 0.55}

event: progress
data: {"phase": 5, "message": "Finding your best matches…", "progress": 0.75}

# Phase 6 only emitted if time allows (photo vision)
event: progress
data: {"phase": 6, "message": "Analyzing hotel photos…", "progress": 0.90}

# Success path:
event: result
data: {<complete HotelSearchResponse JSON — same as /search response>}

event: done
data: {}

# Error path (instead of result):
event: error
data: {"message": "No destination found for 'Xyz'", "status": 404}

event: done
data: {}
```

#### Progress event fields

| Field | Type | Description |
|-------|------|-------------|
| `phase` | `Int` | Pipeline phase (1–6) |
| `message` | `String` | Human-readable status. In **Russian** if `user_wishes` contains Cyrillic; otherwise **English** |
| `progress` | `Float` | 0.0–1.0 — use directly as `ProgressView(value:)` |

**For the iOS implementation guide see [Section 6](#6-sse-streaming--ios-guide).**

#### curl example (observe stream):
```bash
curl -X POST http://localhost:8000/api/hotels/search/stream \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "city": "Rome",
    "check_in": "2026-08-01",
    "check_out": "2026-08-04",
    "adults": 2,
    "budget_max": 200.0,
    "currency": "EUR"
  }'
```

---

### 3.4 POST /api/hotels/search/more

Returns the next batch of 10 hotels from a previous search. Requires `session_id` obtained from a prior `/search` or `/search/stream` response.

**Method:** `POST`
**URL:** `/api/hotels/search/more`
**Response time:** 30–50 seconds (runs phases 3–5 on new candidates)

#### Request body

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | `String` | Yes | From prior `/search` response |

#### Response `200 OK`

Same `HotelSearchResponse` structure. When `has_more: false` and `hotels` is empty, all candidates are exhausted.

```json
{
  "hotels": [ /* next 10 HotelResult objects */ ],
  "notable_excluded": [],
  "city": "",
  "check_in": "2026-07-01",
  "check_out": "2026-07-05",
  "total_found": 847,
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "applied_filters_summary": "",
  "has_more": true
}
```

#### Error responses

| HTTP code | When | Body |
|-----------|------|------|
| 404 | Session not found or expired (TTL: 30 min) | `{"detail": "Session 'abc' not found or expired"}` |

**curl example:**
```bash
curl -X POST http://localhost:8000/api/hotels/search/more \
  -H "Content-Type: application/json" \
  -d '{"session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}'
```

---

### 3.5 POST /api/hotels/find

Find a specific hotel by name with full AI analysis. Use this for a hotel detail screen when the user taps a hotel from a saved search or a deep link.

**Method:** `POST`
**URL:** `/api/hotels/find`
**Response time:** 15–30 seconds

#### Request body

```jsonc
{
  "hotel_name": "Le Bristol Paris",  // string — required, hotel name to search
  "city": "Paris",                   // string | null — helps narrow the search
  "check_in": "2026-07-01",         // string | null — YYYY-MM-DD (defaults to next month if omitted)
  "check_out": "2026-07-05",        // string | null — YYYY-MM-DD
  "adults": 2,                       // integer, default: 2
  "currency": "EUR"                  // string, default: "EUR"
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `hotel_name` | Yes | — | Name of the hotel to look up |
| `city` | No | `null` | City helps when name is ambiguous |
| `check_in` | No | next month | Affects pricing shown |
| `check_out` | No | +3 days | Affects pricing shown |
| `adults` | No | `2` | Guest count for `booking_url` |
| `currency` | No | `"EUR"` | Currency for prices |

#### Response `200 OK`

`HotelSearchResponse` with `hotels` containing exactly 1 result (or 0 if not found).

```json
{
  "hotels": [{ /* single HotelResult with full AI analysis */ }],
  "notable_excluded": [],
  "city": "Paris",
  "check_in": "2026-07-01",
  "check_out": "2026-07-05",
  "total_found": 1,
  "session_id": "b2c3d4e5-...",
  "applied_filters_summary": "Direct lookup: Le Bristol Paris",
  "has_more": false
}
```

**curl example:**
```bash
curl -X POST http://localhost:8000/api/hotels/find \
  -H "Content-Type: application/json" \
  -d '{
    "hotel_name": "Le Bristol Paris",
    "city": "Paris",
    "check_in": "2026-07-01",
    "check_out": "2026-07-05",
    "adults": 2
  }'
```

---

### 3.6 POST /api/hotels/explain

Explain why a specific hotel did not appear in the top-10. Useful for a "Why not this hotel?" feature in the UI.

**Method:** `POST`
**URL:** `/api/hotels/explain`
**Response time:** < 1 second (looks up cached session data)

#### Request body

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "hotel_name": "Ibis Paris Bastille"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `session_id` | Yes | From prior `/search` response |
| `hotel_name` | Yes | Hotel name (fuzzy match applied) |

#### Response `200 OK` — `HotelExplanationResponse`

```json
{
  "hotel_id": 99234,
  "hotel_name": "Ibis Paris Bastille",
  "found_in_candidates": true,
  "reason": "Budget hotel — review score 6.8 is below the 7.0 threshold for your search",
  "ai_score": 4.2
}
```

If the hotel was not in the ~80 candidate pool at all:
```json
{
  "hotel_id": null,
  "hotel_name": "Ibis Paris Bastille",
  "found_in_candidates": false,
  "reason": "This hotel was not in the candidate pool (~80 hotels). It may have been filtered by price, review score, or availability.",
  "ai_score": null
}
```

**curl example:**
```bash
curl -X POST http://localhost:8000/api/hotels/explain \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "hotel_name": "Ibis Paris Bastille"
  }'
```

---

## 4. Data Models

### HotelResult

The core hotel object returned in `hotels[]`.

| Field | Swift Type | Description |
|-------|-----------|-------------|
| `hotel_id` | `Int` | Booking.com hotel identifier |
| `name` | `String` | Hotel name |
| `accommodation_type` | `String` | e.g. `"Hotel"`, `"Apartment"`, `"B&B"` |
| `stars` | `Int` | Star rating 0–5 |
| `is_boutique` | `Bool` | `true` if independent (no chain code) and 3–4 stars |
| `url` | `String` | Hotel page URL on Booking.com (without booking params) |
| `booking_url` | `String` | Deep link with pre-filled dates/guests/currency — **use this for the Book button** |
| `review_score` | `Double` | Overall score 0–10 |
| `review_score_word` | `String` | `"Exceptional"` / `"Superb"` / `"Very Good"` / `"Good"` / `"Pleasant"` |
| `review_count` | `Int` | Total number of reviews |
| `category_scores` | `[String: Double]` | Scores by category: `cleanliness`, `comfort`, `location`, `staff`, `value`, `wifi` (some may be absent) |
| `segment_scores` | `[String: Double]` | Scores by traveller type: `couple`, `family`, `business`, `solo`, `group` (may be sparse) |
| `price_per_night` | `Double` | Price per night in `currency` |
| `total_price` | `Double` | Total price for the entire stay in `currency` |
| `currency` | `String` | ISO 4217 currency code, e.g. `"EUR"` |
| `strikethrough_price` | `Double?` | Original price if a discount is active, else `null` |
| `address` | `String` | Full street address |
| `district` | `String?` | Neighbourhood / district name, may be `null` |
| `distance_to_center_km` | `Double` | Distance to city centre in kilometres |
| `latitude` | `Double` | Geographic latitude |
| `longitude` | `Double` | Geographic longitude |
| `photos` | `[String]` | Up to 5 photo URLs from Booking.com CDN (`cf.bstatic.com`). May be empty. |
| `key_facilities` | `[String]` | Top free amenities, e.g. `["Free WiFi", "Pool", "Spa"]`. Up to 10. |
| `breakfast_included` | `Bool` | Whether breakfast is included in the rate |
| `pets_allowed` | `Bool` | Whether pets are allowed |
| `free_cancellation` | `Bool` | Whether free cancellation is available |
| `checkin_from` | `String` | Earliest check-in time, e.g. `"15:00"` (may be empty string) |
| `checkout_until` | `String` | Latest check-out time, e.g. `"12:00"` (may be empty string) |
| `ai_score` | `Double` | AI-computed match score 0–10. Higher = better match for this user's request. |
| `ai_match_reason` | `String` | One-sentence personalised reason this hotel is a great match. Empty if AI fallback was used. |
| `ai_pros` | `[String]` | Top 3 pros from review analysis. |
| `ai_cons` | `[String]` | Top 2 cons (honest — builds trust). |
| `ai_hidden_issues` | `[String]` | Issues detected in reviews not obvious from the score, e.g. `["Ongoing renovation noise reported in 30% of reviews"]`. Often empty. |
| `review_summary` | `String` | 1–2 sentence AI summary of guest sentiment. |
| `interior_style` | `String?` | Vision analysis (top-5 only): `"modern"` / `"classic"` / `"boutique"` / `"rustic"` / `"mixed"`. `null` if not analysed. |
| `view_quality` | `String?` | Vision analysis: `"sea"` / `"city"` / `"garden"` / `"parking"` / `"none"` / `"mixed"`. `null` if not analysed. |
| `visual_cleanliness` | `String?` | Vision analysis: `"excellent"` / `"good"` / `"average"`. `null` if not analysed. |

### ExcludedHotel

Near-miss hotels that scored but didn't make the top-10. Shown in `notable_excluded[]`.

| Field | Swift Type | Description |
|-------|-----------|-------------|
| `hotel_id` | `Int` | Booking.com hotel identifier |
| `name` | `String` | Hotel name |
| `stars` | `Int` | Star rating 0–5 |
| `review_score` | `Double` | Overall review score |
| `price_per_night` | `Double` | Price per night (in the requested currency) |
| `ai_score` | `Double` | Computed AI score — below top-10 threshold |
| `reason` | `String` | Human-readable explanation why it didn't qualify, e.g. `"Price ≥€1,100/night exceeds budget"` |

### HotelSearchResponse

Top-level response from `/search`, `/search/more`, and `/find`.

| Field | Swift Type | Description |
|-------|-----------|-------------|
| `hotels` | `[HotelResult]` | Up to 10 hotels, sorted by `ai_score` descending |
| `notable_excluded` | `[ExcludedHotel]` | 3–5 near-miss hotels (may be empty) |
| `city` | `String` | City name from the request |
| `check_in` | `String` | Check-in date YYYY-MM-DD |
| `check_out` | `String` | Check-out date YYYY-MM-DD |
| `total_found` | `Int` | Total hotels available on Booking.com for these dates |
| `session_id` | `String` | Opaque session identifier. Pass to `/search/more` for pagination. TTL: 30 minutes. |
| `applied_filters_summary` | `String` | Human-readable summary of applied filters, e.g. `"Budget ≤200/night · Score ≥7 · Paris (847 hotels)"` |
| `has_more` | `Bool` | `true` if more hotels can be fetched via `/search/more` |

### HotelExplanationResponse

Response from `/explain`.

| Field | Swift Type | Description |
|-------|-----------|-------------|
| `hotel_id` | `Int?` | Booking.com hotel ID if found in candidates, else `null` |
| `hotel_name` | `String` | Hotel name (echoed from request, may be normalised) |
| `found_in_candidates` | `Bool` | `true` if the hotel was in the analysed candidate pool |
| `reason` | `String` | Explanation of why the hotel didn't make the top-10 |
| `ai_score` | `Double?` | Computed AI score if available, else `null` |

---

## 5. Booking URL Deep Links

Every `HotelResult` contains a `booking_url` — a pre-built Booking.com URL with all booking parameters already filled in.

### URL format

```
https://www.booking.com/hotel/{country}/{slug}.html
  ?checkin=2026-07-01
  &checkout=2026-07-05
  &group_adults=2
  &group_children=2
  &selected_currency=EUR
  &age=5
  &age=8
```

**Parameters always present:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `checkin` | YYYY-MM-DD | Check-in date |
| `checkout` | YYYY-MM-DD | Check-out date |
| `group_adults` | integer | Number of adults |
| `group_children` | integer | Number of children |
| `selected_currency` | ISO code | Display currency |
| `age` | integer (repeatable) | Age of each child (one param per child) |

**Fallback URL** (when hotel page URL is unavailable):
```
https://www.booking.com/searchresults.html
  ?checkin=...&checkout=...&group_adults=...&hotel_id=1769895
```

### How to use in iOS

**Simple: open in Safari**
```swift
if let url = URL(string: hotel.bookingUrl), !hotel.bookingUrl.isEmpty {
    UIApplication.shared.open(url)
}
```

**In-app WebView (SFSafariViewController):**
```swift
import SafariServices

func openBooking(hotel: HotelResult) {
    guard let url = URL(string: hotel.bookingUrl) else { return }
    let safari = SFSafariViewController(url: url)
    present(safari, animated: true)
}
```

The URL is always non-empty — a fallback `searchresults.html` URL is generated even when the API doesn't return a direct hotel page URL.

---

## 6. SSE Streaming — iOS Guide

The `/search/stream` endpoint uses **Server-Sent Events (SSE)** over a persistent HTTP connection. Each event is a UTF-8 text block with `event:` and `data:` lines separated by blank lines.

### Why SSE with a POST request?

Standard `EventSource` in browsers only supports GET. iOS `URLSession` supports POST SSE manually via a streaming `URLSessionDataTask`. The pattern below handles this correctly.

### Implementation

```swift
import Foundation

class HotelSearchSSEClient: NSObject, URLSessionDataDelegate {

    // Callbacks
    var onProgress: ((Int, String, Double) -> Void)?
    var onResult: ((HotelSearchResponse) -> Void)?
    var onError: ((String, Int) -> Void)?
    var onDone: (() -> Void)?

    private var session: URLSession?
    private var buffer = ""

    func startSearch(request: HotelSearchRequest) {
        let url = URL(string: "\(AppConfig.baseURL)/api/hotels/search/stream")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        urlRequest.httpBody = try? JSONEncoder().encode(request)

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 70  // > max pipeline time (62s)
        config.timeoutIntervalForResource = 70

        session = URLSession(configuration: config, delegate: self, delegateQueue: .main)
        session?.dataTask(with: urlRequest).resume()
    }

    func cancel() {
        session?.invalidateAndCancel()
    }

    // MARK: - URLSessionDataDelegate

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                    didReceive data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        buffer += text
        processBuffer()
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    didCompleteWithError error: Error?) {
        if let error = error {
            onError?("Connection error: \(error.localizedDescription)", 0)
        }
        onDone?()
    }

    // MARK: - SSE parsing

    private func processBuffer() {
        // Events are separated by double newline
        while let range = buffer.range(of: "\n\n") {
            let eventBlock = String(buffer[..<range.lowerBound])
            buffer = String(buffer[range.upperBound...])
            parseEvent(eventBlock)
        }
    }

    private func parseEvent(_ block: String) {
        var eventType = ""
        var dataLine = ""

        for line in block.components(separatedBy: "\n") {
            if line.hasPrefix("event: ") {
                eventType = String(line.dropFirst("event: ".count)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("data: ") {
                dataLine = String(line.dropFirst("data: ".count)).trimmingCharacters(in: .whitespaces)
            }
        }

        guard !eventType.isEmpty, let jsonData = dataLine.data(using: .utf8) else { return }

        switch eventType {
        case "progress":
            if let payload = try? JSONDecoder().decode(ProgressPayload.self, from: jsonData) {
                onProgress?(payload.phase, payload.message, payload.progress)
            }
        case "result":
            if let response = try? JSONDecoder().decode(HotelSearchResponse.self, from: jsonData) {
                onResult?(response)
            }
        case "error":
            if let payload = try? JSONDecoder().decode(ErrorPayload.self, from: jsonData) {
                onError?(payload.message, payload.status)
            }
        case "done":
            onDone?()
        default:
            break
        }
    }

    // MARK: - Payload types

    private struct ProgressPayload: Decodable {
        let phase: Int
        let message: String
        let progress: Double
    }

    private struct ErrorPayload: Decodable {
        let message: String
        let status: Int
    }
}
```

### Usage in a ViewModel

```swift
@MainActor
class HotelSearchViewModel: ObservableObject {
    @Published var hotels: [HotelResult] = []
    @Published var progressValue: Double = 0
    @Published var progressMessage: String = "Starting search…"
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let sseClient = HotelSearchSSEClient()

    func search(city: String, checkIn: String, checkOut: String, adults: Int) {
        isLoading = true
        progressValue = 0
        hotels = []
        errorMessage = nil

        let request = HotelSearchRequest(
            city: city, checkIn: checkIn, checkOut: checkOut, adults: adults
        )

        sseClient.onProgress = { [weak self] phase, message, progress in
            self?.progressValue = progress
            self?.progressMessage = message
        }

        sseClient.onResult = { [weak self] response in
            self?.hotels = response.hotels
            self?.isLoading = false
        }

        sseClient.onError = { [weak self] message, _ in
            self?.errorMessage = message
            self?.isLoading = false
        }

        sseClient.onDone = { [weak self] in
            self?.isLoading = false
        }

        sseClient.startSearch(request: request)
    }

    func cancel() { sseClient.cancel() }
}
```

### SwiftUI progress bar

```swift
struct HotelSearchProgressView: View {
    @ObservedObject var vm: HotelSearchViewModel

    var body: some View {
        VStack(spacing: 16) {
            ProgressView(value: vm.progressValue)
                .progressViewStyle(.linear)
                .animation(.easeInOut, value: vm.progressValue)

            Text(vm.progressMessage)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}
```

### Key points

- Set `timeoutIntervalForRequest` to at least **70 seconds** (pipeline takes up to 62s).
- Buffer incoming `Data` chunks — SSE events may arrive split across multiple `didReceive` calls.
- Events are delimited by `\n\n` (double newline).
- The `result` event contains the full `HotelSearchResponse` JSON — same shape as the `/search` response.
- If `error` is received instead of `result`, show the error and treat as a failed search.
- `done` is always the last event. Use it to hide loading UI.

---

## 7. Pagination Flow

Sessions expire after **30 minutes**. Show "Load more" only when `has_more == true`.

```
┌─────────────────────────────────────────────────────────────────┐
│                    HOTEL SEARCH FLOW                            │
│                                                                 │
│  User taps "Search"                                             │
│        │                                                        │
│        ▼                                                        │
│  POST /api/hotels/search/stream  (or /search)                   │
│        │  30–62s                                                │
│        ▼                                                        │
│  HotelSearchResponse {                                          │
│    hotels: [10 hotels],                                         │
│    session_id: "abc...",   ◄── save this                        │
│    has_more: true                                               │
│  }                                                              │
│        │                                                        │
│        │  Show top-10 hotels                                    │
│        │                                                        │
│        │  User scrolls to bottom                                │
│        ▼                                                        │
│  has_more == true?                                              │
│    YES → show "Load 10 more" button                             │
│    NO  → show "All hotels shown"                                │
│                                                                 │
│        │  User taps "Load 10 more"                              │
│        ▼                                                        │
│  POST /api/hotels/search/more                                   │
│  { "session_id": "abc..." }                                     │
│        │  30–50s                                                │
│        ▼                                                        │
│  HotelSearchResponse {                                          │
│    hotels: [next 10],                                           │
│    session_id: "abc...",   ◄── same session_id                  │
│    has_more: true | false                                       │
│  }                                                              │
│        │                                                        │
│        │  Append new hotels to the list                         │
│        │  Repeat until has_more == false                        │
│        ▼                                                        │
│  has_more == false, hotels == [] → "No more hotels available"   │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation notes:**
- The `session_id` stays the same across all `/search/more` calls — it's the key to the cached session, not a page token.
- Append new hotels to the existing array — don't replace.
- Guard against calling `/search/more` while a previous call is still in flight.
- On 404 (session expired): prompt the user to search again.

---

## 8. UI Recommendations

### Hotel Card (list view)

Minimum fields to show on a compact card:

```
┌─────────────────────────────────────────────┐
│ [photo]  ★★★★☆  4.2 km from centre          │
│          Hotel Name                          │
│          ⭐ 9.2 · Exceptional · 2,847 reviews│
│          Romantic boutique in Saint-Germain  │ ← ai_match_reason
│          From €245/night  [Book →]           │
└─────────────────────────────────────────────┘
```

**Field mapping:**

| UI element | Field | Notes |
|-----------|-------|-------|
| Photo | `photos[0]` | Fall back to placeholder if `photos` is empty |
| Star rating | `stars` | Show ★ icons (0–5) |
| Distance badge | `distance_to_center_km` | e.g. `"1.2 km"` |
| Hotel name | `name` | |
| AI score | `ai_score` | `"AI Score: 8.7"` or coloured pill |
| Review score | `review_score` + `review_score_word` | e.g. `"9.2 · Exceptional"` |
| Review count | `review_count` | e.g. `"2,847 reviews"` |
| Match reason | `ai_match_reason` | 1-line personalised reason |
| Price | `price_per_night` + `currency` | e.g. `"From €245/night"` |
| Strikethrough | `strikethrough_price` | Show crossed-out if not null |
| Book button | `booking_url` | Opens Booking.com |

### Hotel Detail Screen

Show expanded content:

```
Photos carousel      → photos[] (horizontal scroll, up to 5)
Name + stars         → name, stars
AI score pill        → ai_score
Match reason         → ai_match_reason (full text)
Key facilities chips → key_facilities[] (e.g. "Free WiFi", "Pool")
Breakfast badge      → breakfast_included
Free cancel badge    → free_cancellation

"Why we love it" section:
  • ai_pros[] — bullet list

"Worth knowing" section:
  • ai_cons[] — bullet list
  • ai_hidden_issues[] — if non-empty, show with ⚠️ icon

Review summary       → review_summary
Review score grid:
  Cleanliness        → category_scores["cleanliness"]
  Comfort            → category_scores["comfort"]
  Location           → category_scores["location"]
  Staff              → category_scores["staff"]
  Value              → category_scores["value"]
  WiFi               → category_scores["wifi"]

For couples/families:
  Couples score      → segment_scores["couple"]
  Family score       → segment_scores["family"]

Address + map pin    → address, latitude, longitude
Check-in / out       → checkin_from, checkout_until

[Book on Booking.com →] → booking_url (prominent CTA)
```

### Notable Excluded Section

Show below the top-10 list as a collapsible "Hotels that almost made it" section:

```swift
ForEach(response.notableExcluded) { hotel in
    HStack {
        VStack(alignment: .leading) {
            Text(hotel.name).font(.headline)
            Text(hotel.reason).font(.caption).foregroundStyle(.secondary)
        }
        Spacer()
        Text("Score: \(hotel.aiScore, specifier: "%.1f")")
            .foregroundStyle(.secondary)
    }
}
```

### AI Score colour coding

```swift
func aiScoreColor(_ score: Double) -> Color {
    switch score {
    case 8.5...: return .green      // Exceptional match
    case 7.0..<8.5: return .yellow  // Good match
    default: return .orange          // Acceptable match
    }
}
```

### Loading state (SSE)

```swift
if vm.isLoading {
    VStack {
        ProgressView(value: vm.progressValue)
        Text(vm.progressMessage)
            .font(.caption)
            .foregroundStyle(.secondary)
    }
} else if vm.hotels.isEmpty && vm.errorMessage == nil {
    Text("No hotels found. Try adjusting your criteria.")
} else if let error = vm.errorMessage {
    ErrorView(message: error) { vm.search(...) }  // retry button
} else {
    HotelListView(hotels: vm.hotels)
}
```

---

*Generated from live backend source: `src/hotels/domain/schemas.py`, `src/hotels/api/router.py`, `src/hotels/application/orchestrator.py` — Stage 4 (2026-03-22)*
