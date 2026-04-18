"""
Wikidata SPARQL client for the Live Audio Guide City Seeder — KnowledgeCollector.

Fetches a fixed set of entity properties (inception year, architect, style, etc.)
useful for LLM narrative generation (Step 7 — ContentPipeline).

SPARQL endpoint: https://query.wikidata.org/sparql
Wikidata policy requires a descriptive User-Agent header for all requests.
Configured via WIKIPEDIA_USER_AGENT setting (shared with WikipediaClient).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Wikidata property IDs → human-readable keys returned in the facts dict.
# These are the properties most useful for audio-guide narrative generation.
_PROPERTIES: dict[str, str] = {
    "P571":  "inception",           # Date founded / built
    "P84":   "architect",           # Architect(s)
    "P149":  "architectural_style", # Architectural style
    "P17":   "country",             # Country
    "P131":  "located_in",          # Located in administrative entity
    "P361":  "part_of",             # Part of (larger structure/complex)
    "P138":  "named_after",         # Named after
    "P2048": "height_m",            # Height in metres
    "P793":  "significant_event",   # Significant events
}

# SPARQL query template.
# Uses VALUES to restrict which properties are fetched (single round-trip).
# propKey is injected as a literal so the Python dict key is available in bindings.
# OPTIONAL block around label service handles typed literals (dates, quantities)
# that don't have rdfs:label — their raw string form is used instead.
_SPARQL_TEMPLATE = """\
SELECT ?propKey (STR(?val) AS ?rawVal) ?valLabel WHERE {{
  VALUES (?prop ?propKey) {{
    {prop_values}
  }}
  wd:{entity_id} ?prop ?val .
  OPTIONAL {{
    ?val rdfs:label ?valLabel .
    FILTER(LANG(?valLabel) = "{language}" || LANG(?valLabel) = "en")
  }}
}}
"""


class WikidataClient:
    """
    Fetch entity facts from Wikidata SPARQL for a given Q-ID.

    Returns a plain dict: {{ property_key: value_or_list }}.
    Properties with a single value → str.
    Properties with multiple values (e.g. multiple architects) → list[str].
    Returns {} (empty dict, not None) if the entity exists but has none of the
    tracked properties — so callers can always call .get() safely.
    Returns None on timeout or unrecoverable error.
    """

    def __init__(
        self,
        timeout_seconds: int | None = None,
        endpoint: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.wikidata_timeout_seconds
        )
        self._endpoint = endpoint or settings.wikidata_endpoint
        self._user_agent = user_agent or settings.wikipedia_user_agent

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "application/sparql-results+json",
        }

    # =========================================================================
    # Public API
    # =========================================================================

    async def fetch_entity_facts(
        self,
        entity_id: str,
        language: str = "en",
    ) -> dict[str, Any] | None:
        """
        Return a dict of facts for the given Wikidata entity ID (e.g. "Q243").

        Args:
            entity_id: Wikidata Q-ID string (e.g. "Q243" for Eiffel Tower).
                       Must start with "Q" — invalid IDs return None immediately.
            language:  Preferred label language ("en" or "ru").

        Returns:
            dict on success (may be empty if no tracked properties found),
            None on timeout / network error / invalid entity_id.
        """
        if not entity_id or not entity_id.startswith("Q"):
            logger.warning(
                "WikidataClient: invalid entity_id=%r — must start with 'Q'", entity_id
            )
            return None

        prop_values = "\n    ".join(
            f'(wdt:{pid} "{key}")'
            for pid, key in _PROPERTIES.items()
        )
        sparql = _SPARQL_TEMPLATE.format(
            prop_values=prop_values,
            entity_id=entity_id,
            language=language,
        )

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    headers=self._headers,
                    timeout=self._timeout,
                ) as client:
                    resp = await client.get(
                        self._endpoint,
                        params={"query": sparql, "format": "json"},
                    )
                    if resp.status_code in (429, 500, 502, 503, 504):
                        wait = 2 ** attempt
                        logger.warning(
                            "Wikidata SPARQL HTTP %s for entity=%s "
                            "(attempt %d/2) — retry in %ds",
                            resp.status_code, entity_id, attempt + 1, wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return self._parse_results(resp.json())
            except httpx.TimeoutException:
                logger.warning(
                    "Wikidata SPARQL timeout for entity=%s (attempt %d/2)",
                    entity_id, attempt + 1,
                )
                if attempt == 0:
                    await asyncio.sleep(2)
            except Exception as exc:
                logger.warning(
                    "WikidataClient: unexpected error for entity=%s: %s", entity_id, exc
                )
                return None

        return None

    # =========================================================================
    # Parsing
    # =========================================================================

    @staticmethod
    def _parse_results(data: dict[str, Any]) -> dict[str, Any]:
        """
        Convert SPARQL JSON bindings to a flat dict.

        Properties with multiple bindings are collected into lists.
        Date literals (xsd:dateTime) are reduced to the 4-digit year.
        Single-value lists are flattened to plain strings.
        """
        bindings = data.get("results", {}).get("bindings", [])
        facts: dict[str, list[str]] = {}

        for row in bindings:
            prop_key = row.get("propKey", {}).get("value")
            if not prop_key:
                continue

            # Prefer human-readable label; fall back to raw value string
            label = row.get("valLabel", {}).get("value")
            raw = row.get("rawVal", {}).get("value", "")

            if label:
                value = label
            elif raw:
                # Date literals like "1889-01-01T00:00:00Z" → "1889"
                value = raw[:4] if len(raw) >= 4 and raw[:4].isdigit() else raw
            else:
                continue

            if prop_key not in facts:
                facts[prop_key] = []
            if value not in facts[prop_key]:
                facts[prop_key].append(value)

        # Flatten single-value lists to plain strings
        return {
            k: v[0] if len(v) == 1 else v
            for k, v in facts.items()
        }
