"""Extract request and response statements per pair (stage 4).

Capability: ``kg-statement-extraction`` (task 5.1/5.2). For each
identified pair two structured LLM calls (JSON-constrained prompts, one
per stage — design D5/D11):

* **request stage** over the pair's request/modification documents:
  topic/title, request type, meeting date, document id + file names,
  author (joined from the author statement row), intended impact,
  affected audience, actor, precise requested action, start/end dates,
  expected benefit, involved cost — with source document/chunk
  references; fields stay EMPTY when the source has nothing.
* **response stage** over the response documents (verified protocols,
  agenda-item files) + the pair's outcome:
  response type, result, action, executing actor, expected cost,
  start/end dates, modifications to the request, dependencies or
  constraints (e.g. third-party funding condition, Haushaltssperre).
* modification pairs (class ``modification``) are linked to the closest
  original request pair by deterministic title similarity (difflib
  ratio ≥ 0.75 among request pairs around the same meeting date).

Extracted pairs move status ``identified -> statements`` (resume-safe:
re-runs skip completed pairs).

Usage::

    python -m src.kg.kgStatements --limit 10            # sample
    python -m src.kg.kgStatements --model granite4.2:8b # default
    python -m src.kg.kgStatements --skip-request        # responses only
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import difflib
import json
from typing import Any

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab

log = get_logger("riski.kg.statements")

DEFAULT_STORE = "results/kg_statements.sqlite"
DEFAULT_MODEL = "granite4.2:8b"
MAX_TEXT_CHARS = 12000
MODIFY_RATIO = 0.75

REQUEST_FIELDS = [
    "topic",
    "request_type",
    "meeting_date",
    "document_id",
    "file_names",
    "author",
    "intended_impact",
    "audience",
    "action_actor",
    "requested_action",
    "start_date",
    "end_date",
    "expected_benefit",
    "involved_cost",
    "source_refs",
]
RESPONSE_FIELDS = [
    "response_type",
    "result",
    "planned_action",
    "action_executor",
    "expected_cost",
    "start_date",
    "end_date",
    "request_modifications",
    "dependencies_constraints",
    "source_refs",
]

_REQUEST_PROMPT = """Du bist ein extrahierender Assistent. Extrahiere die Kernfakten aus dem
folgenden deutschen Dokument (Antrag/Anfrage der Karlsruher
Kommunalpolitik) und antworte AUSSCHLIESSLICH mit einem JSON-Objekt mit
genau diesen Feldern:

{fields}

Regeln:
- ALLE Feldinhalte streng auf DEUTSCH — übernimm die Worte des
  Dokuments, übersetze nicht, paraphrasiere nicht ins Englische.
- Nur Fakten aus dem Dokument. Wenn etwas nicht drinsteht: leere
  Zeichenkette (""), niemals erfinden.
- involved_cost / start_date / end_date nur mit Werten aus dem Text.
- source_refs: Liste der Dokument-IDs/Dateinamen, aus denen die Werte stammen;
  sonst [].
"""

_RESPONSE_PROMPT = """Du bist ein extrahierender Assistent. Das Folgende sind
Reaktions-/Entscheidungstexte (Protokoll, Beschluss, Antwort) zu einem
Antrag des Gemeinderats Karlsruhe. Extrahiere die Kernfakten und antworte
AUSSCHLIESSLICH mit einem JSON-Objekt mit genau diesen Feldern:

{fields}

Regeln:
- ALLE Feldinhalte streng auf DEUTSCH — übernimme die Worte des
  Dokuments, übersetze nicht, paraphrasiere nicht ins Englische.
- Nur Fakten aus den Texten. Fehlt etwas: "" (niemals erfinden).
- response_type: einer von zugestimmt/abgelehnt/vertagt/verwiesen/
  zur_kenntnis_gekommen/erledigt/ja_stellungnahme/anders.
- request_modifications: Ände von Antrag beschrieben ("" falls keine).
- dependencies_constraints: Bedingungen/Fallstricke (z.B. Drittmittel,
  Haushaltssperre) oder "".
