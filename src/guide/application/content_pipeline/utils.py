"""
Small helper utilities for the Content Pipeline.

Intentionally free of external dependencies — only stdlib regex.
"""
from __future__ import annotations

import re


def _split_sentences(text: str) -> list[str]:
    """
    Naive sentence splitter on .!? boundaries.
    Does not use nltk — regex is sufficient for MVP.
    Returns non-empty stripped strings.
    """
    # Split on .!? followed by whitespace or end-of-string
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _tail(text: str, sentences: int = 2) -> str:
    """Return the last N sentences of text (for transition FROM-context)."""
    if not text:
        return ""
    sents = _split_sentences(text)
    return " ".join(sents[-sentences:]) if sents else text


def _head(text: str, sentences: int = 2) -> str:
    """Return the first N sentences of text (for transition TO-context)."""
    if not text:
        return ""
    sents = _split_sentences(text)
    return " ".join(sents[:sentences]) if sents else text


def _bearing_to_description(bearing_deg: float) -> str:
    """
    Convert a bearing angle (0-360°, clockwise from north) to a compass direction name.

    Used to provide spatial context in transition prompts.
    """
    # Normalize to [0, 360)
    bearing_deg = bearing_deg % 360
    directions = [
        "north", "northeast", "east", "southeast",
        "south", "southwest", "west", "northwest",
    ]
    # Each sector is 45°, centred: N=337.5–22.5, NE=22.5–67.5, ...
    index = int((bearing_deg + 22.5) / 45) % 8
    return directions[index]
