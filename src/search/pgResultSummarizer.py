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

       from src.search.pgTimeline import search_and_summarize
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
from src.search.apiTrace import trace
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
# change: centralize-llm-instruction-prompts — the instruction texts of both
# summarizer passes moved to config/instruction_prompts.json (ids:
# result-summary / result-summary-refine)
_TEASER_MAX_WORDS = 500
_REFINE_MAX_WORDS = 900


# ------------------------------------------------------------------
# PII guard (change: summary-pii-guard) — produced summaries SHALL NOT
# contain person names (user privacy rule, 2026-11-25; live finding:
# the model enumerated council members despite the prompt ban). Layers:
#   1) hardened prompts (first rule) — non-authoritative,
#   2) detection against the OParl Person vocabulary,
#   3) repair chat call, 4) deterministic fallback redaction.
# ------------------------------------------------------------------
_PII_NAME_CACHE = {"ts": 0.0, "names": None}
_PII_CACHE_TTL = 900.0
_PII_VIOLATION_MARKER = "(Name entfernt)"

# geo-name vocabulary for the street/district exemption (unified-update-
# pipeline, PII/geo interplay D12): person names that are part of an
# actual street/district compound stay visible — only the compound, never
# the bare person mention.
_GEO_NAME_CACHE = {"ts": 0.0, "names": None}

# street-typical suffixes; a compound ending in one of these is considered
# a place name even when the exact vocab entry carries different casing
_STREET_SUFFIX_RE = re.compile(
    r"(?i)(str(?:aße|asse)?\.?|weg|platz|allee|gasse|ring|damm|markt|"
    r"brücke|anlage|ufer|park|steg|pfad)$")


def _norm_geo(name: str) -> str:
    """Normalize a place-name candidate: lowercase, ß→ss, hyphens to
    spaces, collapsed whitespace."""
    return re.sub(r"\s+", " ", name.lower().replace("ß", "ss")
                  .replace("-", " ")).strip()


def _geo_names_rows():
    from src.db import get_engine
    names: list[str] = []
    with get_engine(readonly=True).connect() as c:
        for table in ("Street", "District"):
            try:
                names += [r[0] for r in c.execute(
                    text(f'SELECT name FROM "{table}"')).all() if r[0]]
            except Exception as exc:  # noqa: BLE001 - table may not exist
                log.warning("pii guard: geo table %s unavailable (%s)",
                            table, exc)
    return names


def geo_names() -> list[str]:
    """Street/District names, cached (like person_names). Fail-closed:
    on DB failure an EMPTY vocabulary is returned — the guard then keeps
    full redaction (privacy over geo answers)."""
    import time as _time
    now = _time.time()
    if _GEO_NAME_CACHE["names"] is not None and \
            now - _GEO_NAME_CACHE["ts"] < _PII_CACHE_TTL:
        return _GEO_NAME_CACHE["names"]
    try:
        rows = _geo_names_rows()
    except Exception as exc:  # noqa: BLE001 - fail closed
        log.warning("pii guard: geo vocabulary unavailable (%s) — "
                    "no street/district exemption", exc)
        rows = []
    _GEO_NAME_CACHE["names"] = [_norm_geo(n) for n in rows]
    _GEO_NAME_CACHE["ts"] = now
    return _GEO_NAME_CACHE["names"]


# compound token: word chars (incl. umlauts/ß) joined by single hyphens
_COMPOUND_TOKEN_RE = re.compile(
    r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9]*(?:-[A-Za-zÄÖÜäöüß0-9]+)*")


def _geo_exempt_spans(text: str, geo_vocab: list[str]) -> list[tuple[int, int]]:
    """Spans of street/district compounds in *text*.

    A compound token qualifies when its normalized form matches an entry
    of the geo vocabulary, or ends with a street suffix and its suffix-
    stripped normalized form matches. \"Karolinenstraße\" — the compound
    stays visible; a bare \"Karoline\" elsewhere is NOT covered."""
    by_prefix = {n.lower(): n for n in geo_vocab}
    spans = []
    for m in _COMPOUND_TOKEN_RE.finditer(text):
        token = m.group(0)
        norm = _norm_geo(token)
        if norm in by_prefix:
            spans.append((m.start(), m.end()))
            continue
        # suffix-attach: "X-Weg" / "X-Platz" where X is a vocab entry
        parts = token.split("-")
        stem = _norm_geo(parts[0]) if parts else ""
        if len(parts) >= 2 and stem in by_prefix and \
                _STREET_SUFFIX_RE.search(parts[-1]):
            spans.append((m.start(), m.end()))
    return spans


