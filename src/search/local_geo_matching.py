from __future__ import annotations

import re
from typing import Iterable, NamedTuple


class NameMatch(NamedTuple):
    item_id: int
    name: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start

def literal_name_spans(text: str, name: str) -> list[tuple[int, int]]:
    """Return case-insensitive literal matches with clean word-like boundaries.

    A match is rejected when the character directly before or after the literal
    name is alphanumeric or an underscore. This prevents e.g. `Weststadt` from
    matching inside `Nordweststadt`, while punctuation, spaces, quotes and
    hyphens remain valid boundaries.
    """
    if not text or not name:
        return []
    pattern = re.compile(r"(?<!\w)" + re.escape(name.strip()) + r"(?!\w)", re.IGNORECASE)
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def name_matches(text: str, name: str) -> bool:
    return bool(literal_name_spans(text, name))


def longest_non_overlapping_name_matches(
    text: str,
    items: Iterable[tuple[int, str]],
) -> list[NameMatch]:
    """Collect boundary-valid matches and suppress shorter overlapping names.

    The longest span wins. Equal-length matches are deterministic by start,
    normalized name and id. Multiple non-overlapping references remain valid.
    """
    candidates: list[NameMatch] = []
    for item_id, name in items:
        if not name:
            continue
        for start, end in literal_name_spans(text, name):
            candidates.append(NameMatch(int(item_id), str(name), start, end))

    candidates.sort(
        key=lambda m: (-m.length, m.start, m.end, m.name.casefold(), m.item_id)
    )
    accepted: list[NameMatch] = []
    for candidate in candidates:
        overlaps = any(
            candidate.start < existing.end and existing.start < candidate.end
            for existing in accepted
        )
        if not overlaps:
            accepted.append(candidate)

    accepted.sort(key=lambda m: (m.start, m.end, m.name.casefold(), m.item_id))
    return accepted


class PreparedStreetMatcher:
    """Precompiled matcher for a fixed street list.

    Alternatives are sorted longest-first. A single regex scan per AgendaItem
    replaces compiling/testing one regex per street.
    """
    def __init__(self, items: Iterable[tuple[int, str]]):
        normalized = []
        seen_names = set()
        self._id_by_name: dict[str, int] = {}
        for item_id, name in items:
            if not name:
                continue
            clean = str(name).strip()
            key = clean.casefold()
            # Street.name is expected unique; deterministic first-id fallback.
            if not clean or key in seen_names:
                continue
            seen_names.add(key)
            self._id_by_name[key] = int(item_id)
            normalized.append(clean)

        normalized.sort(key=lambda x: (-len(x), x.casefold()))
        if normalized:
            alternatives = "|".join(re.escape(name) for name in normalized)
            self._pattern = re.compile(
                r"(?<!\w)(?:" + alternatives + r")(?!\w)",
                re.IGNORECASE,
            )
        else:
            self._pattern = None

    def matches(self, text: str) -> list[NameMatch]:
        if not text or self._pattern is None:
            return []
        out = []
        for match in self._pattern.finditer(text):
            name = match.group(0)
            item_id = self._id_by_name.get(name.casefold())
            if item_id is None:
                continue
            out.append(NameMatch(item_id, name, match.start(), match.end()))
        return out


def prepare_street_matcher(items: Iterable[tuple[int, str]]) -> PreparedStreetMatcher:
    return PreparedStreetMatcher(items)
