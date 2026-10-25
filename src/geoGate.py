"""GeoGate — LLM relevance gate for street/district geo references
(change: geo-gating).

The literal street/district matcher links names found in File name +
teaser — and teasers are built from the content start, where council
documents carry their Briefkopf (sender/recipient address blocks). Result:
"Antrag der CDU, Hebelstraße 21" links Hebelstraße even though the
document's main content is unrelated.

The gate asks the summary model, per document (all matched names batched
into ONE call), whether each mention belongs to the document's main body
(`content`) or only to boilerplate (Briefkopf addresses, footer/contact
blocks, venue boilerplate, Impressum).

**Permissive principle**: the gate may only suppress when confident.
Verdict semantics for map output:

- ``content``  → shown
- ``unsure``   → shown (LLM cannot decide; reason kept for review)
- ``NULL``     → shown (ungated: legacy rows, LLM unavailable, parse error)
- ``boilerplate`` → hidden (the ONLY suppressing verdict)

A gate failure never fails the matching pipeline — affected rows stay
NULL/visible and the cleanup pass (`pgGeoGateCleanup.py`) gates them later.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import MetaData, Table, text

from src.db import get_engine
from src.db import get_logger

logger = get_logger("riski.geoGate")

# The four association tables the gate covers, with their entity column.
GATED_TABLES = {
    "Streets_items_Files": "street_id",
    "Districts_items_Files": "district_id",
    "Streets_items_AgendaItems": "street_id",
    "Districts_items_AgendaItems": "district_id",
}

GATE_COLUMNS_DDL = [
    'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS gate_status VARCHAR(16)',
    'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS gate_reason VARCHAR(255)',
    'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS gated_at TIMESTAMP',
    'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS gate_model VARCHAR(64)',
]

PROMPT_TEMPLATE = """Du prüfst Georeferenzen in Dokumenten des Ratsinformationssystems der Stadt Karlsruhe.

Gegeben: der Inhalt eines Dokuments und eine Liste von Straßennamen bzw. Stadtteilen, die automatisiert im Text gefunden wurden.

Aufgabe: Entscheide für jeden Namen, ob er zum HAUPTINHALT des Dokuments gehört oder nur aus Beilage-/Metadaten-Text stammt.

Als HAUPTINHALT gilt: der eigentliche Text des Antrags / der Anfrage / der Beschlussvorlage / des Protokolls — z. B. eine Straße als Ort einer geplanten Maßnahme, als betroffener Bereich oder als Thema.

Als BEILAGE/METADATEN gelten und werden als "boilerplate" eingestuft:
- Absender- und Empfängeradressen im Briefkopf (Antragsteller, Fraktion, Amt, Behörde, Unternehmen)
- Fußzeilen, Impressum, Kontakt- und Signaturblöcke
- Veranstaltungsort-Boilerplate (z. B. "Bürgersaal, Rathaus am Marktplatz")
- Wiederkehrende Formulare/Deckblatt-Angaben ohne inhaltlichen Bezug