def _sub_keep_geo(text: str, name: str, replace_fn,
                  title_prefix: bool = False) -> str:
    """Substitute every occurrence of *name* EXCEPT the ones inside a
    street/district compound span (occurrence-level exemption).
    ``title_prefix`` mirrors scrub_names' original pattern (a leading
    "Dr./Prof. " is consumed together with the name)."""
    vocab = geo_names()
    spans = _geo_exempt_spans(text, vocab) if vocab else []
    title = (r"(?:(?:[Dd][Rr]|prof|ing)\.?\s*)?" if title_prefix else "")
    pattern = (r"(?i)(?<![A-Za-zÄÖÜäöüß])" + title + re.escape(name) +
               r"(?![A-Za-zÄÖÜäöüß])")

    def _sub(m):
        for s, e in spans:
            if m.start() >= s and m.end() <= e:
                return m.group(0)  # inside a compound: keep visible
        return replace_fn(m)
    return re.sub(pattern, _sub, text)


def _person_names_rows():
    from src.db import get_engine
    with get_engine(readonly=True).connect() as c:
        return [r[0] for r in c.execute(
            text('SELECT name FROM "Person"')).all() if r[0]]


def person_names() -> list[str]:
    """OParl person names, cached (full names + surnames ≥ 4 chars,
    titles excluded). Guard degradation: on DB failure the guard turns
    pass-through (fail-open documented — full redaction unavailable)."""
    import time as _time
    now = _time.time()
    if _PII_NAME_CACHE["names"] is not None and \
            now - _PII_NAME_CACHE["ts"] < _PII_CACHE_TTL:
        return _PII_NAME_CACHE["names"]
    names: set[str] = set()
    try:
        rows = _person_names_rows()
    except Exception as exc:  # pragma: no cover
        log.warning("pii guard: person vocabulary unavailable (%s)", exc)
        _PII_NAME_CACHE["names"] = []
        _PII_NAME_CACHE["ts"] = now
        return []
    for full in rows:
        full = full.strip()
        if not full:
            continue
        # titled rows ("Dr. Martina Heynen", "Prof. Dr. X", "Dr.-Ing. Y",
        # "Oberbürgermeister Z") → strip EVERY leading address/title token
        # so the vocabulary carries clean names/surnames only
        strip_re = re.compile(
            r"^(?:\s*(?:[Dd][Rr]\.|[Pp]rof\.|[Dd]r\.|[Dd]ipl\.|"
            r"[Dd]ipl\.?[Dd]-?Ing\.?|[Dd]r\.-Ing\.|[Ii]ng\.|"
            r"[Oo]berbürgermeister|Bürgermeister|Stadtrat|Stadträtin|"
            r"[Pp]räsident(?:in)?|[Mm]ayor|[Pp]rofessor))"
            r"[. ]*\s*(?:[Dd][Rr]\.?[. ]*|-[\s.]*)*")
        prev = None
        while prev != full:
            prev, full = full, (strip_re.sub("", full) or full)
            # strip repeatedly: "Prof. Dr. X" / "Dr.-Ing. Y" prefixes
        names.add(full)
        for tok in re.split(r"\s+", full):
            tok = tok.strip(".,")
            if not tok or tok.startswith(("Dr.", "Prof.")):
                continue
            if len(tok) >= 4 and tok.istitle():
                names.add(tok)
    out = sorted(names, key=len, reverse=True)
    _PII_NAME_CACHE["names"] = out
    _PII_NAME_CACHE["ts"] = now
    return out


def find_pii_violations(summary: str) -> list[str]:
    """Person-name matches in the summary text (word boundaries; full
    names take precedence — sorted longest first by :func:`person_names`)."""
    if not summary:
        return []
    low = summary.lower()
    hit: set[str] = set()
    for name in person_names():
        if re.search(r"(?i)(?<![A-Za-zÄÖÜäöüß])" + re.escape(name) +
                     r"(?![A-Za-zÄÖÜäöüß])", summary):
            hit.add(name)
            continue
        low_hits = name.lower() in low
        if low_hits and len(name) >= 8:
            # fallback for hyphenated/titled embeddings, keep exact
            hit.add(name)
    return sorted(hit, key=len, reverse=True)


