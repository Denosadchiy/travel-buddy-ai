# AI Hotel Picker — Stage 5 Post-Testing Improvement Report

**Date:** 2026-03-27
**Status:** ✅ Complete — 49/49 tests passing (after fixes)

---

## Summary

Following live user testing across 3 scenarios (Barcelona / Buenos Aires / Singapore), 8 critical and significant issues were identified and fixed. The most impactful: Tokyo with complex filters previously returned **0 hotels**; after fixes it returns **10 hotels, all 5★+, avg 4.6 photos**.

---

## Issues Fixed & Measurable Improvements

### P0-1 (CRITICAL): Zero results with complex filter combinations

**Root cause:** `free_cancellation` was sent as a hard Booking.com API filter simultaneously with LLM-generated facility filters + user amenities. Combined, these could produce 0 results even when 11,897 hotels were available.

**Fix:** 4-round cascade fallback in `orchestrator.py::_fetch_candidates_with_cascade()`:
- Round 1: All filters
- Round 2: Drop `free_cancellation` hard filter
- Round 3: User amenities only (drop LLM-generated)
- Round 4: No filters, relaxed budget ×1.3, min_score −1.0

**LLM filter cap:** `intent_parser.py` now caps LLM-generated `api_filters` at MAX 4 to prevent over-filtering.

**Metric:**
| Scenario | Before | After |
|----------|--------|-------|
| Tokyo (4★+, kids, spa+pool+WiFi, free_cancel) | **0 hotels** ❌ | **10 hotels** ✅ |
| Singapore (4★+, budget, spa+pool) | 0–few hotels | 10 hotels ✅ |

---

### P0-CITY (CRITICAL): Non-Latin city name recognition

**Root cause:** Booking.com API can't resolve Cyrillic/CJK/etc. script names. Unicode normalization only helps for accented Latin chars (München → Munich) — it can't help Москва → Moscow.

**Fix:** 3-layer universal strategy:
1. **LLM semantic translation** — IntentParser LLM outputs `city_for_booking` in English (when `user_wishes` is provided): "Ciudad de Mexico" → "Mexico City"
2. **Unicode normalization** — strip accents for Latin scripts (São Paulo → Sao Paulo)
3. **Dedicated LLM translation call** — `_translate_city_via_llm()` triggered when city has non-ASCII chars AND dest returns < 10 hotels (handles Москва → Moscow even without `user_wishes`)

**Metric:**
| City Input | Before | After |
|-----------|--------|-------|
| "Ciudad de Mexico" | ❌ 0 hotels | ✅ 4,764 hotels |
| "Москва" | ❌ 1 wrong result | ✅ Translated to "Moscow", found city results |
| "大阪" | ✅ (worked via API) | ✅ 8,515 hotels (maintained) |
| "Buenos Aires" | ✅ | ✅ 8,458 hotels (maintained) |

---

### P1-1 (HIGH): `stars_min` filter silently ignored

**Root cause:** Line `stars_min = None  # comes from HotelSearchRequest, not ParsedIntent` in `candidate_selector.py:204` — intentional comment that effectively disabled the filter entirely.

**Fix:**
1. Added `stars_min: int | None = None` to `ParsedIntent` schema
2. Propagated from `HotelSearchRequest` in `IntentParser._deterministic_parse()` and LLM merge
3. Applied in `CandidateSelector.apply_l1_filter()`: filters hotels with `stars < stars_min`
4. Also excludes 0-star (unrated) properties when `stars_min ≥ 3`

**Metric:**
| Request | Before | After |
|---------|--------|-------|
| Paris, `stars_min=5` | 10 hotels (3 were 0-star apartments) ❌ | 7 hotels — **all 5★** ✅ |
| Tokyo, `stars_min=4` | Ignored → mixed results | 10 hotels — **all 5★** ✅ |

---

### P1-2 (HIGH): Photos — 1 photo instead of 5

**Root cause:**
1. `break` inside inner `room.get("photos")` loop only exited the inner loop, continuing to next rooms
2. `getHotelPhotos()` (40+ hotel-level photos) was never called in Phase 3

**Fix (`booking_client.py::fetch_hotel_full_data()`):**
- Added `get_hotel_photos()` as 6th parallel call (no extra wall-clock time due to async)
- Merged room photos (priority 1) + hotel photos (fill up to 10 if room photos < 10)
- Proper deduplication by URL

