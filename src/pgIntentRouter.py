"""Intent router: decode a natural-language question into an intent and
route it to the right answer handler.

Change: intent-router. See openspec/changes/intent-router/ for the contract.

Components:
  - config loader for config/intents.yaml (shared with the decoder test
    harness in utils/test_intent_decoder_extended.py)
  - vocabulary builder: slot criteria from DB sources + hard config values,
    normalised to lowercase/trimmed matching space
  - SystemOne decision-model client (choice/noul/score question modes)
  - gremium meeting resolution ("letzter Ortschaftsrat X" -> latest held
    meeting of the org group)
  - route execution against search_and_summarize with derived filters and
    an empty-result fallback ladder
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import datetime
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import sqlalchemy as sa
import yaml
from sqlalchemy import MetaData, Table, select, text

from src.apiTrace import trace
from src.db import get_engine
# prompt registry helpers (change: centralize-llm-instruction-prompts)
from src.remote import get_prompt as _registry_get_prompt
from src.remote import log_llm_call, validate_call_ids

CONFIG_PATH = Path(__file__).parent.parent / "config" / "intents.yaml"
DEFAULT_FALLBACK_INTENT = "search_topic"
DEFAULT_THRESHOLD = 0.5
DEFAULT_SYSONE_TIMEOUT = 120.0  # slow boxes / model cold starts


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
def load_intents_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate config/intents.yaml.

    Shared by the production router and the decoder test harness. Validates
    the structural contract (unique names, descriptions, at least one
    choice per intent, exactly one fallback intent) and normalises
    utterances to lowercase.
    """
    cfg_path = path or CONFIG_PATH
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    if not cfg or "intents" not in cfg:
        raise ValueError(f"no intents defined in {cfg_path}")

    names: List[str] = []
    fallbacks: List[str] = []
    for intent in cfg["intents"]:
        for key in ("name", "description"):
            if not intent.get(key):
                raise ValueError(f"intent missing {key!r}: {intent}")
        name = intent["name"]
        if name in names:
            raise ValueError(f"duplicate intent name: {name!r}")
        names.append(name)
        if not intent.get("choices") and not intent.get("negative"):
            raise ValueError(f"intent {name!r} has no example utterances")
        if intent.get("fallback"):
            fallbacks.append(name)
        intent["choices"] = [c.lower() for c in (intent.get("choices") or [])]
        intent["negative"] = [c.lower() for c in (intent.get("negative") or [])]

    if len(fallbacks) != 1:
        raise ValueError(
            f"exactly one fallback intent required, found {fallbacks or 'none'}"
        )
    cfg["fallback_intent"] = fallbacks[0]
    return cfg


