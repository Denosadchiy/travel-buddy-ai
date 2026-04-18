"""
Prompt builder — assembles ready-to-send prompts from templates + data objects.

All functions return a fully formatted string with no remaining {placeholders}.
Caller is responsible for passing correct types; no DB access happens here.
"""
from __future__ import annotations

from uuid import UUID

from src.guide.application.content_pipeline.prompt_templates import (
    BONUS_CONTENT_PROMPT,
    CONNECTOR_NARRATIVE_PROMPT,
    MAIN_NARRATIVE_PROMPT,
    RECAP_PROMPT,
    TRANSITION_PROMPT,
    VOICE_PERSONAS,
    WORD_COUNTS,
    ZONE_TRANSITION_PROMPT,
    _language_name,
)
from src.guide.application.content_pipeline.utils import _head, _tail

# Maximum characters per neighbour excerpt included in point_context
_NEIGHBOR_EXCERPT_MAX = 300


def build_point_context(
    point,           # GuidePoint ORM instance
    card,            # GuideKnowledgeCard ORM instance (may be None)
    zone,            # GuideZone ORM instance — must have .name, .theme, .city_name attr
    neighbor_narratives: dict[str, str],  # {point_name: narrative_excerpt}
    language: str,
) -> str:
    """
    Build the shared context block injected into all content prompts for a point.

    neighbor_narratives: mapping from neighbouring point names to a short excerpt
    of their already-generated narrative (≤ 300 chars each).  Used to tell the
    LLM what themes have been covered nearby so it can avoid repetition.
    """
    ctx_parts: list[str] = []

    ctx_parts.append(f"Place name: {point.name or 'unnamed connector point'}")

    city_name = getattr(zone, "city_name", None) or getattr(
        getattr(zone, "city", None), "name", ""
    )
    # Prefer real street/area name from knowledge card over zone label.
    # Zone names like "Red Square" are often misleading for POIs in different
    # neighborhoods of the same zone.
    area_name = None
    if card is not None and getattr(card, "street_name", None):
        area_name = card.street_name
    if area_name:
        ctx_parts.append(f"Area: {area_name}, {city_name}")
    else:
        ctx_parts.append(f"City: {city_name}")

    if card is not None:
        if card.card_type == "poi":
            if card.wikipedia_summary:
                ctx_parts.append(f"Wikipedia: {card.wikipedia_summary[:800]}")
            if card.wikidata_facts:
                facts = card.wikidata_facts
                fact_lines = []
                for k, v in facts.items():
                    if v:
                        fact_lines.append(f"  {k}: {v}")
                if fact_lines:
                    ctx_parts.append("Known facts:\n" + "\n".join(fact_lines))
            if card.google_place_data:
                summary = (
                    (card.google_place_data.get("editorial_summary") or {}).get(
                        "overview", ""
                    )
                )
                if summary:
                    ctx_parts.append(f"Google summary: {summary}")
        elif card.card_type == "street_context":
            ctx_parts.append(f"Street: {card.street_name or 'unnamed street'}")
            ctx_parts.append(
                "This is a connector point on a pedestrian path (no named POI)."
            )

    if neighbor_narratives:
        ctx_parts.append(
            "Nearby points already narrated (avoid repeating these themes):"
        )
        for neighbor_name, narrative_excerpt in neighbor_narratives.items():
            excerpt = (narrative_excerpt or "")[:_NEIGHBOR_EXCERPT_MAX]
            ctx_parts.append(f"  \u2014 {neighbor_name}: \u00ab{excerpt}...\u00bb")

    return "\n\n".join(ctx_parts)


def build_main_prompt(
    point,
    card,
    zone,
    voice,           # GuideVoice ORM instance — must have .style_group
    language: str,
    detail_level: str,
    neighbor_narratives: dict[str, str],
) -> str:
    """Build the MAIN narrative prompt for a POI point."""
    persona = VOICE_PERSONAS[voice.style_group][language]
    point_context = build_point_context(point, card, zone, neighbor_narratives, language)
    word_count = WORD_COUNTS["main"][detail_level]
    return MAIN_NARRATIVE_PROMPT.format(
        persona_description=persona,
        point_context=point_context,
        word_count=word_count,
        language_name=_language_name(language),
        style_description=voice.style_group,
    )


def build_connector_prompt(
    point,
    card,
    zone,
    voice,
    language: str,
    detail_level: str,
) -> str:
    """Build the connector-node narrative prompt (shorter, street-focused)."""
    persona = VOICE_PERSONAS[voice.style_group][language]
    point_context = build_point_context(point, card, zone, {}, language)
    word_count = WORD_COUNTS["main"][detail_level]  # connector uses same word counts as main
    return CONNECTOR_NARRATIVE_PROMPT.format(
        persona_description=persona,
        point_context=point_context,
        word_count=word_count,
        language_name=_language_name(language),
        style_description=voice.style_group,
    )


def build_bonus_prompt(
    point,
    card,
    zone,
    voice,
    language: str,
    detail_level: str,
    main_narrative_text: str,
) -> str:
    """Build the BONUS content prompt (deeper dive after main narrative)."""
    persona = VOICE_PERSONAS[voice.style_group][language]
    point_context = build_point_context(point, card, zone, {}, language)
    word_count = WORD_COUNTS["bonus"][detail_level]
    return BONUS_CONTENT_PROMPT.format(
        persona_description=persona,
        point_context=point_context,
        main_narrative_text=main_narrative_text[:400],
        word_count=word_count,
        language_name=_language_name(language),
    )


def build_transition_prompt(
    from_point,
    to_point,
    edge,            # GuideEdge ORM instance (for bearing context)
    voice,
    language: str,
    from_narrative_tail: str,
    to_narrative_head: str,
    from_themes: list[str] | None = None,
) -> str:
    """
    Build the TRANSITION prompt for an edge A→B.
    Generates 3 variants in a single LLM call.
    """
    persona = VOICE_PERSONAS[voice.style_group][language]
    themes_str = ", ".join(from_themes or []) or "—"
    return TRANSITION_PROMPT.format(
        persona_description=persona,
        from_point_name=from_point.name or "current location",
        from_themes=themes_str,
        to_point_name=to_point.name or "next location",
        from_narrative_tail=_tail(from_narrative_tail, sentences=2),
        to_narrative_head=_head(to_narrative_head, sentences=2),
        language_name=_language_name(language),
        style_description=voice.style_group,
    )


def build_zone_transition_prompt(
    from_zone,
    to_zone,
    voice,
    language: str,
) -> str:
    """Build the zone-transition prompt (crossing from one neighbourhood to another)."""
    persona = VOICE_PERSONAS[voice.style_group][language]
    return ZONE_TRANSITION_PROMPT.format(
        persona_description=persona,
        from_zone_name=from_zone.name,
        from_zone_theme=from_zone.theme or "mixed",
        to_zone_name=to_zone.name,
        to_zone_theme=to_zone.theme or "mixed",
        language_name=_language_name(language),
    )


def build_recap_prompt(
    point,
    voice,
    language: str,
    main_narrative_excerpt: str,
) -> str:
    """Build the RECAP prompt — brief re-orientation after a session pause."""
    persona = VOICE_PERSONAS[voice.style_group][language]
    return RECAP_PROMPT.format(
        persona_description=persona,
        last_point_name=point.name or "this location",
        last_narrative_excerpt=main_narrative_excerpt[:200],
        language_name=_language_name(language),
    )