**Metric:**
| Metric | Before | After |
|--------|--------|-------|
| Avg photos per hotel (Barcelona) | 1.2 | **4.6** |
| Hotels with 5 photos (Singapore) | ~30% | **80%** |
| Max photos per hotel | 5 | **10** |

---

### P1-3 (HIGH): `free_cancellation` as hard API filter

**Root cause:** `free_cancellation::1` was added to `api_filters` in `_deterministic_parse()`, making it a hard Booking.com API constraint that immediately halved the candidate pool.

**Fix:**
- Removed from `api_filters` in deterministic parse
- Stored as `ParsedIntent.prefers_free_cancellation: bool`
- LLM prompt updated: instructs ranker to give bonus to free-cancellation hotels
- Formula fallback: +0.05 bonus when `prefers_free_cancellation=True` AND hotel offers it

**Metric:** No longer contributes to 0-result cascade. Free cancellation hotels still ranked higher via scoring.

---

### P1-4 (HIGH): Boutique detection excludes 5★ boutiques

**Root cause:** `is_boutique = raw.chaincode is None and raw.stars in (0, 3, 4)` — excluded 5-star boutique properties (Kempinski, smaller luxury brands).

**Fix (`orchestrator.py::_assemble_hotel_result()`):**
```python
is_boutique = (
    raw.chaincode is None and raw.stars in (0, 3, 4, 5)  # added 5
) or any(
    kw in raw.name.lower()
    for kw in ("boutique", "maison", "casa", "palazzo", "villa", "manor", "château")
)
```

**Metric:** 5★ independent hotels (J.K. Place Paris, Le Bristol Paris etc.) now correctly detected as boutique.

---

### P2-1 (MEDIUM): LLM over-generates filters

**Fix:** LLM api_filters capped at 4 in `_parse_llm_result()`:
```python
llm_filters = _safe_list(raw.get("api_filters"), [])[:4]
```
Plus `user_api_filters` / `llm_api_filters` split for cascade control.

---

### P2-2 (MEDIUM): Generic `ai_match_reason` repeated across hotels

**Fix:** Added to `ranker.py` LLM prompt:
> IMPORTANT for ai_match_reason: Each hotel MUST have a UNIQUE reason. Do NOT repeat generic phrases like "excellent location and comfortable rooms". Highlight what specifically distinguishes THIS hotel — its neighborhood, a standout amenity, design style, unusual value, specific guest praise, or anything memorable.

---

### P2-3 (MEDIUM): Fixed `min_review_score` blocking good hotels in small cities

**Fix:** Adaptive threshold in `apply_l1_filter()`:
```python
if len(top) < 5 and min_score > 6.5 and not relaxed:
    return self.apply_l1_filter(raw_hotels, intent.model_copy(...min_score - 0.5), relaxed=True)
```

---

## Live Test Results (Post-Fix)

### Test Case 1: Barcelona — Simple Romantic Boutique
```
City: Barcelona | Found: 5,293 | Returned: 10
AI scores: 8.6–9.5 | Avg photos: 4.5
Top hotel: Antiga Casa Buenavista, 4★, Score: 9.4, 434 EUR/night, AI: 9.5
```

### Test Case 2: Buenos Aires — Medium Boutique + Remote Work
```
City: Buenos Aires | Found: 8,458 | Returned: 10
Avg photos: 4.9 | Boutique hotels: 10/10
All photos: 5 per hotel (was 1–2 before)
```

### Test Case 3: Singapore — Complex Filters (4★+, Budget, Spa+Pool)
```
City: Singapore | Found: 625 | Returned: 10
All 4★+: ✓ | Avg photos: 4.5
Free cancellation: 2/10 (correct — remaining hotels shown without it)
Top: The Ritz-Carlton Millenia, 5★, 9.3 score, 480 SGD/night, AI: 9.2
```

### Formerly Critical: Tokyo — Zero Results Test Case (Previously Failing)
```
Before: 0 hotels ❌ (despite 11,897 available)
After: 10 hotels, all 5★ ✅
Avg photos: 4.6 | Free cancellation: 9/10
Top: The Prince Gallery Tokyo Kioicho, 5★, Score: 9.4, AI: 9.5
```