def find_intent(cfg: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for intent in cfg["intents"]:
        if intent["name"] == name:
            return intent
    return None


_NORMALIZE_RE = re.compile(r"\s+")


def normalize_value(value: str) -> str:
    """Normalise a vocabulary value or query into lowercase matching space:
    trim, collapse inner whitespace, lowercase."""
    if value is None:
        return ""
    return _NORMALIZE_RE.sub(" ", str(value).strip()).lower()


# ----------------------------------------------------------------------
# Slot vocabulary (db sources + hard values, resolved per request)
# ----------------------------------------------------------------------
def _db_source_values(conn, src: Dict[str, Any]) -> List[str]:
    spec = src.get("db") or {}
    table = spec.get("table")
    column = spec.get("column")
    if not table or not column:
        return []
    meta = MetaData()
    tbl = Table(table, meta, autoload_with=conn)
    col = getattr(tbl.c, column)
    stmt = select(col)
    if spec.get("distinct"):
        stmt = stmt.distinct()
    where_regex = spec.get("where_regex")
    if where_regex:
        stmt = stmt.where(col.op("~")(where_regex))
    if hasattr(tbl.c, "classification") and spec.get("classification"):
        stmt = stmt.where(tbl.c.classification == spec["classification"])
    stmt = stmt.where(col.isnot(None)).order_by(col)
    values: List[str] = []
    for (raw,) in conn.execute(stmt):
        norm = spec.get("normalize")
        if norm == "canonical_document_type":
            from src.pgCategorise import canonicalize_document_type

            raw, _code = canonicalize_document_type(raw)
        if raw:
            values.append(str(raw))
    return values


def build_slot_vocab(conn, intent: Dict[str, Any], slot_name: str) -> List[str]:
    """Resolve a slot's value sources (db + hard) to a normalised,
    de-duplicated lowercase criteria list."""
    slot = (intent.get("slots") or {}).get(slot_name) or {}
    values: List[str] = []
    seen = set()
    for src in slot.get("sources", []) or []:
        raw_values: List[str] = []
        if "hard" in src:
            raw_values.extend(src["hard"])
        if "db" in src:
            raw_values.extend(_db_source_values(conn, src))
        for raw in raw_values:
            norm = normalize_value(raw)
            if norm and norm not in seen:
                seen.add(norm)
                values.append(norm)
    return values


# ----------------------------------------------------------------------
# SystemOne decision-model client
# ----------------------------------------------------------------------
class DecoderError(RuntimeError):
    pass


def build_questions(cfg: Dict[str, Any], gremium_vocab: List[str]) -> Dict[str, Any]:
    """One SystemOne payload section: one noul question per intent plus a
    choice question for the gremium slot.

    Note: score questions accept at most 10 criteria levels (SystemOne
    protocol), so slots with larger vocabularies use choice."""
    questions: Dict[str, Any] = {}
    for intent in cfg["intents"]:
        questions[intent["name"]] = {
            "type": "noul",
            # instruction part from the shared prompt registry
            # (change: centralize-llm-instruction-prompts)
            "instructions": (
                _registry_get_prompt("intent-decision-question").format(
                    intent_name=intent["name"],
                    intent_description=intent["description"],
                )
            ),
            "criteria": {"true": "Ja, passt", "false": "Nein, passt nicht"},
        }
    if gremium_vocab:
        questions["slot_gremium"] = {
            "type": "choice",
            "instructions": (
                _registry_get_prompt("intent-gremium-slot-question")
            ),
            "criteria": {v: f"Gremium {v}" for v in gremium_vocab},
        }
    return questions


def parse_answers(cfg: Dict[str, Any], answers: Dict[str, Any],
                  gremium_vocab: List[str]) -> Dict[str, Any]:
    """Map SystemOne answers to {intent, scores, slots}.

    noul mode with per-intent thresholds; no intent at/above threshold
    falls back to the configured fallback intent."""
    scores: Dict[str, float] = {}
    for intent in cfg["intents"]:
        raw = answers.get(intent["name"], {})
        score = raw.get("noul", 0) if isinstance(raw, dict) else 0
        try:
            scores[intent["name"]] = float(score)
        except (TypeError, ValueError):
            scores[intent["name"]] = 0.0

    best_name, best_score = None, -1.0
    for intent in cfg["intents"]:
        threshold = float(intent.get("threshold", DEFAULT_THRESHOLD))
        score = scores[intent["name"]]
        if score >= threshold and score > best_score:
            best_name, best_score = intent["name"], score

    fallback = cfg["fallback_intent"]
    if best_name is None:
        best_name = fallback

    slots: Dict[str, Any] = {}
    if gremium_vocab:
        raw = answers.get("slot_gremium", {})
        choice = raw.get("choice") if isinstance(raw, dict) else None
        if choice:
            choice_norm = normalize_value(choice)
            if choice_norm in gremium_vocab:
                slots["gremium"] = choice_norm

    return {"intent": best_name, "scores": scores, "slots": slots}


class SystemOneDecoder:
    """Thin sync client for the SystemOne decision-model endpoint.

    Timeout (seconds) resolution: explicit argument > env ``SYSONE_TIMEOUT``
    > ``private.py`` ``SYSONE_TIMEOUT`` > default. The default is generous
    because small decision models on slow boxes (or first-load model
    startup) can take a while; a connect timeout bounds the wait when the
    endpoint is simply down. On timeout the client is closed cleanly so no
    half-open connection lingers."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None,
                 key: Optional[str] = None, timeout: Optional[float] = None):
        import os

        import src.private as pr

        self.url = url or getattr(pr, "SYSONE_URL", None)
        self.model = model or getattr(pr, "SYSONE_MDL", None)
        self.key = key or getattr(pr, "SYSONE_KEY", None)
        if timeout is not None:
            self.timeout = timeout
        else:
            env_timeout = os.getenv("SYSONE_TIMEOUT")
            if env_timeout:
                try:
                    self.timeout = float(env_timeout)
                except ValueError:
                    self.timeout = DEFAULT_SYSONE_TIMEOUT
            else:
                self.timeout = float(
                    getattr(pr, "SYSONE_TIMEOUT", DEFAULT_SYSONE_TIMEOUT)
                )
        if not self.url or not self.model:
            raise DecoderError("SYSONE_URL / SYSONE_MDL not configured")

    def decode(self, query: str, cfg: Dict[str, Any],
               gremium_vocab: List[str],
               prompt_id: Optional[str] = None,
               call_id: Optional[str] = None) -> Dict[str, Any]:
        """One round-trip: intent (noul per intent) + slot questions.

        Uses an explicit client so the connection (and its pool) is closed
        deterministically — including on timeout — instead of leaving the
        request dangling. Identified like every prompt-bearing call
        (change: centralize-llm-instruction-prompts): the ids are validated
        per the registry policy and the request/answers go to
        ``log/llm_debug.log``."""
        prompt_id, call_id = validate_call_ids(
            prompt_id, call_id, context="pgIntentRouter.SystemOneDecoder.decode",
        )
        payload = {
            "model": self.model,
            "state": normalize_value(query),
            "questions": build_questions(cfg, gremium_vocab),
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        timeout = httpx.Timeout(self.timeout, connect=min(15.0, self.timeout))
        import time as _time

        t0 = _time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        answers = data.get("answers", {})
        log_llm_call(
            endpoint=self.url, model=self.model, payload=payload, result=answers,
            prompt_id=prompt_id, call_id=call_id,
            duration_ms=round((_time.perf_counter() - t0) * 1000, 1),
        )
        return parse_answers(cfg, answers, gremium_vocab)


# ----------------------------------------------------------------------
# Gremium resolution (org groups + latest held meeting)
# ----------------------------------------------------------------------
def resolve_gremium(session, term: Optional[str],
                    groups: List[Dict[str, Any]],
                    month: Optional[int] = None,
                    year: Optional[int] = None) -> Dict[str, Any]:
    """Resolve a gremium term to organizations and the target meeting.

    Org groups (config) merge one-off sub-orgs into their parent at
    resolve time. With ``month``/``year`` (change:
    fix-gremium-session-docs-thread, task 2.2) the meeting is filtered to
    that month/year. Returns {orgs, meeting, note, empty, months_with_docs?}.
    """
    out: Dict[str, Any] = {"orgs": [], "meeting": None, "note": ""}
    norm_term = normalize_value(term) if term else ""
    if not norm_term:
        out["note"] = "kein Gremium in der Anfrage erkannt"
        return out

    meta = MetaData()
    org = Table("Organization", meta, autoload_with=session.bind)

    # exact/substring match against primary names and group members
    matched_group = None
    for group in groups or []:
        names = [group.get("primary", "")] + list(group.get("merged", []) or [])
        for name in names:
            if norm_term == normalize_value(name) or norm_term in normalize_value(name):
                matched_group = names
                break
        if matched_group:
            break

    if matched_group:
        rows = session.execute(
            select(org.c.name).where(
                org.c.name.in_(matched_group),
                org.c.enddate.is_(None) | (org.c.enddate >= datetime.datetime.now()),
            )
        ).scalars().all()
        out["orgs"] = list(rows)
    else:
        # exact normalized match first, then substring fallback
        rows = session.execute(
            select(org.c.name).where(
                sa.func.lower(org.c.name) == norm_term
            )
        ).scalars().all()
        if not rows:
            like = f"%{norm_term}%"
            rows = session.execute(
                select(org.c.name).where(org.c.name.ilike(like)).limit(10)
            ).scalars().all()
        out["orgs"] = list(rows)
        if len(rows) > 1:
            out["note"] = (
                f"mehrere Gremien passend zu '{term}' gefunden; "
                "Suche ueber alle Treffer"
            )

    if not out["orgs"]:
        out["note"] = f"kein Gremium zu '{term}' gefunden"
        return out

    meeting = _resolve_meeting(session, out["orgs"], month=month, year=year)
    out.update(meeting)
    return out


# German months for the meeting-date filter (change:
# fix-gremium-session-docs-thread, task 2.1): month name with optional
# 4-digit year selects the target session; no year ⇒ current year.
_MONTHS_DE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
    "jan": 1, "mrz": 3, "feb": 2, "merz": 3, "okt": 10, "dez": 12,
}
_MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS_DE, key=len, reverse=True)) +
    r")\s*(\d{4})?\b", re.IGNORECASE)


def extract_meeting_date(query: str) -> Tuple[Optional[int], Optional[int]]:
    """(month, year) from the raw query, or (None, None). Month names with
    an optional year ("im September 2025"); a month without a year defaults
    to the CURRENT year (task 2.1). The first month mention wins."""
    m = _MONTH_RE.search(query or "")
    if not m:
        return (None, None)
    month = _MONTHS_DE[m.group(1).lower()]
    year = int(m.group(2)) if m.group(2) else datetime.datetime.now().year
    return (month, year)


def gremium_meeting_extract(query: str,
                            gremium_term: Optional[str] = None) -> Tuple[
        Optional[int], Optional[int]]:
    """LLM extraction of the meeting date frame (change:
    fix-gremium-session-docs-thread, task 7.2): strict-JSON
    `{gremium, relative, month, year}` via the SUMMARY chat client with the
    `gremium-meeting-extract` prompts. Returns (month, year) like
    :func:`extract_meeting_date` — that regex path is the FALLBACK on any
    failure/unparseable answer/ambiguous `relative` (the decoder already
    took care of the gremium kind; "letzte" needs no date). 0 fields mean
    "not given" ⇒ None like the regex path."""
    from src import remote as _remote
    vocab = (gremium_term or "").strip() or "(Gremium im Text)"
    try:
        system = _remote.get_prompt("gremium-meeting-extract")
        user = _remote.get_prompt("gremium-meeting-extract-user")
        resp = _remote.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": user.replace(
                 "{query}", query).replace("{vocabulary}", vocab)}],
            temperature=0.0,
            prompt_id="gremium-meeting-extract",
            call_id="pgIntentRouter.gremium_meeting_extract.1",
        )
        import json as _json
        import re as _re
        content = resp.get("content") or ""
        m = _re.search(r"\{.*\}", content, _re.DOTALL)
        if not m:
            return (None, None)
        data = _json.loads(m.group(0))
        rel = str(data.get("relative") or "").lower()
        month = int(data.get("month") or 0)
        year = int(data.get("year") or 0)
        if rel == "letzte" or (month == 0 and year == 0):
            return (None, None)
        if not (1 <= month <= 12):
            return (None, None)
        return (month, year or datetime.datetime.now().year)
    except Exception as exc:  # pragma: no cover
        trace("gremium_extract", step="llm_failed", error=str(exc)[:120])
        return (None, None)


def _has_documents(session, meeting_sid) -> bool:
    """True when a meeting row carries agenda items or meeting files."""
    r = session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM \"AgendaItem\" WHERE \"meetingSid\" = :s)"
            " OR EXISTS (SELECT 1 FROM \"File__meeting__Meeting\""
            "  WHERE \"tgtSid\" = :s OR \"srcSid\" = :s)"
        ),
        {"s": meeting_sid},
    ).scalar()
    return bool(r)


# how many document-less held meeting rows to skip before giving up
# (change: fix-gremium-session-docs-thread, task 1.1)
MAX_EMPTY_SKIP = 3


def _resolve_meeting(session, orgs: List[str], month: Optional[int] = None,
                     year: Optional[int] = None) -> Dict[str, Any]:
    """Pick the meeting for the gremium scope (tasks 1.1/2.2).

    With month=None: the latest held meeting that carries documents — the
    OParl backend publishes the meeting rows long before the documents, so
    the empty latest rows are skipped (bounded by ``MAX_EMPTY_SKIP``; each
    skipped date goes into the note). With month/year: the latest held
    meeting with documents in that month — none found means an explicit
    empty response (``empty=True``, months that DO have documents are
    named) and never a silent fallback to another month.
    """
    out: Dict[str, Any] = {"meeting": None, "note": "", "empty": False}
    meta = MetaData()
    meeting = Table("Meeting", meta, autoload_with=session.bind)
    morg = Table("Meeting__organization__Organization", meta,
                 autoload_with=session.bind)
    org = Table("Organization", meta, autoload_with=session.bind)
    now = datetime.datetime.now()

    rows = session.execute(
        select(meeting.c.sid, meeting.c.name, meeting.c.start_date,
               meeting.c.oparlKey)
        .select_from(morg.join(meeting, morg.c.srcSid == meeting.c.sid))
        .where(
            morg.c.tgtSid.in_(
                select(org.c.sid).where(
                    sa.func.lower(org.c.name).in_([o.lower() for o in orgs])
                ).scalar_subquery()
            ),
            meeting.c.start_date <= now,
        )
        .order_by(meeting.c.start_date.desc())
        .limit(400)
    ).all()

    if month is None:
        skipped: List[str] = []
        for sid_, name_, date_, key_ in rows:
            if _has_documents(session, sid_):
                out["meeting"] = {"sid": sid_, "name": name_,
                                  "start_date": date_, "oparlKey": key_}
                if skipped:
                    fmt = ", ".join(d.strftime("%d.%m.%Y") for d in skipped)
                    out["note"] = (
                        "Dokumente für die Sitzung(en) am " + fmt +
                        " sind noch nicht veröffentlicht — zuletzt mit "
                        "Dokumenten: " + date_.strftime("%d.%m.%Y"))
                return out
            skipped.append(date_)
            if len(skipped) > MAX_EMPTY_SKIP:
                break
        out["note"] = ("keine Sitzungsdokumente des Gremiums gefunden"
                       + (" (letzte Sitzung: "
                          + skipped[0].strftime("%d.%m.%Y") + ")"
                          if skipped else ""))
        return out

    # month filter (task 2.2): meetings in that month/year only
    mrows = [r for r in rows
             if r[2].month == month and (year is None or r[2].year == year)]
    for sid_, name_, date_, key_ in mrows:
        if _has_documents(session, sid_):
            out["meeting"] = {"sid": sid_, "name": name_,
                              "start_date": date_, "oparlKey": key_}
            return out
    # explicit empty: state the months that DO have documents nearby
    near = sorted({f"{r[2].month}/{r[2].year}" for r in rows
                   if _has_documents(session, r[0])},
                  key=lambda k: (-int(k.split('/')[1]), -int(k.split('/')[0])))
    out["empty"] = True
    out["note"] = (
        f"Für {orgs[0] if orgs else 'das Gremium'} liegen für "
        f"{month:d}/{year or 'die aktuelle Jahreszeit'} keine Sitzungs-"
        "unterlagen vor")
    if near:
        out["note"] += " — Monate mit Dokumenten: " + ", ".join(near[:4])
    return out



# ----------------------------------------------------------------------
# Location resolution (change: add-location-intent)
# ----------------------------------------------------------------------
DEFAULT_LOCATION_THRESHOLD = 0.5
DEFAULT_SUFFIX_THRESHOLD = 0.4
DEFAULT_AMBIGUITY_DELTA = 0.1
DEFAULT_LOCATION_SUFFIXES = [
    "strasse", "straße", "platz", "weg", "allee", "gasse", "ring", "ufer",
    "markt", "damm", "bruecke", "brücke", "tunnel", "kai", "berg", "tal",
    "steige", "wall", "insel", "feld", "wald", "acker", "hof",
]


def _location_slot_spec(intent: Dict[str, Any]) -> Dict[str, Any]:
    """The location slot's trigram source spec (tables/column/thresholds)."""
    slot = (intent.get("slots") or {}).get("location") or {}
    for src in slot.get("sources") or []:
        if "trigram" in src:
            return src["trigram"] or {}
    return {}


def _query_has_suffix(norm_query: str, suffixes: List[str]) -> bool:
    """True when the normalized query contains a location suffix as a word."""
    for suf in suffixes or []:
        if re.search(r"\b\w*" + re.escape(suf) + r"\b", norm_query):
            return True
    return False


def resolve_location(session, query: str,
                     intent: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve place references in the query against the location vocabulary
    (streets, districts) via trigram word similarity — typo-tolerant, no
    tokenization: the full normalized query is compared against each name.

    Config lives on the intent's ``location`` slot (``trigram`` source):
    tables, column, threshold, suffix_threshold, suffixes, ambiguity_delta,
    top_k. The suffix list only lowers the acceptance threshold — a query is
    never rejected for lacking one.

    Returns {locations, alternates, note, threshold}; ``locations`` holds
    every vocabulary row matching the best name (a street and a district may
    share a name), ``alternates`` the runner-ups within the ambiguity delta.
    """
    spec = _location_slot_spec(intent)
    tables = spec.get("tables") or ["Street", "District"]
    column = spec.get("column") or "name"
    suffixes = spec.get("suffixes") or DEFAULT_LOCATION_SUFFIXES
    threshold = float(spec.get("threshold", DEFAULT_LOCATION_THRESHOLD))
    suffix_threshold = float(spec.get("suffix_threshold", DEFAULT_SUFFIX_THRESHOLD))
    delta = float(spec.get("ambiguity_delta", DEFAULT_AMBIGUITY_DELTA))
    limit = int(spec.get("top_k", 5))

    norm_query = normalize_value(query)
    out = {"locations": [], "alternates": [], "note": "", "threshold": threshold}
    if not norm_query:
        out["note"] = "kein Ort in der Anfrage erkannt"
        return out

    used = suffix_threshold if _query_has_suffix(norm_query, suffixes) else threshold
    out["threshold"] = used

    meta = MetaData()
    rows: List[Dict[str, Any]] = []
    for tname in tables:
        tbl = Table(tname, meta, autoload_with=session.bind)
        col = getattr(tbl.c, column)
        sim = sa.func.word_similarity(sa.func.lower(col), norm_query).label("sim")
        stmt = (
            select(tbl.c.id, col, sim)
            .where(sim > used)
            .order_by(sa.desc("sim"), sa.asc(tbl.c.id))
            .limit(limit)
        )
        for rid, name, s in session.execute(stmt):
            rows.append({
                "type": tname.lower(), "id": rid, "name": name,
                "score": round(float(s), 4),
            })

    if not rows:
        out["note"] = "kein Ort in der Anfrage erkannt"
        return out

    rows.sort(key=lambda r: (-r["score"], r["name"]))
    best = rows[0]
    best_name = normalize_value(best["name"])
    out["locations"] = [r for r in rows if normalize_value(r["name"]) == best_name]
    out["alternates"] = [
        r for r in rows
        if normalize_value(r["name"]) != best_name
        and r["score"] >= best["score"] - delta
    ]
    if out["alternates"]:
        names = ", ".join(a["name"] for a in out["alternates"])
        out["note"] = (
            f"mehrere Orte passend zu '{query}' gefunden; "
            f"'{best['name']}' verwendet (auch gefunden: {names})"
        )
    return out


def _future_meeting_file_keys(session) -> set:
    """oparlKeys of files that are ONLY linked to meetings in the future."""
    meta = MetaData()
    file_tbl = Table("File", meta, autoload_with=session.bind)
    fm = Table("File__meeting__Meeting", meta, autoload_with=session.bind)
    meeting = Table("Meeting", meta, autoload_with=session.bind)
    past_linked = (
        select(fm.c.srcSid)
        .select_from(fm.join(meeting, fm.c.tgtSid == meeting.c.sid))
        .where(meeting.c.start_date <= datetime.datetime.now())
    )
    stmt = (
        select(file_tbl.c.oparlKey)
        .select_from(
            file_tbl.join(fm, fm.c.srcSid == file_tbl.c.sid)
            .join(meeting, fm.c.tgtSid == meeting.c.sid)
        )
        .where(meeting.c.start_date > datetime.datetime.now())
        .except_(
            select(file_tbl.c.oparlKey).where(file_tbl.c.sid.in_(past_linked))
        )
    )
    return {r[0] for r in session.execute(stmt)}


def drop_future_meeting_files(session, result: Dict[str, Any],
                              notes: List[str]) -> Dict[str, Any]:
    """Decision-scope guard: remove top_files that link exclusively to
    future meetings (documents published ahead of a session are not
    decisions). No-op guard for the common case."""
    top = result.get("top_files") or []
    if not top:
        return result
    future_keys = _future_meeting_file_keys(session)
    if not future_keys:
        return result
    kept = []
    for f in top:
        if f.get("oparlKey") in future_keys:
            continue
        kept.append(f)
    if len(kept) != len(top):
        notes.append(
            f"{len(top) - len(kept)} Dokument(e) vor kuenftigen Sitzungen "
            "ausgeschlossen (keine Beschluesse)"
        )
    result["top_files"] = kept
    return result


# ----------------------------------------------------------------------
# Meeting-centric gremium answers (design D10)
# ----------------------------------------------------------------------
def _merge_graph_partials(partials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge additive graph partials by node id / edge triple (same merge
    semantics the frontend applies for /expand)."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[tuple, Dict[str, Any]] = {}
    for p in partials or []:
        for n in p.get("nodes", []) or []:
            if n["id"] not in nodes:
                nodes[n["id"]] = n
        for e in p.get("edges", []) or []:
            key = (e["source"], e["target"], e["relation"])
            edges.setdefault(key, e)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def _is_tagesordnung(node: Dict[str, Any]) -> bool:
    name = (node.get("name") or "").lower()
    return "tagesordnung" in name


def meeting_scope_result(session, query: str, resolved: Dict[str, Any],
                         limit_per_relation: int = 50,
                         top_k: int = 10) -> Dict[str, Any]:
    """Meeting-centric answer for gremium questions (design D10, rewritten
    by change: fix-gremium-session-docs-thread task 8.1).

    Aggregates topics/files via DIRECT database queries (AgendaItem rows of
    the resolved meeting + assoc tables) — NO graph build or expansion (a
    gremium session view carries no graph). Tagesordnung + meeting files
    first, then the TOPs' documents as top_files (no top_k cut — the
    session IS the answer). No LLM summary, no map
    (answer_mode: list_topics)."""
    notes: List[str] = list(resolved.get("notes") or [])
    grem = resolved.get("gremium") or {}
    meeting = grem.get("meeting") or {}
    graph = {"nodes": [], "edges": []}
    top_files: List[Dict[str, Any]] = []
    topics: List[Dict[str, Any]] = []

    if not meeting.get("oparlKey"):
        # resolution notes carry the precise cause (month filter empty /
        # document-less meetings) — do not repeat it
        if not any("Sitzung" in n for n in notes):
            notes.append("keine abgehaltene Sitzung gefunden; Suche ohne Sitzungs-Scope")
        return {
            "query": query, "graph": graph, "top_files": top_files,
            "topics": topics, "answer_mode": "list_topics", "notes": notes,
            "empty": True,
        }

    meeting_sid = meeting.get("sid")
    import sqlalchemy as sa

    def _file_row(r) -> Dict[str, Any]:
        return {
            "id": f"File_{r.sid}", "oparlKey": r.oparlKey, "name": r.name,
            "date": r.date, "downloadurl": r.downloadurl or r.oparlId,
            "oparlId": r.oparlId,
        }

    def _assoc_files(assoc: str, node_col: str, node_sid,
                     file_col: str = "tgtSid") -> List[Any]:
        """Files of an association row. The File side column is explicit
        (no universal orientation): per graphModel.ADJACENCY, verified live
        — aux assocs put the file on tgtSid, File__paper__Paper on srcSid."""
        return session.execute(sa.text(
            'SELECT f.sid, f."oparlKey", f.name, f.date, '
            "f.data->>'downloadurl' AS downloadurl, f.\"oparlId\" "
            f'FROM "{assoc}" x JOIN "File" f ON f.sid = x."{file_col}" '
            f'WHERE x."{node_col}" = :k'), {"k": node_sid}).all()

    def _files_for_paper(paper_sid) -> List[Dict[str, Any]]:
        # File__paper__Paper: src = File, tgt = Paper
        return [_file_row(r) for r in _assoc_files(
            "File__paper__Paper", "tgtSid", paper_sid, file_col="srcSid")]

    def _files_ai(ai_sid, cons_sid) -> List[Dict[str, Any]]:
        """Files of a TOP: direct aux files + consultation → paper →
        main/aux files."""
        out: List[Dict[str, Any]] = []
        seen: set = set()

        def _feed(fs):
            for f in fs:
                if f["id"] not in seen:
                    seen.add(f["id"])
                    out.append(f)
        _feed([_file_row(r) for r in _assoc_files(
            "AgendaItem__auxiliaryFile__File", "srcSid", ai_sid)])
        if cons_sid:
            paper_sids = session.execute(sa.text(
                'SELECT "srcSid" FROM "Paper__consultation__Consultation" '
                'WHERE "tgtSid" = :k'), {"k": cons_sid}).scalars().all()
            for psid in paper_sids:
                _feed(_files_for_paper(psid))
                _feed([_file_row(r) for r in _assoc_files(
                    "Paper__auxiliaryFile__File", "srcSid", psid)])
        return out

    agenda = session.execute(sa.text(
        'SELECT sid, "oparlKey", name, number, result, "consultationSid" '
        'FROM "AgendaItem" WHERE "meetingSid" = :sid ORDER BY number'),
        {"sid": meeting_sid}).mappings().all()

    agenda_file_ids: List[Dict[str, Any]] = []
    seen_agenda_files: set = set()
    for a in agenda:
        files = _files_ai(a["sid"], a.get("consultationSid"))
        topics.append({
            "id": f"AgendaItem_{a['oparlKey']}",
            "oparlKey": a["oparlKey"], "number": a["number"],
            "name": a["name"], "result": a["result"],
            "date": meeting.get("start_date"),
            "orgs": grem.get("orgs") or [],
            "files": files,
        })
        for f in files:
            if f["id"] not in seen_agenda_files:
                seen_agenda_files.add(f["id"])
                agenda_file_ids.append(f)

    # top_files: Tagesordnung first, then the other meeting files, then the
    # TOPs' documents (dedup, agenda-first order)
    meeting_files: List[Dict[str, Any]] = []
    mf_seen: set = set()
    for stmt, file_col in (
        ('SELECT f.sid, f."oparlKey", f.name, f.date, '
         "f.data->>'downloadurl' AS downloadurl, f.\"oparlId\" "
         'FROM "File__meeting__Meeting" x JOIN "File" f ON f.sid = x."tgtSid" '
         'WHERE x."srcSid" = :sid', "meeting"),
    ):
        for r in session.execute(sa.text(stmt), {"sid": meeting_sid}).all():
            key = r.sid or r.oparlKey
            if key in mf_seen:
                continue
            mf_seen.add(key)
            meeting_files.append(_file_row(r))
    meeting_files.sort(key=lambda f: not _is_tagesordnung({"name": f["name"] or ""}))

    ordered: List[Dict[str, Any]] = list(meeting_files)
    ordered_ids = {f["id"] for f in ordered}
    for f in agenda_file_ids:
        if f["id"] in ordered_ids:
            continue
        ordered_ids.add(f["id"])
        ordered.append(f)

    top_files = [
        {
            "oparlKey": f.get("oparlKey"), "name": f.get("name"),
            "fileName": None, "downloadurl": f.get("downloadurl"),
            "oparlId": f.get("oparlId"), "date": f.get("date"),
            "distance": None, "match": {},
        }
        for f in ordered
    ]

    if not top_files:
        notes.append("keine Sitzungsdokumente gefunden")
    return {
        "query": query, "graph": graph, "top_files": top_files,
        "topics": topics, "answer_mode": "list_topics", "notes": notes,
        "empty": not (top_files or topics),
    }



# ----------------------------------------------------------------------
# kg-app-integration D7: thread-turn classification
# ----------------------------------------------------------------------
DEICTIC_MARKERS = (
    "das", "die", "es", "sie", "dem", "denen", "dort", "damit", "dabei",
    "hier", "dazu", "danach", "davon", "dieser", "diese", "dieses",
)
# pronoun-initial sentence heads are the strongest anaphora sign
DEICTIC_HEADS = ("das ", "die_li;", "dem ", "es ", "damit ", "dort ",
                 "dazu ", "davon ")


PROFORM_TOKENS = {"das", "dem", "es", "dort", "damit", "dabei", "dazu",
                  "darauf", "davon", "daraus", "dafür", "dagegen",
                  "darüber", "hierzu", "hierdurch"}


def _is_deictic(raw_query: str) -> bool:
    """Anaphora evidence on the RAW query (task 7.2): a proform counts
    when it is either (a) the last word of the query — "…hat das" — or
    (b) followed by a lowercase continuation word (usually the verb),
    NOT by a Capitalized noun ("das Forum" = determiner, not proform)."""
    words = raw_query.strip().split()
    if not words:
        return False
    if words[-1].lower().rstrip(",.!?:;") in PROFORM_TOKENS:
        return True
    for i, w in enumerate(words[:-1]):
        if w.lower().rstrip(",.!?:;") in PROFORM_TOKENS:
            nxt = words[i + 1]
            # determiner+noun continues ". …das Forum…"; proform continues
            # with a verb/proform continuation ("dem zugestimmt")
            if nxt[0].islower():
                return True
    return False


def classify_thread_turn(query: str, intent_name: str,
                         intent_scores: dict | None = None,
                         topic_focus: str | None = None, *,
                         recall_confident: bool = True) -> dict[str, Any]:
    """Deterministic followup-vs-break decision (design D7, task 7.2).

    ``thread_followup`` when the query has no clear target of its own.
    Primary signal: anaphoric proform usage on the raw query ("welche
    umweltauswirkungen hat das", "warum haben die grünen dem
    zugestimmt" — proform as clause-final or with a lowercase verb
    continuation; "das Forum" with a following capitalized noun is a
    determiner, not anaphora). Secondary: no topic-vector fire AND
    router confidence below threshold. Non-thematic intents
    (gremium/decision lookups) always break.

    ``recall_confident=False`` marks the weak-recall path that routes
    to the chips mode instead (called from the API layer)."""
    intent_scores = intent_scores or {}
    conf = float(intent_scores.get(intent_name, 0.0) or 0.0)
    deictic = _is_deictic(query)
    no_topic = topic_focus is None
    low_conf = conf < DEFAULT_THRESHOLD
    thematic = intent_name == "search_topic"
    is_followup = thematic and recall_confident and (
        deictic or (no_topic and low_conf)
    )
    # api-debug-logging: the followup-vs-break decision with its reasons
    trace("thread_turn",
          action="followup" if is_followup else "break",
          intent=intent_name, deictic=deictic, no_topic=no_topic,
          low_conf=low_conf, recall_confident=recall_confident,
          topic_focus=topic_focus, query=query)
    return {
        "action": "followup" if is_followup else "break",
        "intent": intent_name,
        "deictic": deictic,
        "no_topic": no_topic,
        "low_conf": low_conf,
        "recall_confident": recall_confident,
    }


# ----------------------------------------------------------------------
# Route execution + empty-result ladder
# ----------------------------------------------------------------------
class IntentRouter:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None,
                 decoder: Optional[SystemOneDecoder] = None,
                 engine=None):
        self.cfg = cfg or load_intents_config()
        self._decoder = decoder
        self._engine = engine

    @property
    def decoder(self) -> SystemOneDecoder:
        if self._decoder is None:
            self._decoder = SystemOneDecoder()
        return self._decoder

    def decode(self, query: str, engine=None) -> Dict[str, Any]:
        """Decode a query: intent + slots. Falls back to search_topic (with
        an error note) whenever the decision model is unreachable."""
        engine = engine or get_engine(readonly=True)
        with engine.connect() as conn:
            gremium_intent = None
            for intent in self.cfg["intents"]:
                if "gremium" in (intent.get("slots") or {}):
                    gremium_intent = intent
                    break
            gremium_vocab = (
                build_slot_vocab(conn, gremium_intent, "gremium")
                if gremium_intent else []
            )
        try:
            decoded = self.decoder.decode(
                query, self.cfg, gremium_vocab,
                prompt_id="intent-decision-question",
                call_id="pgIntentRouter.IntentRouter.decode.1",
            )
            decoded["error"] = None
        except Exception as exc:  # noqa: BLE001 - degrade to plain search
            decoded = {
                "intent": self.cfg["fallback_intent"],
                "scores": {},
                "slots": {},
                "error": f"decision model unreachable: {exc}",
            }
        # change: fix-gremium-session-docs-thread — deterministic intent
        # override: a query that names a gremium AND a meeting date ("themen
        # der gemeinderatssitzung im April 2026") is a session question even
        # when the decision model scored themensuche higher — the model
        # matches on topic words and under-scores the date frame. Override
        # (no model change) with the vocab-matched gremium term.
        try:
            decoded = self._apply_gremium_date_override(decoded, query,
                                                        gremium_vocab)
        except Exception as exc:  # noqa: BLE001
            trace("intent_override", step="gremium_date", error=str(exc))
        # api-debug-logging: the intent decision with its reasons
        scores = decoded.get("scores") or {}
        trace("intent_route", intent=decoded["intent"],
              confidence=max(scores.values(), default=0.0),
              scores=dict(sorted(scores.items(), key=lambda kv: -kv[1])[:5]),
              slots=decoded.get("slots") or {},
              decoder_error=decoded.get("error"))
        if decoded.get("error"):
            trace("intent_fallback", step="decoder_unreachable",
                  reason="decision model unreachable — fallback intent",
                  intent=decoded["intent"])
        return decoded

    def _apply_gremium_date_override(
            self, decoded: Dict[str, Any], query: str,
            gremium_vocab: List[str]) -> Dict[str, Any]:
        """Session-question override on a themensuche decode (change:
        fix-gremium-session-docs-thread).

        Fires when the decoded intent is the fallback/topic search but the
        raw query names both a gremium term (from the slot vocabulary) and
        a meeting date (German month, or "letzte sitzung"). Those queries
        are session questions; the decision model tends to under-score the
        date frame ("gemeinderat im April 2026" scored themensuche in live
        routing). The override pins the vocab-matched gremium term into the
        slot so resolve() scopes the meeting. No-op when the session
        machinery is not the decoded intent family."""
        if decoded.get("intent") not in (None, "", "search_topic"):
            return decoded
        month, year = extract_meeting_date(query)
        names_last = re.search(r"\bletzten?\b", query or "", re.IGNORECASE)
        norm_q = normalize_value(query)
        grem_term = None
        for term in gremium_vocab or []:
            if term and re.search(r"\b" + re.escape(normalize_value(term)) + r"\b",
                                  norm_q):
                grem_term = term
                break
        if grem_term is None or (month is None and names_last is None):
            return decoded
        # locate the gremium intent name from the vocab source
        for intent in self.cfg["intents"]:
            if "gremium" in (intent.get("slots") or {}):
                decoded["intent"] = intent["name"]
                break
        decoded.setdefault("slots", {})["gremium"] = grem_term
        decoded["override"] = "gremium_date"
        trace("intent_override", step="gremium_date", intent=decoded["intent"],
              slot=grem_term, month=month, year=year)
        return decoded

    def resolve(self, intent_name: str, slots: Dict[str, Any],
                session, query: str = "") -> Dict[str, Any]:
        """Derive filters/scope for the decoded intent.

        ``query`` is needed by slots resolved DB-side against the raw query
        (the location slot's trigram match) rather than via decoder choice.
        """
        intent = find_intent(self.cfg, intent_name) or {}
        route = intent.get("route") or {}
        resolved: Dict[str, Any] = {
            "intent": intent_name,
            "handler": route.get("handler", "search"),
            "answer_mode": route.get("answer_mode", "summary"),
            "filters": list(route.get("filters") or []),
            "gremium": None,
            "location": None,
            "notes": [],
        }
        if "gremium" in (intent.get("slots") or {}):
            groups = (intent.get("groups") or {}).get("gremium", [])
            term = slots.get("gremium")
            # change: fix-gremium-session-docs-thread — the raw query may
            # name a month ("themen der gemeinderatssitzung im september"):
            # LLM-based extraction (fallback: the regex path) feeds the
            # meeting resolution
            m_month, m_year = gremium_meeting_extract(query, term)
            if m_month is None:
                m_month, m_year = extract_meeting_date(query)
            grem = resolve_gremium(session, term, groups,
                                   month=m_month, year=m_year)
            resolved["gremium"] = grem
            if grem.get("empty") and grem.get("note"):
                # change: fix-gremium-session-docs-thread — month filter
                # without documents: state the real cause in the notes
                resolved["notes"].append(grem["note"])
            if grem["orgs"]:
                resolved["filters"] = resolved["filters"] + [
                    {"facet": "organization", "op": "in", "values": grem["orgs"]}
                ]
            else:
                # unknown gremium: fall through to unscoped search
                resolved["filters"] = []
                resolved["notes"].append(grem["note"])
        if "location" in (intent.get("slots") or {}):
            loc = resolve_location(session, query, intent)
            resolved["location"] = loc
            if not loc["locations"]:
                # unresolved location: fall through to unscoped search
                resolved["notes"].append(loc["note"])
        return resolved

    def run_search(self, session, query: str, resolved: Dict[str, Any],
                   top_k: int = 10, signals: Optional[Dict[str, bool]] = None,
                   summarize: bool = True,
                   search_fn: Optional[callable] = None) -> Dict[str, Any]:
        """Execute the routed search with the empty-result fallback ladder:
        scoped search -> unscoped retry (if filters were applied) -> honest
        empty response.

        ``search_fn`` swaps the executed pipeline (change:
        progressive-frontend-rendering): the default is the monolithic
        ``search_and_summarize``; the /ask endpoint injects a stage-1-only
        (recall) callable so the response carries no timeline/graph."""
        from src.pgTimeline import search_and_summarize

        if search_fn is None:
            search_fn = search_and_summarize

        notes: List[str] = list(resolved.get("notes") or [])
        filters = resolved.get("filters") or []

        # design D10: gremium answers are meeting-centric — the resolved
        # session IS the answer (graph + topic list), not a filtered search
        if (resolved.get("intent") == "ask_gremium_recent"
                and resolved.get("gremium", {}).get("meeting")):
            mres = meeting_scope_result(session, query, resolved)
            notes.extend(mres.get("notes") or [])
            result: Dict[str, Any] = {
                "query": query,
                "graph": mres["graph"],
                "top_files": mres["top_files"],
                "timeline": [],
                "matched_entities": [
                    {"id": n["id"], "type": n["type"], "oparlKey": n.get("oparlKey"),
                     "name": n.get("name"), "score": None, "signals": {}}
                    for n in mres["graph"]["nodes"]
                ],
                "facets": {},
                "applied_filters": filters,
                "topics": mres["topics"],
                "answer_mode": "list_topics",
            }
            if mres.get("empty"):
                # change: fix-gremium-session-docs-thread — the empty
                # message carries the resolution note (month filter /
                # document-less skip) so the UI shows the real cause
                result["empty_response"] = {
                    "message": (resolved["notes"][-1]
                                if resolved["notes"] else
                                "Für diese Sitzung wurden keine Dokumente gefunden."),
                    "intent": resolved["intent"],
                    "filters_tried": filters,
                    "gremium": resolved.get("gremium"),
                }
            result["intent"] = resolved["intent"]
            result["answer_mode"] = "list_topics"
            result["applied_filters"] = filters
            result["gremium"] = resolved.get("gremium")
            result["fallback_notes"] = notes
            trace("intent_route", handler="meeting_scope",
                  intent=resolved["intent"],
                  meeting=(resolved.get("gremium") or {}).get("meeting"))
            return result

        # add-location-intent: location answers retrieve through the geo
        # association tables; an unresolvable location falls through to the
        # unscoped search path below
        if (resolved.get("handler") == "location_scoped_search"
                and (resolved.get("location") or {}).get("locations")):
            from src.pgLocationSearch import location_search_stage

            result = location_search_stage(
                session, query, resolved["location"]["locations"],
                top_k=top_k, summarize=summarize)
            notes.extend(result.pop("notes", None) or [])
            if not (result.get("top_files") or []) and not (
                    result.get("matched_entities") or []):
                notes.append(
                    "keine Treffer im Ortsscope; Suche ohne Ortsscope "
                    "wiederholt"
                )
                trace("intent_fallback", step="location_scope_dropped",
                      reason="keine Treffer im Ortsscope")
                result = search_fn(
                    session, query, top_k=top_k, filters=None,
                    signals=signals, summarize=summarize,
                )
        else:
            result = search_fn(
                session, query, top_k=top_k, filters=filters or None,
                signals=signals, summarize=summarize,
            )
        if filters and not (result.get("top_files") or []):
            notes.append(
                "keine Treffer mit dem gefilterten Scope; Suche ohne Filter "
                "wiederholt"
            )
            trace("intent_fallback", step="filters_dropped",
                  reason="keine Treffer mit dem gefilterten Scope",
                  filters=filters)
            result = search_fn(
                session, query, top_k=top_k, filters=None,
                signals=signals, summarize=summarize,
            )

        if resolved.get("intent") == "ask_decision_date":
            try:
                result = drop_future_meeting_files(session, result, notes)
            except Exception:  # noqa: BLE001 - guard is best-effort
                notes.append("Zukunftssitzungs-Filter uebersprungen")

        empty = not (result.get("top_files") or []) and not (
            result.get("matched_entities") or []
        )
        result["intent"] = resolved["intent"]
        result["answer_mode"] = resolved["answer_mode"]
        result["applied_filters"] = filters
        result["gremium"] = resolved.get("gremium")
        result["location"] = resolved.get("location")
        result["fallback_notes"] = notes
        if empty:
            notes.append(
                "nichts gefunden; bitte andere Formulierung oder anderen "
                "Suchbegriff versuchen"
            )
            trace("intent_fallback", step="empty_response",
                  reason="nichts gefunden", intent=resolved["intent"],
                  filters=filters)
            result["empty_response"] = {
                "message": "Zu dieser Anfrage wurde nichts gefunden.",
                "intent": resolved["intent"],
                "filters_tried": filters,
                "gremium": resolved.get("gremium"),
            }
        return result


def is_gremium_session_query(query: str,
                             cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Head-of-chain pre-check for /ask (change:
    fix-gremium-session-docs-thread, task 7.3): the query names a gremium
    (from the slot vocabulary) AND a session date frame ("letzte(ten)
    Sitzung", month expression). Cheap DB-scan + regex — no model call.
    Used to skip the thread turn entirely (a gremium session query resets
    the conversation)."""
    from src.db import get_engine
    norm_q = normalize_value(query)
    if not norm_q:
        return False
    month, year = extract_meeting_date(query)
    names_last = re.search(r"\bletzten?\b", query or "", re.IGNORECASE)
    if month is None and not names_last:
        return False
    try:
        cfg = cfg or load_intents_config()
        gremium_intent = next(
            i for i in cfg["intents"]
            if "gremium" in (i.get("slots") or {}))
    except Exception:
        return False
    groups = (gremium_intent.get("groups") or {}).get("gremium", [])
    names = [g.get("primary", "") for g in groups] + [
        m for g in groups for m in (g.get("merged") or [])]
    for name in names:
        if name and re.search(
                r"\b" + re.escape(normalize_value(name)) + r"\b", norm_q):
            return True
    # aliases live in the slot vocabulary (e.g. "gr" for Gemeinderat) —
    # DB-scan once; the same query the decode uses via build_slot_vocab
    try:
        from src.db import get_engine
        vocab = build_slot_vocab(get_engine(readonly=True).connect(), gremium_intent, "gremium")
        for term in vocab:
            if term and re.search(
                    r"\b" + re.escape(normalize_value(term)) + r"\b", norm_q):
                return True
    except Exception:  # pragma: no cover - vocab failure → config-only path
        pass
    return False


def ask(session, query: str, cfg: Optional[Dict[str, Any]] = None,
        router: Optional[IntentRouter] = None, top_k: int = 10,
        signals: Optional[Dict[str, bool]] = None,
        summarize: bool = True,
        search_fn: Optional[callable] = None) -> Dict[str, Any]:
    """Convenience entry point for the /ask endpoint: decode + resolve +
    execute in one call.

    The query-embedding fetch and the decision-model decode are
    independent network waits — the embedding is pre-warmed on the
    parallel pool while the decoder runs (change:
    api-latency-optimization, task 4.1).

    ``search_fn`` is passed through to :meth:`IntentRouter.run_search`
    (change: progressive-frontend-rendering) so the /ask endpoint can
    execute the recall stage only."""
    router = router or IntentRouter(cfg=cfg)

    prewarm = None
    if _parallel_enabled():
        try:
            from src.pgHybridSearch import _hybrid_executor
            from src.pgTimeline import call_embedding_model

            prewarm = _hybrid_executor().submit(call_embedding_model, query)
        except Exception:  # noqa: BLE001 - pre-warm is best-effort
            prewarm = None

    decoded = router.decode(query)

    if prewarm is not None:
        try:
            prewarm.result(timeout=60)
        except Exception:  # noqa: BLE001 - search path embeds on its own
            pass

    resolved = router.resolve(decoded["intent"], decoded.get("slots") or {},
                              session, query=query)
    result = router.run_search(session, query, resolved, top_k=top_k,
                               signals=signals, summarize=summarize,
                               search_fn=search_fn)
    result["intent_scores"] = decoded.get("scores") or {}
    if decoded.get("error"):
        result["fallback_notes"] = list(result.get("fallback_notes") or []) + [
            decoded["error"]
        ]
    result["slots"] = decoded.get("slots") or {}
    return result


def _parallel_enabled() -> bool:
    import os

    return os.getenv("RISKI_PARALLEL_SIGNALS", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
