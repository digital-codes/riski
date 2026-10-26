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

import logging
import re

from sqlalchemy import text

from src import remote
from src.timing import timed

log = logging.getLogger("riski.summarizer")

_MAX_CONTENT_CHARS = 5000
# Full-content refinement (user action): the per-file budget is a multiple
# of the teaser cap — full documents are longer, and the model context
# must stay bounded (top_k answer-set size × this budget).
_FULL_CONTENT_FACTOR = 4
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
    "Dokumente und Ergebnisse. Bleibe unter {max_words} Wörtern. Keine "
    "Emojis.\n"
    "3) Hänge an das Ende einen Abschnitt '**Nicht berücksichtigte "
    "Dokumente:**' an. Liste dort jede als nicht relevant eingestufte "
    "Datei als eigene Zeile '- Datei <Nummer>: <Titel>' auf (Nummer = "
    "Nummer aus der Dokumentenliste). Wenn alle Dokumente relevant waren, "
    "schreibe dort 'Alle Dokumente wurden berücksichtigt.'\n"
    "Antworte nur mit der Zusammenfassung (inklusive dieses Abschnitts)."
)

# Refinement prompt (user action, full content): NO document selection —
# the document set comes from the initial selection or the user's
# include/exclude toggles, so the model must read everything provided and
# deliver a concise but COMPLETE overview with per-document references
# (change: summary-refine-file-control).
_REFINE_SYSTEM_PROMPT = (
    "Du bist ein Assistent für das Ratsinformationssystem. Dir sind eine "
    "Frage und eine nummerierte Liste von Dokumenten (Volltexte) gegeben. "
    "Die Dokumentenauswahl wurde bereits getroffen — treffe KEINE eigene "
    "Auswahl und lasse KEIN Dokument aus.\n"
    " Lies alle bereitgestellten Inhalte vollständig und erstelle eine "
    "prägnante, aber VOLLSTÄNDIGE Übersicht auf Deutsch, die die Frage "
    "beantwortet: Themen, Entscheidungen, Beschlüsse, Verantwortlichkeiten "
    "und Widersprüche zwischen den Dokumenten. Belege jede Aussage mit "
    "einer Dokumentreferenz '(Datei N)'. Bleibe unter {max_words} Wörtern. "
    "Keine Emojis.\n"
    "Antworte nur mit der Übersicht."
)