- source_refs: Liste der Dokument-IDs/Dateinamen, sonst [].
"""


def texts_for_role(conn: Any, doc_keys: list[str], n_docs: int = 4) -> tuple[str, list[str]]:
    """Head text of the pair's documents for one role; returns (text, doc ids)."""
    import re

    from sqlalchemy import text as _t

    texts, ids = [], []
    for dk in doc_keys[:n_docs]:
        rows = conn.execute(
            _t(
                """
                SELECT fc.text, f."oparlId", f.filename
                FROM "File_chunks" fc
                JOIN "File" f ON f.sid = fc."file_sid"
                WHERE f."oparlKey" = :dk
                ORDER BY fc.chunk_index LIMIT 8
                """
            ),
            {"dk": dk},
        ).fetchall()
        if rows:
            body = "".join((r[0] or "") for r in rows)[:MAX_TEXT_CHARS]
            texts.append(f"[Dok {rows[0][1]} {rows[0][2]}]\n{body}")
            ids.append(rows[0][1])
        else:
            teaser = conn.execute(
                _t('SELECT COALESCE(teaser, \'\') FROM "File" WHERE "oparlKey" = :k'),
                {"k": dk},
            ).scalar()
            if teaser:
                texts.append(teaser[:2000])
    return "\n\n".join(texts), ids


class StatementExtractor:
    def __init__(self, remote: KgRemote, model: str = DEFAULT_MODEL):
        self.remote = remote
        self.model = model

    # ------------------------------------------------------------------
    def extract(self, stage: str, body: str, extra: str = "") -> dict:
        fields = ", ".join('"' + f + '"' for f in (REQUEST_FIELDS if stage == "request" else RESPONSE_FIELDS))
        prompt = (_REQUEST_PROMPT if stage == "request" else _RESPONSE_PROMPT).format(fields=fields)
        if extra:
            prompt += f"\n{extra}"
        return self.remote.chat_json(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": body or "<kein Text>"},
            ],
            model=self.model,
        )

    # ------------------------------------------------------------------
    def sanitize(self, stage: str, out: dict, meta: dict) -> dict:
        """Keep only declared fields, fill meta-owned fields, drop junk."""
        fields = REQUEST_FIELDS if stage == "request" else RESPONSE_FIELDS
        clean = {f: str(out.get(f, "") or "") for f in fields if f != "source_refs"}
        refs = out.get("source_refs")
        clean["source_refs"] = refs if isinstance(refs, list) else []
        for key, value in meta.items():
            clean[key] = value
        return clean