def _redact_text(summary: str, violations: list[str]) -> str:
    """Deterministic fallback (task 2.3): violated tokens become
    "(Name entfernt)"; a line whose tokens are overwhelmingly person-name
    references (bare member lists like the live finding 'Fahringer /
    Dujmovic / Dr. Heynen…') collapses to that one marker.
    Occurrences inside street/district compounds are exempt (kept), and
    compound tokens do not count toward the collapse ratio."""
    vocab = geo_names()
    for name in violations:
        summary = _sub_keep_geo(
            summary, name, lambda m: _PII_VIOLATION_MARKER)
    out_lines = []
    for line in summary.splitlines():
        stripped = line.strip(" -•*0123456789. \t")
        if not stripped:
            out_lines.append(line)
            continue
        toks = [t for t in re.split(r"[^\wÄÖÜäöüß]+", stripped) if t]
        spans = _geo_exempt_spans(stripped, vocab) if vocab else []
        nameish = 0
        pos = 0
        for t in toks:
            start = stripped.find(t, pos)
            pos = start + len(t)
            in_geo = any(s <= start and start + len(t) <= e for s, e in spans)
            if not in_geo and any(t.lower() in v.lower()
                                  for v in violations):
                nameish += 1
        if toks and nameish / max(1, len(toks)) >= 0.5:
            out_lines.append("  - (Name entfernt)")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)
    out_lines = []
    for line in summary.splitlines():
        stripped = line.strip(" -•*0123456789. \t")
        if not stripped:
            out_lines.append(line)
            continue
        toks = [t for t in re.split(r"[^\wÄÖÜäöüß]+", stripped) if t]
        nameish = sum(1 for t in toks
                      if any(t.lower() in v.lower() or
                             (len(t) >= 4 and t.lower() in v.lower())
                             for v in violations))
        if toks and nameish / max(1, len(toks)) >= 0.5:
            out_lines.append("  - (Name entfernt)")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


TITLED_NAME_RE = re.compile(
    r"(?i)(?<![A-Za-zÄÖÜäöüß])(?:(?:[Dd][Rr]|prof|ing)\.?\s*|-(?:\s*))?"
    r"([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+){0,3})")


def _next_pseudonym(map_: dict[str, str], counter: list[int],
                    name: str) -> str:
    if name not in map_:
        counter[0] += 1
        map_[name] = f"[PERSON_{counter[0]}]"
    return map_[name]


class Sc:
    pass


def pii_guard(summary: str) -> str:
    """Output verification layer (architectural design): detect person
    names in the MODEL OUTPUT and redact deterministically (pseudonym or
    "(Name entfernt)") — NO repair LLM call (mistral review: prompt/LLM
    self-correction is not a reliable control; the guarantee must not
    depend on an LLM). Clean summaries pass through untouched."""
    violations = find_pii_violations(summary)
    if not violations:
        return summary
    log.info("pii guard: %d person-name match(es) in output — redacting", len(violations))
    return _redact_text(summary, violations)


def scrub_names(text: str, seat=None) -> str:
    """Context scrubbing BEFORE generation (architectural layer 1):
    person names in the document context yield pseudonyms [PERSON_n]
    (consistent per request via the summarizer's map); the model cannot
    copy a name it never sees. Occurrences inside street/district
    compounds are exempt (geo names must reach the model as-is for geo
    answers). `seat` request-pseudonym source."""
    if not text:
        return text
    _map = seat._pii_pseudonyms
    counter = [seat._pii_counter]
    out = text
    for name in person_names():
        if name and re.search(r"(?i)(?<![A-Za-zÄÖÜäöüß])" + re.escape(name) +
                              r"(?![A-Za-zÄÖÜäöüß])", out):
            out = _sub_keep_geo(
                out, name,
                lambda m, n=name: _next_pseudonym(_map, counter, n),
                title_prefix=True)
    seat._pii_counter = counter[0]
    return out


