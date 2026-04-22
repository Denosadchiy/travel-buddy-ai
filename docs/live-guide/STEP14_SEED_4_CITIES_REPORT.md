# Step 14: Seed 4 New Cities for Live Guide

**Date:** 2026-04-21
**Status:** Complete

## Overview

Seeded 4 new cities into the Live Guide system: **Paris**, **Dubai**, **Shanghai**, **Istanbul**. Each city went through the full seeder pipeline: Zone Discovery (DBSCAN) -> auto-select best zone -> PointPlacement (OSMnx) -> GraphBuilder (networkx) -> KnowledgeCollector (Wikipedia + Wikidata + Google Details).

Audio content generation was NOT performed (no ElevenLabs subscription). Only geo-structure + knowledge cards were created.

## Results Summary

| City | Zones Found | Recommended Zone | POI | Connectors | Edges | Knowledge Cards | Wikipedia | Wikidata | Google |
|------|------------|-----------------|-----|-----------|-------|----------------|-----------|----------|--------|
| **Paris** | 4 | Eiffel Tower | 189 | 2,605 | 11,000 | 2,770 | 150 | 144 | 160 |
| **Dubai** | 10 | Zabeel Park | 53 | 1,096 | 4,620 | 1,168 | 58 | 55 | 71 |
| **Shanghai** | 2 | The Bund | 15 | 62 | 257 | 73 | 11 | 11 | 11 |
| **Istanbul** | 6 | Hagia Sophia Grand Mosque | 104 | 907 | 3,932 | 993 | 76 | 75 | 84 |
| **TOTAL** | 22 | — | **361** | **4,670** | **19,809** | **5,004** | **295** | **285** | **326** |

