"""
HEKTO chunk role classifier.

Assigns a role to each speech chunk based on keyword matching (MVP).
Roles:  analysis | expectation | doubt | hold | exit | reflection | other

After 40+ complete chains the system could switch to a learned classifier,
but this module provides the deterministic keyword-based layer that is
always available regardless of data volume.
"""

from __future__ import annotations

import logging
import re

from src.config import CHUNK_ROLE_KEYWORDS

logger = logging.getLogger(__name__)

# Valid roles (order matters: first match wins when scores are tied)
VALID_ROLES = ("exit", "doubt", "hold", "reflection", "expectation", "analysis", "other")

# ── Chain-open trigger phrases ────────────────────────────────────────────

_CHAIN_OPEN_PATTERNS: list[str] = [
    r"\bсмотрю\b",
    r"\bвижу сетап\b",
    r"\bанализирую\b",
    r"\bновый сетап\b",
    r"\bначинаю анализ\b",
]

_CHAIN_CLOSE_PATTERNS: list[str] = [
    r"\bзакрыл\b",
    r"\bвышел\b",
    r"\bстоп\b",
    r"\bтейк\b",
    r"\bзафиксировал\b",
    r"\bвсё\b",
    r"\bстоп-лосс сработал\b",
]


def classify_chunk_role(text: str) -> str:
    """
    Classify a speech chunk text into one of the defined roles.

    Uses keyword matching from CHUNK_ROLE_KEYWORDS config.
    Returns the role with the highest keyword hit count.
    If no keywords match, returns 'other'.
    """
    if not text:
        return "other"

    text_lower = text.lower()
    scores: dict[str, int] = {}

    for role, keywords in CHUNK_ROLE_KEYWORDS.items():
        count = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                count += 1
        if count > 0:
            scores[role] = count

    if not scores:
        return "other"

    # Return role with highest score; on tie, use VALID_ROLES priority order
    max_score = max(scores.values())
    for role in VALID_ROLES:
        if scores.get(role, 0) == max_score:
            return role

    return "other"


def detect_chain_open(text: str) -> bool:
    """Return True if text contains a chain-open trigger phrase."""
    if not text:
        return False
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in _CHAIN_OPEN_PATTERNS)


def detect_chain_close(text: str) -> bool:
    """Return True if text contains a chain-close trigger phrase."""
    if not text:
        return False
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in _CHAIN_CLOSE_PATTERNS)