TITLED_REFERENCE = re.compile(
    r"(?i)(?<![A-Za-zÄÖÜäöüß])((?:(?:dr|prof|ing)\.?\s*)+)"
    r"(?P<name>[A-Za-zÄÖÜäöüß\- ]{3,60})")


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

    def _file_text(self, oparl_key: str, full: bool = False,
                   chunk_index: int | None = None) -> tuple[str | None, str | None]:
        """Return ``(text, downloadUrl)`` for a file.

        Context layer: with ``full=True`` the refinement reads the file's
        content layer — the MATCHED chunk when the search phase determined
        one (``chunk_index`` from the file's match metadata), otherwise the
        legacy ``content`` column, falling back to the teaser (change:
        fix-result-summarizer). With ``full=False`` the teaser layer is
        preferred, falling back to content (change:
        summary-refine-file-control).
        """
        row = self._session.execute(
            text('SELECT teaser, content, downloadurl FROM "File" WHERE "oparlKey" = :k'),
            {"k": oparl_key},
        ).first()
        if row is None:
            return None, None
        teaser, _content, download_url = row[0], row[1], row[2]
        # change: unify-file-content-in-chunks — File_chunks is the single
        # text store (chunk 0 = the complete small document); File.content
        # is retired. The teaser layer stays the first choice.
        if full:
            chosen = None
            if chunk_index:
                chosen = self._chunk_text(oparl_key, chunk_index)
            chosen = chosen or self._document_text(oparl_key) or teaser or None
        else:
            chosen = teaser or self._document_text(oparl_key) or None
        return chosen, download_url

    def _chunk_text(self, oparl_key: str, chunk_index: int) -> str | None:
        """Text of the file's matched chunk (refinement context piece),
        capped by the full-content budget; ``None`` when the chunk row is
        absent (callers fall back to the document text)."""
        row = self._session.execute(
            text('SELECT fc.text FROM "File_chunks" fc '
                 'JOIN "File" f ON f.sid = fc.file_sid '
                 'WHERE f."oparlKey" = :k AND fc.chunk_index = :i'),
            {"k": oparl_key, "i": chunk_index},
        ).first()
        if row is None or not row[0]:
            return None
        return row[0][: self.full_content_chars]

    def _document_text(self, oparl_key: str) -> str | None:
        """Complete document text from File_chunks (all chunks in order),
        capped by the full-content budget; ``None`` when absent."""
        row = self._session.execute(
            text('SELECT string_agg(fc.text, chr(10) ORDER BY fc.chunk_index) '
                 'FROM "File_chunks" fc '
                 'JOIN "File" f ON f.sid = fc.file_sid '
                 'WHERE f."oparlKey" = :k'),
            {"k": oparl_key},
        ).first()
        if row is None or not row[0]:
            return None
        return row[0][: self.full_content_chars]

    def _model_available(self) -> bool:
        return bool(remote.CHAT_BASE_URL and self.model)

    @timed
    def _grounding_blocks(self, top_files: list) -> dict[str, str]:
        """kg-app-integration: grounding blocks per file (oparlKey).

        Fetches request/response statements for the pair of the file's
        paper sid; flagged fields excluded (kgFlagFailures contract).
        Returns {oparlKey: "\nExtrahierte Fakten: …"} or empty string.
        """
        blocks: dict[str, str] = {}
        keys = [f.get("oparlKey") for f in top_files if f.get("oparlKey")]
        if not keys:
            return blocks
        try:
            from src.kg.kgQueries import statements_for_papers, file_sid_for_key
            sids = file_sid_for_key(keys)
            sids = {k: v for k, v in sids.items() if v}
            stmts = statements_for_papers(list(sids.values()))
        except Exception as exc:  # pragma: no cover
            log.warning("grounding fetch failed: %s", exc)
            return blocks
        key_to_sid = {k: v for k, v in sids.items()}
        for k in keys:
            sid = key_to_sid.get(k)
            entry = stmts.get(sid) if sid else None
            if not entry or not (entry.get("request") or entry.get("response")):
                blocks[k] = ""
                continue
            parts = []
            for stage, label in (("request", "Antrag"), ("response", "Beschluss")):
                f = entry.get(stage)
                if not f:
                    continue
                bits = []
                if f.get("topic"):
                    bits.append(f"Thema: {f['topic']}")
                if f.get("requested_action") or f.get("planned_action"):
                    bits.append("Maßnahme: " + (f.get("requested_action") or f.get("planned_action") or ""))
                if f.get("involved_cost") or f.get("expected_cost"):
                    bits.append("Kosten: " + (f.get("involved_cost") or f.get("expected_cost") or ""))
                if f.get("start_date"):
                    bits.append(f"Beginn: {f['start_date']}")
                if f.get("outcome"):
                    bits.append(f"Ergebnis: {f['outcome']}")
                if f.get("result"):
                    bits.append(f"Ergebnis: {f['result']}")
                if bits:
                    parts.append(f"{label}: " + " · ".join(bits))
            if parts:
                blocks[k] = "\nExtrahierte Fakten (kg): " + " | ".join(parts)
            else:
                blocks[k] = ""
        return blocks

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
        # PII scrubbing state (change: summary-pii-guard): consistent
        # pseudonyms per request — same person ⇒ same [PERSON_n] across the
        # whole prompt; unknown residual names in the OUTPUT are redacted
        # with the "(Name entfernt)" marker (fallback; better: covered by
        # the NER follow-up).
        self._pii_pseudonyms: dict[str, str] = {}
        self._pii_counter = 0
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
        # kg-app-integration: grounding blocks from the kg statement layer
        grounding = self._grounding_blocks(top_files)
        n_grounded = sum(1 for g in grounding.values() if g)
        # api-debug-logging: summarizer input/output sizes
        trace("summarizer", docs=len(top_files), grounded=n_grounded,
              layer=layer, full_content=use_full_content, query=query)

        # change: summary-temporal-context — the CONTEXT presents the
        # documents chronologically (oldest first; missing dates last) so
        # the model weighs recency; the file NUMBERS stay bound to the
        # user's relevance-ordered list (header carries them)
        def _date_key(f):
            return f.get("date") or "9999-12-31"
        context_rows = sorted(top_files, key=_date_key)
        for file in context_rows:
            # matched chunk from the search phase (change: content-chunking
            # + fix-result-summarizer): the refinement reads the piece of
            # the document that matched the query, not the stored head
            match = file.get("match") or {}
            text_, _url = self._file_text(file["oparlKey"], full=use_full_content,
                                          chunk_index=match.get("content_chunk"))
            f_date = file.get("date")
            f_date_str = ""
            if f_date:
                # top_files dates arrive as ISO strings (JSON) or datetimes
                d_parsed = None
                if isinstance(f_date, str):
                    import datetime as _dt
                    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            d_parsed = _dt.datetime.strptime(
                                f_date[:19], fmt)
                            break
                        except ValueError:
                            continue
                else:
                    d_parsed = f_date
                if d_parsed:
                    f_date_str = (f" ({d_parsed.day:02d}.{d_parsed.month:02d}."
                                  f"{d_parsed.year:04d})")
                else:
                    f_date_str = f" ({f_date})"
            prompt += f"\nDatei {full_index[file['oparlKey']]}{f_date_str}: {file['name']} ({file['fileName']})\n"
            if text_:
                cap = self.full_content_chars if use_full_content else self.content_chars
                prompt += f"Inhalt: {text_[:cap]}\n"
            else:
                prompt += "Inhalt: Not available\n"
            # change: summary-pii-guard — SCRUB BEFORE GENERATION
            # (architectural layer 1): person names in the context never
            # reach the model
            prompt = prompt if not text_ else scrub_names(prompt, self)
            block = grounding.get(file.get("oparlKey"))
            if block:
                prompt += scrub_names(block, self)

        if grounding and any(grounding.values()):
            grounding_note = (
                "\nFür einige Dokumente liegen Extrahierte Fakten aus "
                "Antrag und Beschluss vor (siehe 'Extrahierte Fakten'). "
                "Nutze diese geprüften Angaben bevorzugt als Beleg."
            )
        else:
            grounding_note = ""

        max_words = _REFINE_MAX_WORDS if use_full_content else _TEASER_MAX_WORDS
        # instruction parts from the shared prompt registry
        # (change: centralize-llm-instruction-prompts); ids distinguish the
        # two call paths: .1 = teaser summary, .2 = full-content refinement
        if use_full_content:
            system_prompt = remote.get_prompt("result-summary-refine")
            prompt_id = "result-summary-refine"
            call_id = "pgResultSummarizer.summarize.2"
        else:
            system_prompt = remote.get_prompt("result-summary")
            prompt_id = "result-summary"
            call_id = "pgResultSummarizer.summarize.1"
        messages = [
            {"role": "system", "content": system_prompt.format(max_words=max_words) + grounding_note},
            {"role": "user", "content": prompt},
        ]
        response = remote.chat(
            messages, model=self.model, temperature=self.temperature,
            prompt_id=prompt_id, call_id=call_id,
        )
        raw_content = response.get("content", "")
        if not raw_content or raw_content == "[dummy response]":

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
        # change: summary-pii-guard — the produced summary never renders
        # with person names: detect → deterministic fallback (architectural
        # decision: no repair LLM)
        summary = pii_guard(raw_content)
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