_TEASER_MAX_WORDS = 500
_REFINE_MAX_WORDS = 900


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

    def __init__(self, session, model: str | None = None,
                 temperature: float = 0.1, content_chars: int = _MAX_CONTENT_CHARS) -> None:
        self._session = session
        self.model = model or remote.CHAT_MODEL
        self.temperature = temperature
        self.content_chars = content_chars

    def _file_text(self, oparl_key: str, full: bool = False) -> tuple[str | None, str | None]:
        """Return ``(text, downloadUrl)`` for a file.

        Context layer: with ``full=True`` the full ``content`` is preferred
        (capped by the full-content budget) over the teaser; otherwise the
        teaser layer is preferred, falling back to content (change:
        summary-refine-file-control).
        """
        row = self._session.execute(
            text('SELECT teaser, content, downloadurl FROM "File" WHERE "oparlKey" = :k'),
            {"k": oparl_key},
        ).first()
        if row is None:
            return None, None
        teaser, content, download_url = row[0], row[1], row[2]
        if full:
            chosen = (content[: self.full_content_chars] if content else None) or teaser or None
        else:
            chosen = teaser or content or None
        return chosen, download_url

    def _model_available(self) -> bool:
        return bool(remote.CHAT_BASE_URL and self.model)

    @timed
    def summarize(self, result: dict, force: bool = False,
                  use_full_content: bool = False, exclude: set | None = None) -> dict:
        """Populate ``result["summary"]`` in place; returns the result.

        Skips when: no top files, summary already present (unless
        *force*), or no chat model configured. A ``"[dummy response]"``
        from the client (offline fallback) is ignored.

        ``use_full_content`` (refinement runs) prefers the full document
        content over the teaser layer and names the layer in the prompt.
        ``exclude`` (oparlKeys) removes files from the working copy — the
        original ``top_files`` stay untouched in the session result.
        """
        self.full_content_chars = self.content_chars * _FULL_CONTENT_FACTOR
        self._last_refused = []
        all_files = list(result.get("top_files") or [])
        top_files = all_files
        if exclude:
            top_files = [f for f in top_files if f.get("oparlKey") not in exclude]
        result["summary_excluded"] = sorted(exclude or set())
        if not top_files:
            result["summary_files"] = self._summary_files(result.get("top_files") or [], set(), exclude,
                                                          {f["oparlKey"]: i for i, f in enumerate(result.get("top_files") or [], 1)})
            return result
        if result.get("summary") and not force:
            return result
        if not self._model_available():
            log.warning("Summary model not configured, skipping summarization")
            return result

        layer = "Volltext" if use_full_content else "Teaser"
        # stable numbering: files keep their FULL-list position so the
        # model's "(Datei N)" references always match the document list the
        # user sees (excluded positions are simply absent — renumbering the
        # working set made the references point at different documents)
        full_index = {f["oparlKey"]: i for i, f in enumerate(all_files, 1)}
        query = (result.get("query") or "").strip()
        if query:
            prompt = f"Frage: {query}\n\nDokumente ({layer}):\n"
        else:  # defensive: no query in the result — generic shape
            prompt = f"\nDokumente ({layer}):\n"
        for file in top_files:
            text_, _url = self._file_text(file["oparlKey"], full=use_full_content)
            prompt += f"\nDatei {full_index[file['oparlKey']]}: {file['name']} ({file['fileName']})\n"
            if text_:
                cap = self.full_content_chars if use_full_content else self.content_chars
                prompt += f"Inhalt: {text_[:cap]}\n"
            else:
                prompt += "Inhalt: Not available\n"

        max_words = _REFINE_MAX_WORDS if use_full_content else _TEASER_MAX_WORDS
        system_prompt = (_REFINE_SYSTEM_PROMPT if use_full_content else _SYSTEM_PROMPT)
        messages = [
            {"role": "system", "content": system_prompt.format(max_words=max_words)},
            {"role": "user", "content": prompt},
        ]
        response = remote.chat(messages, model=self.model, temperature=self.temperature)
        summary = response.get("content", "")
        if not summary or summary == "[dummy response]":
            # LLM failure on a (re)finement run: the exclusion set was
            # already recorded server-side — rebuild the document list so
            # it matches the user's selection. Previous refusal verdicts
            # are kept for everything still excluded, but a document the
            # user explicitly re-included MUST NOT stay blocked (user
            # finding: re-selecting a refused document left the map empty)
            prev_refused = result.get("summary_refused") or []
            kept_refused = [r for r in prev_refused
                            if r.get("oparlKey") in set(exclude or set())]
            result["summary_refused"] = kept_refused
            final_excluded = set(exclude or set()) | {r["oparlKey"] for r in kept_refused}
            result["summary_excluded"] = sorted(final_excluded)
            result["summary_files"] = self._summary_files(
                result.get("top_files") or [], kept_refused, final_excluded, full_index)
            log.warning("Summary LLM call failed (dummy response) — "
                        "document list rebuilt from the exclusion set")
            return result
        if summary:
            # the summary must state the input query — prepended
            # deterministically, not left to the model
            header = f"**Frage:** {query}\n\n" if query else ""
            # machine-readable relevance verdict: the Datei numbers the
            # model listed as refused, resolved back to the fetched files —
            # consumers (map view) gate on this
            refused = self._parse_refused(summary, all_files)
            # the model's note is redundant with our own document list
            # (which carries the verdict per file) — parse it, then strip
            # it from the displayed summary (change: summary-refine-file-control)
            summary = self._strip_refusal_note(summary)
            self._last_refused = refused
            user_excluded = set(exclude or set())
            if not use_full_content:
                # automatic pass: the model's refusals pre-exclude files for
                # the interactive list (refused files start excluded)
                final_excluded = user_excluded | {r["oparlKey"] for r in refused}
            else:
                # refinement: NO document selection — the refine prompt
                # reads everything and never refuses, so the "not
                # considered" set is exactly the user-excluded files (keeps
                # the map gating aligned with the visible list)
                final_excluded = user_excluded
                refused = [f for f in result.get("top_files") or []
                           if f["oparlKey"] in final_excluded]
            result["summary_excluded"] = sorted(final_excluded)
            # full-content mode marker: the frontend disables the refine
            # button once the summary is already refined
            result["summary_refined"] = use_full_content
            # provenance footer (model, endpoint, tokens, energy/emissions
            # when the endpoint reports them) — part of the summary, so it
            # is included in the PDF export. The document list is NOT part
            # of the stored summary: the frontend renders it from the
            # structured summary_files metadata (single list, no
            # duplication — change: summary-refine-file-control)
            footer = self._footer(response)
            result["summary"] = header + summary + footer
            result["summary_refused"] = refused
            # structured per-file metadata for the interactive frontend
            result["summary_files"] = self._summary_files(result.get("top_files") or [], refused, final_excluded, full_index)
            log.debug("Summary (query-guided, %s): %s", layer, result["summary"])
            if result["summary_refused"]:
                log.debug("Refused documents: %s", [r["name"] for r in result["summary_refused"]])
        return result

    def _strip_refusal_note(self, summary: str) -> str:
        """Remove the model's trailing refusal note from the summary text.

        The verdicts are carried by our own document list (berücksichtigt /
        nicht berücksichtigt per file) — the separate note is redundant and
        could contradict the list's exclusion-state verdicts. Parsing
        happens BEFORE stripping (map gating + pre-exclusion)."""
        marker = summary.find("**Nicht berücksichtigte Dokumente:**")
        if marker == -1:
            return summary.rstrip()
        return summary[:marker].rstrip()

    def _summary_files(self, top_files: list[dict], refused: list[dict],
                       excluded: set, full_index: dict) -> list[dict]:
        """Structured per-file metadata for the frontend (name, download
        URL, refused/excluded flags). ``excluded`` is the authoritative
        set state — the frontend renders the verdict from it. Download
        URLs may be missing when the DB row is absent."""
        refused_keys = {r["oparlKey"] for r in refused}
        files = []
        for f in top_files:
            _, download_url = self._file_text(f["oparlKey"])
            files.append({
                "oparlKey": f["oparlKey"],
                "index": full_index.get(f["oparlKey"]),
                "name": f.get("name"),
                "fileName": f.get("fileName"),
                "downloadUrl": download_url,
                "refused": f["oparlKey"] in refused_keys,
                "excluded": f["oparlKey"] in excluded,
                # change: agenda-sibling-documents — provenance for
                # agenda-block sibling documents (e.g. "TOP 13")
                "via": f.get("via"),
            })
        return files

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
