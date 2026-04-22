# Step 15.1: Universal Scripts + Walking Commentary for 4 Cities

**Date:** 2026-04-22
**Status:** Complete

## 1. Scripts Created

### `scripts/guide/generate_content.py` (NEW)

Universal content generation for any zone. Replaces `topup_content.py` (POI content) + text phase of `produce_yakimanka.py` (walking commentary).

**Parameters:**
- `--zone-id` (required) — UUID of the zone
- `--language` (required) — en / ru
- `--voice-style` — academic / friendly / dramatic / minimal (default: academic)
- `--poi-only` — skip walking commentary
- `--commentary-only` — only walking commentary
- `--skip-transitions` — skip transition generation
- `--commentary-spacing-m` — min distance between commentary points (default: 120m)
- `--max-llm-calls` — LLM call budget (default: 5000)
- `--force-regenerate` — overwrite existing blocks
- `--non-interactive` (required)

**Flow:** POI content (DraftGenerator) → Transitions → Walking commentary (WALKING_COMMENTARY_PROMPT) → Coherence validation → Quality gate → Batch approve

### `scripts/guide/synthesize_audio.py` (NEW)

Universal audio synthesis for any zone via ElevenLabs TTS.

**Parameters:**
- `--zone-id`, `--language`, `--voice-style`, `--non-interactive` (required)
- `--dry-run` — count chars and estimate cost only
- `--parallel-concurrency` — ElevenLabs concurrent requests (default: 3)
- `--content-types` — comma-separated filter (main, bonus, transition, walking_commentary)

**Key design decision:** No FFmpeg postprocessing — ElevenLabs outputs well-normalized audio (-23 dB). Previous FFmpeg loudnorm destroyed audio (root cause of silent files bug in Step 13).

### Old scripts preserved:
- `topup_content.py` — unchanged, still usable
- `produce_yakimanka.py` — unchanged, still usable
- `quality_gate_yakimanka.py` — unchanged

## 2. Walking Commentary by City

| City | Connectors Total | Selected (120m spacing) | Generated | LLM Calls |
|------|-----------------|------------------------|-----------|-----------|
| Shanghai | 2,069 | 1,164 | 229 | 231 |
| Dubai | 1,096 | 468 | 468 | 468 |
| Istanbul | 907 | 413 | 413 | 413 |
| Paris | 2,605 | 1,171 | 1,171 | 1,171 |
| **TOTAL** | **6,677** | **3,216** | **2,281** | **2,283** |

Note: Shanghai had 1,164 connectors selected but only 229 needed generation (the rest were already in DB from an earlier partial run that inserted 935 commentary blocks before validation crashed).

## 3. Final Statistics (All 5 Cities)

| City | Main | Bonus | Recap | Trans | Commentary | Total | Audio |
|------|------|-------|-------|-------|------------|-------|-------|
| Dubai | 59 | 59 | 59 | 708 | 468 | **1,353** | 0 |
| Istanbul | 76 | 76 | 76 | 912 | 413 | **1,553** | 0 |
| Moscow | 216 | 215 | 132 | 1,584 | 73 | **2,220** | 193 |
| Paris | 145 | 145 | 145 | 1,740 | 1,171 | **3,346** | 0 |
| Shanghai | 18 | 18 | 18 | 216 | 1,164 | **1,434** | 0 |
| **TOTAL** | **514** | **513** | **430** | **5,160** | **3,289** | **9,906** | **193** |

- **Grand total blocks:** 9,906
- **Blocks with audio (Moscow only):** 193
- **Blocks without audio (4 cities):** 7,686
- **All blocks status:** reviewed (ready for synthesis)

## 4. io.net Usage

| Step | Calls | Est. Cost |
|------|-------|-----------|
| Step 15 POI content | ~2,280 | ~$2.30 |
| Step 15.1 Commentary | ~2,283 | ~$2.28 |
| **Total** | **~4,563** | **~$4.56** |

## 5. SQL Dump

```
File: tmp/guide_data_5_cities.sql
Size: 17 MB
Lines: 58,101
```

Contains all `guide_*` table data:
- 5 cities (Dubai, Istanbul, Moscow, Paris, Shanghai)
- 22 discovered zones (5 approved + active)
- 9,906 content blocks
- 19,809 edges
- 5,004+ knowledge cards
- 193 audio URLs (Moscow/Yakimanka)

## 6. Files Created/Modified

| File | Status |
|------|--------|
| `scripts/guide/generate_content.py` | NEW |
| `scripts/guide/synthesize_audio.py` | NEW |
| `tmp/guide_data_5_cities.sql` | UPDATED (17 MB) |
| `docs/live-guide/STEP15_1_UNIVERSAL_SCRIPTS_REPORT.md` | NEW |

## 7. ElevenLabs Readiness

When subscription is purchased:
1. Run `synthesize_audio.py --dry-run` for each zone to get exact char counts
2. Estimated total for 4 new cities: ~7,686 blocks × 300 chars avg = ~2.3M chars
3. Shanghai (1,434 blocks, ~430K chars) recommended as first synthesis test
4. No FFmpeg needed — just ElevenLabs API key + subscription
