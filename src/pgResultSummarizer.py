"""Result summarizer (change: categorization-indexing follow-up).

Consumes a search result as produced by
``src.pgTimeline.search_and_build_timeline`` and adds a German summary of
the top files' content under ``result["summary"]`` — the field the web
app's SummaryCard renders.

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
_SYSTEM_PROMPT = (
    "You are a helpful assistant that summarizes German text. "
    "Respond in German. stay below 500 words. no emojis."
)


class ResultSummarizer:
    """Add a German summary of the top files' content to a search result.

    The LLM context uses each file's ``teaser`` (the ~1k-char compressed
    layer) when available, falling back to ``content`` — an order of
    magnitude fewer input tokens than full content, so the summary call
    returns in a fraction of the time. The number of files is unaffected
    (``top``, default 5).
    """

    def __init__(self, session, top: int = 10, model: str | None = None,
                 temperature: float = 0.1, content_chars: int = _MAX_CONTENT_CHARS) -> None:
        self._session = session
        self.top = top
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

        prompt = "\nSummary of Top Files:\n"
        for i, file in enumerate(top_files[: self.top], 1):
            text_ = self._file_text(file["oparlKey"])
            prompt += f"\nFile {i}: {file['name']} ({file['fileName']})\n"
            if text_:
                prompt += f"Content: {text_[: self.content_chars]}...\n"
            else:
                prompt += "Content: Not available\n"

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
            result["summary"] = summary
            print(f"\nSummary of Top Files:\n{summary}")
        return result