(Moscow's existing Red Square zone: 67 POI, 998 points, 46 Wikipedia — unchanged.)

## Per-City Details

### Paris, France

- **Zones discovered:** 4 (Eiffel Tower, Jardin du Luxembourg, Cimetiere du Pere-Lachaise, Jardin des Tuileries)
- **Recommended:** "Eiffel Tower" — largest zone by POI count (189 POI)
- **Zone center:** (48.8627, 2.3322), area ~38.92 km2
- **DBSCAN params:** eps=800m, min_samples=5, rating>=3.5, reviews>=30
- **Key POI:** Eiffel Tower, Louvre, Notre-Dame, Arc de Triomphe, Musee d'Orsay, Sacre-Coeur, Pantheon
- **Wikipedia coverage:** 150/189 POI (79%) — excellent
- **Zone size note:** This zone covers a large portion of central Paris. For production, CPO may want to split it into 2-3 sub-zones (e.g. Ile de la Cite, Montmartre, Latin Quarter) for more focused audio tours.

### Dubai, UAE

- **Zones discovered:** 10 (Zabeel Park, Dubai Marina, Palm Jumeirah, etc.)
- **Recommended:** "Zabeel Park" — highest POI density near downtown
- **Zone center:** (25.2487, 55.3103), area ~19.13 km2
- **DBSCAN params:** eps=1200m (wider due to Dubai's spread-out layout), min_samples=5
- **Key POI:** Burj Khalifa, Dubai Frame, Dubai Museum, Gold Souk, Zabeel Park
- **Wikipedia coverage:** 58/53 POI (most POI have Wikipedia)
- **Note:** Dubai's tourist attractions are geographically spread out. The "Zabeel Park" zone captures the Downtown/Business Bay/Old Dubai corridor. Dubai Marina and Palm Jumeirah form separate zones.

### Shanghai, China

- **Zones discovered:** 2 (The Bund, Jing'an)
- **Recommended:** "The Bund" — iconic waterfront promenade
- **Zone center:** (31.2371, 121.4919), area ~2.91 km2
- **DBSCAN params:** eps=800m, min_samples=5
- **Key POI:** The Bund, Yu Garden, Nanjing Road, Shanghai Tower, Oriental Pearl TV Tower
- **Wikipedia coverage:** 11/15 POI (73%)
- **Note:** Shanghai has fewer Google Places POI classified as "tourist_attraction" compared to European cities. The zone is compact and highly walkable — ideal for an audio tour. French Concession would be a good candidate for a second zone.

### Istanbul, Turkey

- **Zones discovered:** 6 (Hagia Sophia, Fatih Sultan Mehmet Bridge area, others)
- **Recommended:** "Hagia Sophia Grand Mosque" — Sultanahmet district
- **Zone center:** (41.0299, 28.9845), area ~18.04 km2
- **DBSCAN params:** eps=800m, min_samples=5
- **Key POI:** Hagia Sophia, Blue Mosque, Topkapi Palace, Grand Bazaar, Basilica Cistern, Galata Tower
- **Wikipedia coverage:** 76/104 POI (73%) — good
- **Note:** The zone covers Sultanahmet + Beyoglu/Galata on both sides of the Golden Horn. Very rich in historical content.

## Content Generation Estimates

| City | Main | Bonus | Transitions | Commentary | Total Blocks | LLM Calls | ElevenLabs chars |
|------|------|-------|-------------|-----------|-------------|-----------|-----------------|
| Paris | 189 | 189 | ~33,000 | ~2,605 | ~36,172 | ~36,172 | ~14.5M |
| Dubai | 53 | 53 | ~13,860 | ~1,096 | ~15,115 | ~15,115 | ~6.0M |
| Shanghai | 15 | 15 | ~771 | ~62 | ~878 | ~878 | ~351K |
| Istanbul | 104 | 104 | ~11,796 | ~907 | ~13,015 | ~13,015 | ~5.2M |
| **TOTAL** | **361** | **361** | **~59,427** | **~4,670** | **~65,180** | **~65,180** | **~26.1M** |

**Cost estimates:**
- io.net LLM calls: ~65,180 calls x ~$0.001/call = **~$65** (for all 4 cities)
- ElevenLabs: ~26.1M characters. At Creator plan pricing ($22/month, 100K chars) this would require ~261 months. **Recommendation:** upgrade to Scale plan or use batch synthesis with limits.

**Realistic approach:** For MVP, generate content only for POI points (not all connectors). This reduces blocks to ~3,600 (main+bonus+recap per POI + transitions between POIs only), cost ~$3.60 io.net, ~1.4M ElevenLabs chars (~14 months on Creator plan, or ~2 weeks on Scale plan).

## HTML Maps

All maps are in `tmp/zone_proposals/`:

| File | Size | Description |
|------|------|-------------|
| `paris_zones.html` | 27 KB | All 4 zones with RECOMMENDED badge |
| `paris_points.html` | 1,432 KB | POI + connector points + edges |
| `dubai_zones.html` | 19 KB | All 10 zones with RECOMMENDED badge |
| `dubai_points.html` | 614 KB | POI + connector points + edges |
| `shanghai_zones.html` | 8 KB | All 2 zones with RECOMMENDED badge |
| `shanghai_points.html` | 39 KB | POI + connector points + edges |
| `istanbul_zones.html` | 19 KB | All 6 zones with RECOMMENDED badge |
| `istanbul_points.html` | 524 KB | POI + connector points + edges |

Each zones map has:
- All discovered zones as colored polygons
- Recommended zone highlighted in blue with star badge
- Sidebar with summary statistics and content estimates
- POI markers inside recommended zone
- List of all zones with POI counts

## Google Places API Usage

| City | Nearby Search | Place Details | Reverse Geocode | Total Requests | Est. Cost |
|------|--------------|--------------|----------------|----------------|-----------|
| Paris | ~20 | ~189 | ~2,605 | ~2,814 | ~$2.80 |
| Dubai | ~25 | ~53 | ~1,096 | ~1,174 | ~$1.20 |
| Shanghai | ~20 | ~15 | ~62 | ~97 | ~$0.50 |
| Istanbul | ~20 | ~104 | ~907 | ~1,031 | ~$1.00 |
| **TOTAL** | **~85** | **~361** | **~4,670** | **~5,116** | **~$5.50** |

## Database State After Seeding

```
5 cities:    Dubai, Istanbul, Moscow, Paris, Shanghai
5 approved zones (1 per city, all is_active=TRUE)
22 total zones discovered (remaining 17 unapproved, available for future expansion)
5,004 knowledge cards (295 with Wikipedia, 285 with Wikidata)
19,809 edges across all zones
```

## Script Created

`scripts/guide/seed_cities.py` — reusable seeder script for multiple cities:
- `--non-interactive` — required flag
- `--city <name>` — process single city
- `--phase discovery|full` — stop after zone discovery or run full pipeline

## What Was NOT Done

- Text content generation (DraftGenerator) — next step
- Audio synthesis — no ElevenLabs subscription
- New database migrations — guide_* tables already exist
- Moscow zone modifications — untouched

## Recommendations for CPO

1. **Paris zone is very large** (39 km2, 189 POI). Consider splitting into 2-3 sub-zones for focused 30-60 minute tours.
2. **Shanghai zone is compact** (2.9 km2, 15 POI) — ideal for a single 30-minute tour. Consider adding French Concession as second zone.
3. **Dubai zone** covers Downtown to Old Dubai — good mix of modern and historic.
4. **Istanbul zone** covers Sultanahmet + Galata — the most tourist-dense area.
5. **Content generation** should start with Shanghai (smallest, cheapest to test) then Istanbul (rich historical content, moderate size).
