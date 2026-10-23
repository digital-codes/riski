"""Result summarizer (change: query-guided-summary).

Consumes a search result as produced by
``src.pgTimeline.search_and_build_timeline`` and adds a German summary
under ``result["summary"]`` — the field the web app's SummaryCard renders.

The summary is QUERY-GUIDED: the search query is part of the LLM prompt
and the model condenses the document teasers with respect to the
question, naming the key documents — not a neutral corpus summary.
Context covers ALL files the search step fetched (``top_files``), not a
subset.

Usage — two equivalent ways:

1. Class, applied to an existing search result::

       result = search_and_build_timeline(session, query)
       ResultSummarizer(session).summarize(result)

2. Convenience wrapper (search + summarize in one call)::

       from src.pgTimeline import search_and_summarize
       result = search_and_summarize(session, query)

The summarizer is intentionally a separate step: it needs the chat model,
while the search itself does not. A missing model configuration degrades
to returning the result unchanged (summary simply absent).
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import re

from sqlalchemy import text

from src import remote
from src.timing import timed

_MAX_CONTENT_CHARS = 5000
# Query-guided instruction with relevance filtering: wide searches can
# deliver documents that don't actually relate to the question, so the
# model must judge each document first, summarize only the relevant ones,
# and disclose the excluded ones in a trailing note — referencing them by
# their Datei number so the verdict is machine-parseable (the map view
# uses it to skip georeferences from refused documents).
_SYSTEM_PROMPT = (
    "Du bist ein Assistent für das Ratsinformationssystem. Dir sind eine "
    "Frage und eine nummerierte Liste von Dokumenten (als "
    "Kurzfassungen/Teaser) gegeben.\n"
    "1) Beurteile zunächst für jedes Dokument, ob es inhaltlich zur "
    "gestellten Frage beiträgt.\n"
    "2) Fasse NUR die relevanten Dokumente auf Deutsch zusammen — in "
    "Hinblick auf die Frage. Nenne die für die Frage wichtigsten "
    "Dokumente und Ergebnisse. Bleibe unter 500 Wörtern. Keine Emojis.\n"
    "3) Hänge an das Ende einen Abschnitt '**Nicht berücksichtigte "
    "Dokumente:**' an. Liste dort jede als nicht relevant eingestufte "
    "Datei als eigene Zeile '- Datei <Nummer>: <Titel>' auf (Nummer = "
    "Nummer aus der Dokumentenliste). Wenn alle Dokumente relevant waren, "
    "schreibe dort 'Alle Dokumente wurden berücksichtigt.'\n"
    "Antworte nur mit der Zusammenfassung (inklusive dieses Abschnitts)."
)


class ResultSummarizer:
    """Add a query-guided German summary to a search result.

    The LLM context uses each file's ``teaser`` (the ~1k-char compressed
    layer) when available, falling back to ``content``. Context covers
    ALL files in ``result["top_files"]`` — the answer-set size is decided
    by the search step (``top_k``), not here.
    """

    def __init__(self, session, model: str | None = None,
                 temperature: float = 0.1, content_chars: int = _MAX_CONTENT_CHARS) -> None:
        self._session = session
        self.model = model or remote.CHAT_MODEL
        self.temperature = temperature
        self.content_chars = content_chars

    def _file_text(self, oparl_key: str) -> str | None:
        """Prefer the teaser layer; fall back to content."""
        row = self._session.execute(
            text('SELECT teaser, content FROM "File" WHERE "oparlKey" = :k'),
            {"k": oparl_key},
        ).first()
        if row is None:
            return None
        return row[0] or row[1] or None

    def _model_available(self) -> bool:
        return bool(remote.CHAT_BASE_URL and self.model)

    @timed
    def summarize(self, result: dict, force: bool = False) -> dict:
        """Populate ``result["summary"]`` in place; returns the result.

        Skips when: no top files, summary already present (unless
        *force*), or no chat model configured. A ``"[dummy response]"``
        from the client (offline fallback) is ignored.
        """
        top_files = result.get("top_files") or []
        if not top_files:
            return result
        if result.get("summary") and not force:
            return result
        if not self._model_available():
            print("Summary model not configured, skipping summarization")
            return result

        query = (result.get("query") or "").strip()
        if query:
            prompt = f"Frage: {query}\n\nDokumente (Teaser):\n"
        else:  # defensive: no query in the result — generic shape
            prompt = "\nDokumente (Teaser):\n"
        for i, file in enumerate(top_files, 1):
            text_ = self._file_text(file["oparlKey"])
            prompt += f"\nDatei {i}: {file['name']} ({file['fileName']})\n"
            if text_:
                prompt += f"Inhalt: {text_[: self.content_chars]}\n"
            else:
                prompt += "Inhalt: Not available\n"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = remote.chat(messages, model=self.model, temperature=self.temperature)
        summary = response.get("content", "")
        if summary and summary != "[dummy response]":
            # the summary must state the input query — prepended
            # deterministically, not left to the model
            header = f"**Frage:** {query}\n\n" if query else ""
            # provenance footer (model, endpoint, tokens, energy/emissions
            # when the endpoint reports them) — part of the summary, so it
            # is included in the PDF export
            footer = self._footer(response)
            result["summary"] = header + summary + footer
            # machine-readable relevance verdict: the Datei numbers the
            # model listed as refused, resolved back to the fetched files —
            # consumers (map view) gate on this
            result["summary_refused"] = self._parse_refused(summary, top_files)
            print(f"\nSummary (query-guided):\n{result['summary']}")
            if result["summary_refused"]:
                print("Refused documents:", [r["name"] for r in result["summary_refused"]])
        return result

    def _parse_refused(self, summary: str, top_files: list[dict]) -> list[dict]:
        """Extract the refused documents from the trailing note.

        The note section lists lines '- Datei <Nummer>: <Titel>'. Returns
        the refused files as {'oparlKey', 'name'}; best-effort — when the
        section is absent or lists everything as considered, the result is
        an empty list (no gating).
        """
        marker = summary.find("**Nicht berücksichtigte Dokumente:**")
        if marker == -1:
            return []
        section = summary[marker:]
        refused = []
        for match in re.finditer(r"Datei\s+(\d+)", section):
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(top_files):
                f = top_files[idx]
                entry = {"oparlKey": f["oparlKey"], "name": f["name"]}
                if entry not in refused:
                    refused.append(entry)
        return refused

    def _footer(self, response: dict) -> str:
        """Markdown provenance footer: model, endpoint, token usage, and —
        when the endpoint reports them — inference time, energy and
        emissions. Empty string when nothing is available."""
        parts: list[str] = []
        model = response.get("model") or self.model
        endpoint = response.get("endpoint") or remote.CHAT_BASE_URL
        if model:
            parts.append(f"Modell: `{model}`")
        if endpoint:
            parts.append(f"Endpunkt: `{endpoint}`")

        usage = response.get("usage") or {}
        p, c, t = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")
        if t is not None:
            if p is not None and c is not None:
                parts.append(f"Tokens: {p} / {c} (Prompt / Antwort, {t} gesamt)")
            else:
                parts.append(f"Tokens: {t}")

        impact = response.get("impact") or {}
        inference = impact.get("inferenceTime") or {}
        if inference.get("total") is not None:
            parts.append(f"Inferenzzeit: {_fmt_num(inference['total'])} {inference.get('unit', 'ms')}")
        energy = impact.get("energy") or {}
        if energy.get("total") is not None:
            parts.append(f"Energie: {_fmt_num(energy['total'])} {energy.get('unit', 'Wms')}")
        emissions = impact.get("emissions") or {}
        if emissions.get("total") is not None:
            unit = {"ugCO2e": "µgCO₂e"}.get(emissions.get("unit", ""), emissions.get("unit", ""))
            parts.append(f"Emissionen: {_fmt_num(emissions['total'])} {unit}".strip())

        if not parts:
            return ""
        return "\n\n---\n\n*" + " · ".join(parts) + "*\n"


def _fmt_num(value) -> str:
    """Compact number formatting: 1234.0 → '1234', 1.5 stays '1.5'."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