def modification_links(store: KgStore) -> int:
    """Link modification pairs to their original request pair (D11).

    Title similarity uses the Paper names from PostgreSQL (attachment
    names are boilerplate like "Änderungs-/Ergänzungsantrag" and would
    match everything at ratio 1.0).
    """
    from sqlalchemy import text as _t

    from src.db import get_engine

    conn = get_engine(readonly=True).connect()
    names: dict[str, str] = {}
    for row in conn.execute(_t('SELECT "oparlId", name FROM "Paper"')):
        names[row[0]] = row[1] or ""
    conn.close()

    mods = store.conn.execute(
        """
        SELECT pair_key, paper_key, meeting_date FROM pairs
        WHERE request_type = 'aenderungsantrag'
        """
    ).fetchall()
    cands = store.conn.execute(
        """
        SELECT pair_key, paper_key, meeting_date FROM pairs
        WHERE request_type IN ('antrag', 'anfrage', 'beschlussvorlage')
        """
    ).fetchall()

    import difflib

    def _year(md: str | None) -> int | None:
        try:
            return int(md.split("-")[0])
        except (ValueError, AttributeError, IndexError):
            return None

    links = 0
    for mod in mods:
        mod_title = names.get(mod["paper_key"], "")
        if not mod_title:
            continue
        mod_year = _year(mod["meeting_date"])
        best_key, best_ratio = None, 0.0
        for cand in cands:
            cand_title = names.get(cand["paper_key"], "")
            if not cand_title or cand["pair_key"] == mod["pair_key"]:
                continue
            # prefer temporally close originals (± 1 year): only run the
            # expensive difflib when the years are plausibly adjacent —
            # a modification request always follows its original closely
            cy = _year(cand["meeting_date"])
            if mod_year is not None and cy is not None and abs(cy - mod_year) > 1:
                continue
            ratio = difflib.SequenceMatcher(
                None, mod_title.lower(), cand_title.lower()
            ).ratio()
            if mod_year is not None and cy is not None and abs(cy - mod_year) <= 1:
                ratio = min(1.0, ratio + 0.1)
            if ratio > best_ratio:
                best_key, best_ratio = cand["pair_key"], ratio
        if best_key and best_ratio >= MODIFY_RATIO:
            store.upsert_statement(
                mod["pair_key"],
                "link",
                None,
                json.dumps(
                    {"modifies": best_key, "title_ratio": round(best_ratio, 3),
                     "title": mod_title},
                    ensure_ascii=False,
                ),
            )
            links += 1
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default="ollama")
    parser.add_argument("--limit", type=int, default=0, help="at most N pairs")
    parser.add_argument("--skip-request", action="store_true")
    parser.add_argument("--skip-response", action="store_true")
    parser.add_argument(
        "--commit-every", type=int, default=5,
        help="commit the SQLite store every N pairs (checkpointing; the "
        "long bulk run must survive interruption without repeating work)",
    )
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    remote = KgRemote(args.endpoint)
    remote.available_models()  # accessibility check
    if args.model not in remote.available_models():
        log.warning("model %s not offered by endpoint — using decision model", args.model)

    extractor = StatementExtractor(remote, args.model)
    modification_links(store)

    pairs = store.pairs_by_status("identified")
    stats = {"pairs": 0, "request_ok": 0, "response_ok": 0, "errors": 0}
    ticker = StatusTicker()
    ticker.section("statements")
    for pair in pairs:
        if args.limit and stats["pairs"] >= args.limit:
            break
        stats["pairs"] += 1
        ticker.tick(
            f"pairs={stats['pairs']} request={stats['request_ok']} "
            f"response={stats['response_ok']} errors={stats['errors']}"
        )
        docs = store.documents_for_pair(pair["pair_key"])
        role_keys = {
            r: [d["doc_key"] for d in docs if d["role"] == r]
            for r in ("request", "modification", "response")
        }
        author_row = store.conn.execute(
            "SELECT fields_json FROM statements WHERE pair_key = ? AND stage = 'author'",
            (pair["pair_key"],),
        ).fetchone()
        author = json.loads(author_row[0])["author"] if author_row else ""

        # ---- request stage ------------------------------------------
        if not args.skip_request:
            req_docs = role_keys["request"] + role_keys["modification"]
            body, ids = texts_for_role(conn, req_docs)
            # metadata comes from the DB, never from the model
            filenames = [
                d["filename"] for d in docs if d["role"] in ("request", "modification") and d["filename"]
            ]
            meta = {
                "meeting_date": pair["meeting_date"] or "",
                "author": author,
                "request_type": pair["request_type"] or "",
                "document_id": "|".join(ids),
                "file_names": ", ".join(filenames),
            }
            try:
                out = extractor.extract("request", body)
                clean = extractor.sanitize("request", out, meta)
                for owned in ("meeting_date", "author", "request_type", "document_id", "file_names"):
                    clean[owned] = meta[owned]  # DB values always win
                store.upsert_statement(
                    pair["pair_key"], "request", None, json.dumps(clean, ensure_ascii=False)
                )
                stats["request_ok"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
                log.warning("request extraction failed for %s: %s", pair["pair_key"], exc)

        # ---- response stage -----------------------------------------
        if not args.skip_response:
            cand_ids = role_keys["response"]
            if cand_ids:
                body, ids = texts_for_role(conn, cand_ids)
                epilogue = (
                    f"Vorbekannt aus der Datenbank: Ergebnis='{pair['outcome']}', "
                    f"Beschluss der Sitzung vom {pair['meeting_date']}."
                )
                try:
                    out = extractor.extract("response", body, epilogue)
                    clean = extractor.sanitize(
                        "response",
                        out,
                        {
                            "meeting_date": pair["meeting_date"] or "",
                            "outcome_db": pair["outcome"] or "",
                            "document_id": "|".join(cand_ids[:4]),
                        },
                    )
                    clean["meeting_date"] = pair["meeting_date"] or ""
                    store.upsert_statement(
                        pair["pair_key"], "response", None, json.dumps(clean, ensure_ascii=False)
                    )
                    stats["response_ok"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    log.warning("response extraction failed for %s: %s", pair["pair_key"], exc)

        store.set_pair_status(pair["pair_key"], "statements")
        if args.commit_every and stats["pairs"] % args.commit_every == 0:
            store.commit()  # checkpoint: resume later without repeating

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
