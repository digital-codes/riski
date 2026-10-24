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
from typing import Any, Dict, List, Optional

import httpx
import sqlalchemy as sa
import yaml
from sqlalchemy import MetaData, Table, select, text

from src.db import get_engine

CONFIG_PATH = Path(__file__).parent.parent / "config" / "intents.yaml"
DEFAULT_FALLBACK_INTENT = "search_topic"
DEFAULT_THRESHOLD = 0.5
DEFAULT_SYSONE_TIMEOUT = 30.0


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
            "instructions": (
                f"Ist der Intent '{intent['name']}' gemeint? ({intent['description']})"
            ),
            "criteria": {"true": "Ja, passt", "false": "Nein, passt nicht"},
        }
    if gremium_vocab:
        questions["slot_gremium"] = {
            "type": "choice",
            "instructions": (
                "Welches Gremium (Rat, Ortschaftsrat, Ausschuss) ist in der "
                "Benutzeranfrage gemeint?"
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
    """Thin sync client for the SystemOne decision-model endpoint."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None,
                 key: Optional[str] = None, timeout: float = DEFAULT_SYSONE_TIMEOUT):
        import src.private as pr

        self.url = url or getattr(pr, "SYSONE_URL", None)
        self.model = model or getattr(pr, "SYSONE_MDL", None)
        self.key = key or getattr(pr, "SYSONE_KEY", None)
        self.timeout = timeout
        if not self.url or not self.model:
            raise DecoderError("SYSONE_URL / SYSONE_MDL not configured")

    def decode(self, query: str, cfg: Dict[str, Any],
               gremium_vocab: List[str]) -> Dict[str, Any]:
        """One round-trip: intent (noul per intent) + slot questions."""
        payload = {
            "model": self.model,
            "state": normalize_value(query),
            "questions": build_questions(cfg, gremium_vocab),
        }
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        resp = httpx.post(self.url, json=payload, timeout=self.timeout, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return parse_answers(cfg, data.get("answers", {}), gremium_vocab)


# ----------------------------------------------------------------------
# Gremium resolution (org groups + latest held meeting)
# ----------------------------------------------------------------------
def resolve_gremium(session, term: Optional[str],
                    groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve a gremium term to organizations and the latest held meeting.

    Org groups (config) merge one-off sub-orgs into their parent at
    resolve time. Returns {orgs: [names], meeting: {...}|None, note: str}.
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

    # latest held meeting across the org group (future meetings never win)
    meeting = Table("Meeting", meta, autoload_with=session.bind)
    morg = Table("Meeting__organization__Organization", meta, autoload_with=session.bind)
    row = session.execute(
        select(
            meeting.c.sid, meeting.c.name, meeting.c.start_date, meeting.c.oparlKey
        )
        .select_from(
            morg.join(meeting, morg.c.srcSid == meeting.c.sid).join(
                org, morg.c.tgtSid == org.c.sid
            )
        )
        .where(
            org.c.name.in_(out["orgs"]),
            meeting.c.start_date <= datetime.datetime.now(),
        )
        .order_by(meeting.c.start_date.desc())
        .limit(1)
    ).first()
    if row:
        out["meeting"] = {
            "sid": row[0], "name": row[1], "start_date": row[2],
            "oparlKey": row[3],
        }
    else:
        out["note"] = "keine abgehaltene Sitzung des Gremiums gefunden"
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
    """Meeting-centric answer for gremium questions (design D10).

    Forward traversal from the resolved meeting via the ADJACENCY map;
    returns the meeting-centered graph, the agenda items as topics with
    their files, and Tagesordnung + all session documents as top_files
    (no top_k cut — the session IS the answer). No LLM summary, no map
    (answer_mode: list_topics)."""
    from src.graphModel import expand_neighbors

    notes: List[str] = list(resolved.get("notes") or [])
    grem = resolved.get("gremium") or {}
    meeting = grem.get("meeting") or {}

    graph = {"nodes": [], "edges": []}
    top_files: List[Dict[str, Any]] = []
    topics: List[Dict[str, Any]] = []

    meeting_key = meeting.get("oparlKey")
    if not meeting_key:
        notes.append("keine abgehaltene Sitzung gefunden; Suche ohne Sitzungs-Scope")
        return {
            "query": query, "graph": graph, "top_files": top_files,
            "topics": topics, "answer_mode": "list_topics", "notes": notes,
            "empty": True,
        }

    meeting_id = f"Meeting_{meeting_key}"
    # depth 1: agenda items, Tagesordnung + aux files, organizations, then
    # the agenda items' children (files, consultations -> papers -> files)
    partials: List[Dict[str, Any]] = [
        expand_neighbors(session.bind, meeting_id, limit_per_relation)
    ]
    graph = _merge_graph_partials(partials)
    for round_type in ("AgendaItem", "Consultation", "Paper"):
        ids = [n["id"] for n in graph["nodes"] if n["type"] == round_type]
        for nid in ids:
            try:
                partials.append(
                    expand_neighbors(session.bind, nid, limit_per_relation)
                )
            except ValueError:
                continue
        graph = _merge_graph_partials(partials)
    file_by_id = {n["id"]: n for n in graph["nodes"] if n["type"] == "File"}

    # topics: agenda items with their files (direct + via consultation/paper)
    consult_of_ai: Dict[str, str] = {}
    paper_of_consult: Dict[str, str] = {}
    files_of_paper: Dict[str, List[str]] = {}
    for e in graph["edges"]:
        src, tgt, rel = e["source"], e["target"], e["relation"]
        if rel == "consultation" and src.startswith("AgendaItem_"):
            consult_of_ai[src] = tgt
        elif rel == "paper" and src.startswith("Consultation_"):
            paper_of_consult[src] = tgt
        elif rel in ("auxiliaryFile", "mainFile") and src.startswith("Paper_"):
            files_of_paper.setdefault(src, []).append(tgt)

    item_files: Dict[str, List[str]] = {}
    for e in graph["edges"]:
        if (e["relation"] == "auxiliaryFile"
                and e["source"].startswith("AgendaItem_")
                and e["target"].startswith("File_")):
            item_files.setdefault(e["source"], []).append(e["target"])
    for ai, consult in consult_of_ai.items():
        paper = paper_of_consult.get(consult)
        for fid in files_of_paper.get(paper, []) or []:
            item_files.setdefault(ai, []).append(fid)

    def _file_payload(fid: str) -> Dict[str, Any]:
        f = file_by_id.get(fid, {})
        return {
            "id": fid,
            "oparlKey": f.get("oparlKey"),
            "name": f.get("name"),
            "date": f.get("date"),
            "downloadurl": (f.get("attrs") or {}).get("downloadurl")
                           or f.get("oparlId"),
        }

    def _top_sort_key(n):
        num = (n.get("attrs") or {}).get("number")
        try:
            # sub-items like "4.1" become decimals: 4 < 4.1 < 5
            return (0, float(num), "")
        except (TypeError, ValueError):
            if num is None:
                return (1, 0.0, "")
            return (2, 0.0, str(num))

    for n in sorted(
        (n for n in graph["nodes"] if n["type"] == "AgendaItem"),
        key=_top_sort_key,
    ):
        fids = list(dict.fromkeys(item_files.get(n["id"], [])))
        topics.append({
            "id": n["id"],
            "oparlKey": n.get("oparlKey"),
            "number": (n.get("attrs") or {}).get("number"),
            "name": n.get("name"),
            "result": (n.get("attrs") or {}).get("result"),
            "files": [_file_payload(fid) for fid in fids],
        })

    # top_files: Tagesordnung first, then the session's other documents —
    # meeting-linked files (TO/Protokoll/aux), falling back to the agenda
    # items' documents when the session has none published yet
    meeting_file_ids = {
        e["target"] for e in graph["edges"]
        if e["source"] == meeting_id and e["target"].startswith("File_")
    }
    agenda_file_ids = list(dict.fromkeys(
        fid for fids in item_files.values() for fid in fids
    ))
    ordered_ids = sorted(
        meeting_file_ids, key=lambda fid: not _is_tagesordnung(file_by_id.get(fid, {}))
    ) + [fid for fid in agenda_file_ids if fid not in meeting_file_ids]
    for fid in ordered_ids:
        n = file_by_id.get(fid) or {}
        attrs = n.get("attrs") or {}
        top_files.append({
            "oparlKey": n.get("oparlKey"),
            "name": n.get("name"),
            "fileName": attrs.get("fileName"),
            "downloadurl": attrs.get("downloadurl"),
            "oparlId": n.get("oparlId"),
            "date": n.get("date"),
            "distance": None,
            "match": {},
        })

    if not top_files:
        notes.append("keine Sitzungsdokumente gefunden")
    return {
        "query": query, "graph": graph, "top_files": top_files,
        "topics": topics, "answer_mode": "list_topics", "notes": notes,
        "empty": not (top_files or topics),
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
            decoded = self.decoder.decode(query, self.cfg, gremium_vocab)
            decoded["error"] = None
        except Exception as exc:  # noqa: BLE001 - degrade to plain search
            decoded = {
                "intent": self.cfg["fallback_intent"],
                "scores": {},
                "slots": {},
                "error": f"decision model unreachable: {exc}",
            }
        return decoded

    def resolve(self, intent_name: str, slots: Dict[str, Any],
                session) -> Dict[str, Any]:
        """Derive filters/scope for the decoded intent."""
        intent = find_intent(self.cfg, intent_name) or {}
        route = intent.get("route") or {}
        resolved: Dict[str, Any] = {
            "intent": intent_name,
            "handler": route.get("handler", "search"),
            "answer_mode": route.get("answer_mode", "summary"),
            "filters": list(route.get("filters") or []),
            "gremium": None,
            "notes": [],
        }
        if "gremium" in (intent.get("slots") or {}):
            groups = (intent.get("groups") or {}).get("gremium", [])
            term = slots.get("gremium")
            grem = resolve_gremium(session, term, groups)
            resolved["gremium"] = grem
            if grem["orgs"]:
                resolved["filters"] = resolved["filters"] + [
                    {"facet": "organization", "op": "in", "values": grem["orgs"]}
                ]
            else:
                # unknown gremium: fall through to unscoped search
                resolved["filters"] = []
                resolved["notes"].append(grem["note"])
        return resolved

    def run_search(self, session, query: str, resolved: Dict[str, Any],
                   top_k: int = 10, signals: Optional[Dict[str, bool]] = None,
                   summarize: bool = True) -> Dict[str, Any]:
        """Execute the routed search with the empty-result fallback ladder:
        scoped search -> unscoped retry (if filters were applied) -> honest
        empty response."""
        from src.pgTimeline import search_and_summarize

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
                result["empty_response"] = {
                    "message": "Für diese Sitzung wurden keine Dokumente gefunden.",
                    "intent": resolved["intent"],
                    "filters_tried": filters,
                    "gremium": resolved.get("gremium"),
                }
            result["intent"] = resolved["intent"]
            result["answer_mode"] = "list_topics"
            result["applied_filters"] = filters
            result["gremium"] = resolved.get("gremium")
            result["fallback_notes"] = notes
            return result

        result = search_and_summarize(
            session, query, top_k=top_k, filters=filters or None,
            signals=signals, summarize=summarize,
        )
        if filters and not (result.get("top_files") or []):
            notes.append(
                "keine Treffer mit dem gefilterten Scope; Suche ohne Filter "
                "wiederholt"
            )
            result = search_and_summarize(
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
        result["fallback_notes"] = notes
        if empty:
            notes.append(
                "nichts gefunden; bitte andere Formulierung oder anderen "
                "Suchbegriff versuchen"
            )
            result["empty_response"] = {
                "message": "Zu dieser Anfrage wurde nichts gefunden.",
                "intent": resolved["intent"],
                "filters_tried": filters,
                "gremium": resolved.get("gremium"),
            }
        return result


def ask(session, query: str, cfg: Optional[Dict[str, Any]] = None,
        router: Optional[IntentRouter] = None, top_k: int = 10,
        signals: Optional[Dict[str, bool]] = None,
        summarize: bool = True) -> Dict[str, Any]:
    """Convenience entry point for the /ask endpoint: decode + resolve +
    execute in one call."""
    router = router or IntentRouter(cfg=cfg)
    decoded = router.decode(query)
    resolved = router.resolve(decoded["intent"], decoded.get("slots") or {}, session)
    result = router.run_search(session, query, resolved, top_k=top_k,
                               signals=signals, summarize=summarize)
    result["intent_scores"] = decoded.get("scores") or {}
    if decoded.get("error"):
        result["fallback_notes"] = list(result.get("fallback_notes") or []) + [
            decoded["error"]
        ]
    result["slots"] = decoded.get("slots") or {}
    return result
