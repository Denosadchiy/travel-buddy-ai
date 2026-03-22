"""
Integration tests for IntentParser.

Requires: LLM provider configured in .env (IONET_API_KEY or ANTHROPIC_API_KEY).

Run:
  pytest src/hotels/tests/test_intent_parser.py -v -s --no-cov
"""
import pytest

from src.hotels.application.intent_parser import IntentParser
from src.hotels.domain.schemas import HotelSearchRequest, ParsedIntent, ScoringWeights


# ---------------------------------------------------------------------------
# Test 1: LLM path — romantic boutique request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intent_parser_romantic_boutique() -> None:
    """LLM path: romantic boutique in Paris center → correct segment + weights."""
    parser = IntentParser()
    request = HotelSearchRequest(
        city="Paris",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        user_wishes="Романтический отпуск, тихий бутиковый отель в центре, не сетевой",
    )

    intent = await parser.parse(request)

    assert isinstance(intent, ParsedIntent)
    assert isinstance(intent.scoring_weights, ScoringWeights)

    # User segment should be couple
    assert intent.user_segment == "couple", f"Expected 'couple', got {intent.user_segment!r}"

    # Weights: location + semantic_match should be prioritized for this request
    w = intent.scoring_weights
    assert w.location > 0.15, f"location weight too low: {w.location}"
    assert w.semantic_match > 0.15, f"semantic_match weight too low: {w.semantic_match}"
    assert abs(sum(w.model_dump().values()) - 1.0) < 0.02, "ScoringWeights must sum to ~1.0"

    # Dealbreakers should mention noise or chains
    deal_text = " ".join(intent.dealbreakers).lower()
    has_noise_or_chain = any(
        kw in deal_text
        for kw in ["noise", "noisy", "chain", "сеть", "шум", "corporate", "branded"]
    )
    assert has_noise_or_chain or intent.is_boutique_preferred, (
        f"Expected noise/chain dealbreaker or boutique flag. Dealbreakers: {intent.dealbreakers}"
    )

    print(f"\n✅ Intent parsed:")
    print(f"   segment={intent.user_segment}")
    print(f"   weights={{{', '.join(f'{k}={v:.2f}' for k, v in w.model_dump().items())}}}")
    print(f"   dealbreakers={intent.dealbreakers}")
    print(f"   must_have={intent.must_have}")
    print(f"   api_filters={intent.api_filters}")
    print(f"   boutique_preferred={intent.is_boutique_preferred}")


# ---------------------------------------------------------------------------
# Test 2: Deterministic path — structured fields only (no user_wishes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intent_parser_deterministic_family() -> None:
    """Deterministic path: family trip with amenity checkboxes."""
    parser = IntentParser()
    request = HotelSearchRequest(
        city="Barcelona",
        check_in="2026-08-01",
        check_out="2026-08-07",
        adults=2,
        children_ages=[5, 8],
        amenities=["facility::433", "facility::28"],  # Pool + Family rooms
        budget_max=200.0,
        free_cancellation=True,
    )

    intent = await parser.parse(request)

    assert intent.user_segment == "family"
    assert intent.children_ages == [5, 8]
    assert "facility::433" in intent.api_filters
    assert "facility::28" in intent.api_filters
    assert "free_cancellation::1" in intent.api_filters
    assert intent.price_max == 200.0

    # Default weights should sum to ~1.0
    w = intent.scoring_weights
    assert abs(sum(w.model_dump().values()) - 1.0) < 0.02

    print(f"\n✅ Deterministic intent:")
    print(f"   segment={intent.user_segment}, children={intent.children_ages}")
    print(f"   filters={intent.api_filters}")
    print(f"   price_max={intent.price_max}")


# ---------------------------------------------------------------------------
# Test 3: Solo traveler with remote work request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intent_parser_remote_work() -> None:
    """LLM path: solo remote worker → business/solo segment, facility weights high."""
    parser = IntentParser()
    request = HotelSearchRequest(
        city="Lisbon",
        check_in="2026-06-01",
        check_out="2026-06-15",
        adults=1,
        user_wishes="Need to work from the hotel. Fast WiFi is critical, need a desk. Quiet room.",
    )

    intent = await parser.parse(request)

    assert intent.user_segment in ("solo", "business")
    assert intent.is_remote_work is True

    # facility_match weight should be significant for work-focused request
    w = intent.scoring_weights
    assert w.facility_match >= 0.15, f"facility_match too low: {w.facility_match}"

    # WiFi and desk should appear in must_have or api_filters
    must_text = " ".join(intent.must_have).lower()
    filter_text = " ".join(intent.api_filters).lower()
    has_wifi = "wifi" in must_text or "107" in filter_text
    has_desk = "desk" in must_text or "23" in filter_text
    assert has_wifi or has_desk, (
        f"Expected WiFi or desk. must_have={intent.must_have}, filters={intent.api_filters}"
    )

    print(f"\n✅ Remote work intent:")
    print(f"   segment={intent.user_segment}, is_remote_work={intent.is_remote_work}")
    print(f"   must_have={intent.must_have}")
    print(f"   filters={intent.api_filters}")