WICHTIG: Auch wenn eine Straße politisch relevant erscheint (z. B. die
"Hebelstraße", in der das Haus der Fraktionen liegt und viele Fraktionen
ihre Geschäftsstelle haben): Eine Adresszeile eines Antragstellers
("Fraktion X, Hebelstraße 21, 76133 Karlsruhe") ist BOILERPLATE, egal
welche Partei oder Behörde dort sitzt. Entscheidend ist allein, ob der
HAUPTTEXT des Dokuments diese Straße inhaltlich behandelt. Nur wenn der
Haupttext selbst von der Straße handelt (z. B. Verkauf des "ehemaligen
Hauses der Fraktionen in der Hebelstraße 13"), ist es "content".

Dokument-Typ: {doc_type}
Dokument-Name: {doc_name}

Dokumentinhalt:
\"\"\"
{content}
\"\"\"

Gefundene Namen (mit Fundkontext):
{mentions}

Antworte AUSSCHLIESSLICH mit JSON, keine weiteren Texte:
{{"verdicts": [
  {{"name": "<Name>", "verdict": "content"|"boilerplate"|"unsure",
    "reason": "<kurzer deutscher Grund, max. 1 Satz>"}}
]}}

Regeln:
- Genau ein Eintrag pro gegebenem Namen, Namen unverändert übernehmen.
- "content": der Name wird im Haupttext inhaltlich verwendet — auch wenn er zusätzlich in einer Adresse vorkommt.
- "boilerplate": der Name kommt NUR in Kopf-/Fuß-/Adressbestandteilen vor.
- Wenn du nicht sicher entscheiden kannst: "unsure"."""


class GeoGate:
    """LLM gate for geo references. Permissive: only a confident
    ``boilerplate`` verdict suppresses; everything else stays visible."""

    def __init__(self, engine=None, model: Optional[str] = None,
                 max_content_chars: int = 6000, context_chars: int = 200):
        self.engine = engine or get_engine()
        self.model = model
        self.max_content_chars = max_content_chars
        self.context_chars = context_chars

    # -- schema -----------------------------------------------------------

    def ensure_columns(self) -> None:
        """Add the gate columns to all four assoc tables (idempotent)."""
        with self.engine.begin() as conn:
            for table in GATED_TABLES:
                for ddl in GATE_COLUMNS_DDL:
                    conn.execute(text(ddl.format(table=table)))

    # -- context extraction -------------------------------------------------

    def _context_around(self, content: str, name: str) -> str:
        """A short excerpt around the first occurrence of *name* in the
        content (for the prompt's mention list)."""
        idx = content.lower().find(name.lower())
        if idx < 0:
            return ""
        start = max(0, idx - self.context_chars // 2)
        end = min(len(content), idx + len(name) + self.context_chars // 2)
        excerpt = content[start:end].replace("\n", " ").strip()
        return f"…{excerpt}…" if start > 0 or end < len(content) else excerpt

    # -- prompting ----------------------------------------------------------

    def build_prompt(self, doc_name: str, doc_type: str, content: str,
                     mentions: List[Dict[str, str]]) -> str:
        mention_lines = []
        for m in mentions:
            ctx = m.get("context") or ""
            mention_lines.append(f"- {m['entity']}" + (f" (Fundkontext: {ctx})" if ctx else ""))
        return PROMPT_TEMPLATE.format(
            doc_type=doc_type or "unbekannt",
            doc_name=doc_name or "unbekannt",
            content=content[: self.max_content_chars],
            mentions="\n".join(mention_lines) or "- (keine)",
        )

    @staticmethod
    def parse_verdicts(raw: str, names: List[str]) -> Dict[str, Dict[str, str]]:
        """Parse the model's JSON answer; defensive — on any failure every
        name degrades to ``unsure``/``parse error`` (permissive principle:
        parse problems must never hide links)."""
        fallback = {n: {"verdict": "unsure", "reason": "parse error"}
                    for n in names}
        if not raw:
            return fallback
        # strip code fences if the model wrapped its answer
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return fallback
        try:
            data = json.loads(cleaned[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return fallback
        out: Dict[str, Dict[str, str]] = {}
        by_name = {}
        for v in data.get("verdicts", []):
            if isinstance(v, dict) and isinstance(v.get("name"), str):
                by_name[v["name"].strip().lower()] = v
        for n in names:
            v = by_name.get(n.strip().lower())
            verdict = (v or {}).get("verdict", "unsure")
            if verdict not in ("content", "boilerplate", "unsure"):
                verdict = "unsure"
            reason = str((v or {}).get("reason", ""))[:250]
            out[n] = {"verdict": verdict, "reason": reason}
        return out

    # -- gating -------------------------------------------------------------

    def _chat(self, prompt: str) -> Optional[str]:
        """One summary-model call; returns content or None on failure."""
        try:
            from src import remote

            result = remote.chat(
                [{"role": "system",
                  "content": "Du bist ein präziser Assistent für "
                             "Dokumentenanalyse. Antworte ausschließlich mit "
                             "dem geforderten JSON."},
                 {"role": "user", "content": prompt}],
                model=self.model, temperature=0.0,
            )
            return (result or {}).get("content")
        except Exception as exc:  # noqa: BLE001 - gate must never break matching
            logger.warning("GeoGate LLM call failed: %s", exc)
            return None

    def gate_mentions(self, doc_name: str, doc_type: str, content: str,
                      mentions: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        """Classify *mentions* against the document content. Returns
        {entity: {"verdict", "reason"}}. All-unsure on any failure."""
        names = [m["entity"] for m in mentions]
        if not names:
            return {}
        prompt = self.build_prompt(doc_name, doc_type, content or "", mentions)
        try:
            raw = self._chat(prompt)
        except Exception as exc:  # noqa: BLE001 - gate must never break matching
            logger.warning("GeoGate LLM call failed: %s", exc)
            raw = None
        verdicts = self.parse_verdicts(raw, names)
        if raw is None:
            # LLM unavailable: permissive fallback, flagged for cleanup
            verdicts = {n: {"verdict": "unsure", "reason": "llm error"}
                        for n in names}
        return verdicts

    def gate_file(self, file_sid: int,
                  mentions: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        """Load the document (name/kind/content) for *file_sid* and gate its
        mentions against it."""
        from sqlalchemy import text as _text

        with self.engine.connect() as conn:
            row = conn.execute(_text(
                'SELECT name, contentkind, content FROM "File" WHERE sid = :s'
            ), {"s": file_sid}).first()
        if row is None:
            return {m["entity"]: {"verdict": "unsure", "reason": "file missing"}
                    for m in mentions}
        name, kind, content = row
        return self.gate_mentions(name, kind, content, mentions)

    def gate_agenda_item(self, item_sid: int, item_name: str,
                         mentions: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        """Gate mentions found in an agenda item name (context = the name —
        short input, same permissive semantics)."""
        return self.gate_mentions(item_name, "Tagesordnungspunkt",
                                  item_name or "", mentions)

    def gate_agenda_links(self, assoc_table: str, entity_col: str,
                          new_pairs: List[Dict[str, Any]]) -> int:
        """Gate newly written agenda-item links (batched per item).
        new_pairs: [{entity_id, entity_name, item_sid, item_name}].
        Failures leave rows ungated (permissive). Returns gated count."""
        if not new_pairs:
            return 0
        by_item: Dict[int, List[Dict[str, Any]]] = {}
        for pair in new_pairs:
            by_item.setdefault(pair["item_sid"], []).append(pair)
        gated = 0
        for item_sid, pairs in by_item.items():
            try:
                mentions = [{"entity": p["entity_name"]} for p in pairs]
                verdicts = self.gate_agenda_item(
                    item_sid, pairs[0]["item_name"], mentions)
                for p in pairs:
                    self.write_verdicts(
                        assoc_table,
                        [{"entity_id": p["entity_id"],
                          "entity_name": p["entity_name"],
                          "item_sid": item_sid}],
                        verdicts, entity_col)
                    gated += 1
            except Exception as exc:  # noqa: BLE001 - permissive fallback
                logger.warning("agenda-item gate failed (%s/%s): %s",
                               assoc_table, item_sid, exc)
        return gated

    # -- verdict persistence --------------------------------------------------

    def write_verdicts(self, assoc_table: str, rows: List[Dict[str, Any]],
                       verdicts: Dict[str, Dict[str, str]],
                       entity_col: str) -> int:
        """Update gate columns on *rows* ({entity_id, file_id|item_sid}).
        Returns the number of updated rows."""
        if not rows:
            return 0
        model_name = self.model or "summary(default)"
        updated = 0
        with self.engine.begin() as conn:
            for row in rows:
                v = verdicts.get(row["entity_name"]) or {}
                status = v.get("verdict", "unsure")
                reason = v.get("reason", "")
                if "file_id" in row:
                    stmt = text(
                        f'UPDATE "{assoc_table}" SET gate_status = :s, '
                        'gate_reason = :r, gated_at = :t, gate_model = :m '
                        f'WHERE {entity_col} = :eid AND file_id = :fid'
                    )
                    params = {"eid": row["entity_id"], "fid": row["file_id"]}
                else:
                    stmt = text(
                        f'UPDATE "{assoc_table}" SET gate_status = :s, '
                        'gate_reason = :r, gated_at = :t, gate_model = :m '
                        f'WHERE {entity_col} = :eid AND agendaitem_id = :iid'
                    )
                    params = {"eid": row["entity_id"], "iid": row["item_sid"]}
                conn.execute(stmt, {**params, "s": status, "r": reason,
                                    "t": datetime.now(timezone.utc),
                                    "m": model_name})
                updated += 1
        return updated
