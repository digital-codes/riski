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

from sqlalchemy import text

from src import remote
from src.timing import timed

_MAX_CONTENT_CHARS = 5000
# Query-guided instruction with relevance filtering: wide searches can
# deliver documents that don't actually relate to the question, so the
# model must judge each document first, summarize only the relevant ones,
# and disclose the excluded ones in a trailing note.
_SYSTEM_PROMPT = (
    "Du bist ein Assistent für das Ratsinformationssystem. Dir sind eine "
    "Frage und eine Liste von Dokumenten (als Kurzfassungen/Teaser) "
    "gegeben.\n"
    "1) Beurteile zunächst für jedes Dokument, ob es inhaltlich zur "
    "gestellten Frage beiträgt.\n"
    "2) Fasse NUR die relevanten Dokumente auf Deutsch zusammen — in "
    "Hinblick auf die Frage. Nenne die für die Frage wichtigsten "
    "Dokumente und Ergebnisse. Bleibe unter 500 Wörtern. Keine Emojis.\n"
    "3) Hänge an das Ende einen Abschnitt '**Nicht berücksichtigte "
    "Dokumente:**' an, der die Titel aller als nicht relevant "
    "eingestuften Dokumente auflistet — oder den Hinweis, dass alle "
    "Dokumente berücksichtigt wurden.\n"
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

        response = remote.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model=self.model,
            temperature=self.temperature,
        )
        summary = response.get("content", "")
        if summary and summary != "[dummy response]":
            # the summary must state the input query — prepended
            # deterministically, not left to the model
            header = f"**Frage:** {query}\n\n" if query else ""
            result["summary"] = header + summary
            print(f"\nSummary (query-guided):\n{result['summary']}")
        return result
