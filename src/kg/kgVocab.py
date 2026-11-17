"""Shared vocabulary loader for the kg pipeline (config/kg_vocabulary.yaml).

Provides resolution helpers that treat wording variance per design D4
(normalization layer: case, hyphen, whitespace-insensitive matching
through regex variant tables).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "kg_vocabulary.yaml",
)


@lru_cache(maxsize=None)
def _compile(pattern: str):
    import re

    return re.compile(pattern)


@lru_cache(maxsize=8)
def load_vocab(path: str | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_mapping(
    value: str | None, table: dict[str, Any]
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve *value* against a mapping table.

    Returns ``(key, entry)`` or ``(None, None)`` when nothing matches.
    Case- and whitespace-insensitive by design.
    """
    if not value:
        return None, None
    probe = value.strip()
    for key, entry in table.items():
        for pattern in entry.get("variants", []):
            if _compile(pattern).search(probe):
                return key, entry
    return None, None