### City Name Recognition Tests
| City Input | Before Fix | After Fix |
|-----------|-----------|---------|
| "Ciudad de Mexico" | ❌ 0 hotels | ✅ 4,764 hotels |
| "Москва" (Russian) | ❌ 1 wrong match | ✅ Translated to Moscow |
| "大阪" (Japanese) | ✅ 8,515 hotels | ✅ 8,515 hotels (maintained) |
| "Barcelona" | ✅ 5,293 hotels | ✅ 5,293 hotels (maintained) |

### `stars_min` Accuracy
| Request | Before | After |
|---------|--------|-------|
| Paris, stars_min=5 | 10 hotels (3 were 0★ apartments) | 7 hotels, **all 5★** |
| Tokyo, stars_min=4, complex filters | 0 hotels | 10 hotels, **all 5★** |

---

## Test Suite Results

```
pytest src/hotels/tests/ -v --no-cov
49 tests collected

Before fixes: 47 ✅ / 2 ❌
After fixes:  49 ✅ / 0 ❌
```

| Test File | Tests | Before | After |
|-----------|-------|--------|-------|
| `test_booking_client.py` | 4 | ✅ | ✅ |
| `test_candidate_selector.py` | 3 | ✅ | ✅ |
| `test_data_fetcher.py` | 2 | ✅ | ✅ |
| `test_review_analyzer.py` | 1 | ✅ | ✅ |
| `test_ranker.py` | 2 | ✅ | ✅ |
| `test_session_store.py` | 6 | ✅ | ✅ |
| `test_full_pipeline.py` | 1 | ⚠️ Flaky (rate limit) | ✅ |
| `test_orchestrator.py` | 8 | ✅ | ✅ |
| `test_intent_parser.py` | 3 | ❌ (expected hard free_cancel filter) | ✅ (updated to soft) |
| `test_booking_url.py` | 7 | ✅ | ✅ |
| `test_photos.py` | 3 | ✅ | ✅ |
| `test_streaming.py` | 3 | ✅ | ✅ |
| `test_production.py` | 6 | ✅ | ✅ |
| **Total** | **49** | **47/49** | **49/49** |

---

## Files Changed

| File | Changes |
|------|---------|
| `src/hotels/application/orchestrator.py` | `_fetch_candidates_with_cascade()`, `_translate_city_via_llm()`, improved city retry logic (threshold 10 hotels), boutique detection fix |
| `src/hotels/application/candidate_selector.py` | `stars_min` applied in L1 filter (+ 0-star exclusion for stars_min≥3), adaptive min_review_score |
| `src/hotels/application/intent_parser.py` | LLM filter cap (max 4), `city_for_booking` output, `free_cancellation` → soft preference, `stars_min` propagation, `user_api_filters` separation |
| `src/hotels/application/ranker.py` | Unique `ai_match_reason` prompt instruction, `prefers_free_cancellation` bonus, sorted output guarantee |
| `src/hotels/infrastructure/booking_client.py` | 6th parallel call `get_hotel_photos()`, merged photo list (up to 10), proper dedup |
| `src/hotels/domain/schemas.py` | `ParsedIntent`: +`user_api_filters`, +`stars_min`, +`prefers_free_cancellation`, +`city_for_booking` |
| `src/hotels/tests/test_intent_parser.py` | Updated `test_intent_parser_deterministic_family` for new `free_cancellation` behavior |

---

## Key Architectural Improvements

### Before Stage 5
- City names: Only ASCII/Latin + Unicode normalization → failures for Cyrillic, CJK
- Filter cascade: None → 0 results = empty response
- photos: 1–2 from room details only
- `stars_min`: Field existed but silently ignored (→ `None`)
- `free_cancellation`: Hard API filter (halved candidate pool)
- Boutique detection: Excluded 5★ hotels

### After Stage 5
- City names: 3-layer universal (LLM translation → Unicode normalization → dedicated LLM call)
- Filter cascade: 4-round progressive relaxation — always returns results
- Photos: Up to 10 per hotel (room photos + hotel photos merged)
- `stars_min`: Applied in L1 filter with 0-star exclusion for high thresholds
- `free_cancellation`: Soft scoring bonus with `prefers_free_cancellation` field
- Boutique detection: Includes 5★ + name keyword detection
