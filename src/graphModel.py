"""OParl graph model (change: add-network-view, tasks 1.1-1.3).

Single source of truth for the entity graph derivable from the OParl
association tables and direct foreign keys (mirrors
``references/postgres/riski-struct.sql``):

- ``ADJACENCY`` — declarative map: node type → relations (target type,
  junction/FK carrier, key columns). Powers graph serialization now and
  the future ``/expand`` API endpoint later; adding a relation type is a
  new map row, not traversal code.
- ``build_graph`` — serializes traversed objects + logged edges into the
  ``graph`` section of the search result (contract in the change design).

Node ids are ``{Type}_{oparlKey}`` — stable across searches so the
frontend can merge by id. Edge ``relation`` values mirror the association
table names; ``via`` records the carrier for provenance/debugging.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from typing import Any, Dict, List, Optional

from src.timing import timed

# ----------------------------------------------------------------------
# Adjacency map (task 1.1)
# ----------------------------------------------------------------------
# Each entry: relation (OParl semantics, source owns it), target node
# type, carrier table, and the key columns inside that carrier.
# "FK:<column>" as carrier means a direct foreign key on the SOURCE row
# pointing at the target's sid.
ADJACENCY: Dict[str, List[Dict[str, str]]] = {
    "Paper": [
        {"relation": "auxiliaryFile", "target": "File", "via": "Paper__auxiliaryFile__File", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "mainFile", "target": "File", "via": "File__paper__Paper", "src_key": "tgtSid", "tgt_key": "srcSid"},
        {"relation": "consultation", "target": "Consultation", "via": "Paper__consultation__Consultation", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "underDirectionOf", "target": "Organization", "via": "Paper__underDirectionOf__Organization", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "subordinatedPaper", "target": "Paper", "via": "Paper__subordinatedPaper__Paper", "src_key": "srcSid", "tgt_key": "tgtSid"},
    ],
    "File": [
        {"relation": "meeting", "target": "Meeting", "via": "File__meeting__Meeting", "src_key": "srcSid", "tgt_key": "tgtSid"},
        # reverse lookups: the relation is owned by the other side, but
        # expanding a File must still find its papers. Edges keep the
        # canonical direction (Paper --relation--> File) so merges never
        # duplicate.
        {"relation": "auxiliaryFile", "target": "Paper", "via": "Paper__auxiliaryFile__File", "src_key": "tgtSid", "tgt_key": "srcSid", "reverse": True},
        {"relation": "mainFile", "target": "Paper", "via": "File__paper__Paper", "src_key": "tgtSid", "tgt_key": "srcSid", "reverse": True},
    ],
    "Meeting": [
        {"relation": "agendaItem", "target": "AgendaItem", "via": "Meeting__agendaItem__AgendaItem", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "auxiliaryFile", "target": "File", "via": "Meeting__auxiliaryFile__File", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "organization", "target": "Organization", "via": "Meeting__organization__Organization", "src_key": "srcSid", "tgt_key": "tgtSid"},
        # files may link to their meeting from the File side (session
        # documents like Tagesordnung/Protokoll); canonical direction stays
        # File --meeting--> Meeting
        {"relation": "meeting", "target": "File", "via": "File__meeting__Meeting", "src_key": "tgtSid", "tgt_key": "srcSid", "reverse": True},
    ],
    "AgendaItem": [
        {"relation": "auxiliaryFile", "target": "File", "via": "AgendaItem__auxiliaryFile__File", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "consultation", "target": "Consultation", "via": "FK:AgendaItem.consultationSid"},
        {"relation": "meeting", "target": "Meeting", "via": "FK:AgendaItem.meetingSid"},
    ],
    "Consultation": [
        {"relation": "organization", "target": "Organization", "via": "Consultation__organization__Organization", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "meeting", "target": "Meeting", "via": "FK:Consultation.meetingSid"},
        {"relation": "paper", "target": "Paper", "via": "FK:Consultation.paperSid"},
        {"relation": "agendaItem", "target": "AgendaItem", "via": "FK:Consultation.agendaItemSid"},
    ],
    "Organization": [],
    "Person": [],  # future: via Membership (2-hop, collapsed to typed edge)
}

# per-type date field precedence for node serialization
_DATE_FIELDS = {
    "Meeting": ("start_date", "end_date"),
    "AgendaItem": ("start_date", "end_date"),
    "Paper": ("date",),
    "File": ("date",),
    "AuxFile": ("date",),
    "Consultation": (),  # no date of its own
    "Organization": (),
}

# per-type attributes worth carrying onto nodes (kept small; additive)
_ATTR_FIELDS = {
    "Paper": ("reference", "paperType"),
    "File": ("fileName", "downloadurl"),
    "AgendaItem": ("number", "result"),
    "Consultation": ("role", "authoritative"),
    "Organization": ("classification", "shortName"),
    "AuxFile": ("fileName",),
}

# Deployment-specific: public calendar page for meetings. The base URL
# lives in a config file (one per deployment, override the path via
# private.py ``MEETING_WEB_URL_FILE`` or env); the graph builder appends
# "termin-<meeting number>". Agenda items link to their TOP anchor on that
# page (falls back to the page when the anchor doesn't exist). When the
# file is missing, no calendar links are generated.
DEFAULT_MEETING_WEB_URL_FILE = "config/meeting_web_url.txt"


def load_meeting_web_base() -> str | None:
    import os

    from src.db import _load_private

    pr = _load_private()
    path = None
    if pr is not None:
        path = getattr(pr, "MEETING_WEB_URL_FILE", None)
    path = path or os.getenv("MEETING_WEB_URL_FILE") or DEFAULT_MEETING_WEB_URL_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            # one URL per file; comment lines (#) and blanks are ignored
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
        return None
    except OSError:
        return None


# Sentinel for "load the calendar base from config" in build_graph
# (passing None explicitly disables calendar links).
_UNSET = object()


def _meeting_web_url(base: str, meeting_key) -> str:
    return base.rstrip("/") + f"/termin-{meeting_key}"


def _web_attrs(obj: Dict[str, Any], node_type: str, meeting_key_by_sid: Dict[int, Any],
               web_base: str | None) -> Dict[str, Any]:
    """Calendar links: Meeting -> its termin page; AgendaItem -> termin page
    with its TOP anchor; Consultation -> the termin page it belongs to."""
    attrs: Dict[str, Any] = {}
    if web_base is None:
        return attrs
    if node_type == "Meeting" and obj.get("oparlKey") is not None:
        attrs["webUrl"] = _meeting_web_url(web_base, obj["oparlKey"])
    elif node_type in ("AgendaItem", "Consultation"):
        meeting_key = meeting_key_by_sid.get(obj.get("meetingSid"))
        if meeting_key:
            url = _meeting_web_url(web_base, meeting_key)
            if node_type == "AgendaItem" and obj.get("number"):
                url += f"#dtop{obj['number']}"
            attrs["webUrl"] = url
    return attrs


def node_id(node_type: str, oparl_key) -> str:
    return f"{node_type}_{oparl_key}"


def _pick_date(obj: Dict[str, Any], node_type: str) -> Optional[str]:
    for field in _DATE_FIELDS.get(node_type, ()):
        value = obj.get(field)
        if value:
            return str(value)
    return None


def _pick_attrs(obj: Dict[str, Any], node_type: str) -> Dict[str, Any]:
    return {k: obj[k] for k in _ATTR_FIELDS.get(node_type, ()) if obj.get(k) is not None}


def build_graph(
    related_objects: Dict[str, List[Dict[str, Any]]],
    edges: List[Dict[str, Any]],
    top_files: List[Dict[str, Any]],
    meeting_web_base: Any = _UNSET,
) -> Dict[str, Any]:
    """Serialize the traversed objects + logged edges into the graph contract.

    ``related_objects`` comes from ``find_related_objects``, ``edges`` from
    the edge log built during the same traversal, ``top_files`` from the
    search result (seed File nodes carry their match provenance).
    """
    nodes: Dict[str, Dict[str, Any]] = {}

    def add(node_type: str, obj: Dict[str, Any], attrs: Optional[Dict[str, Any]] = None) -> None:
        key = obj.get("oparlKey")
        if key is None:
            return
        nid = node_id(node_type, key)
        if nid in nodes:
            if attrs:
                nodes[nid].setdefault("attrs", {}).update(
                    {k: v for k, v in attrs.items() if v is not None}
                )
            return
        nodes[nid] = {
            "id": nid,
            "type": node_type,
            "oparlKey": str(key),
            "name": obj.get("name") or obj.get("fileName") or f"{node_type} {obj.get('id', key)}",
            "date": _pick_date(obj, node_type),
            "oparlId": obj.get("oparlId"),
            "attrs": {k: v for k, v in (attrs or {}).items() if v is not None},
        }

    # seed File nodes (search hits) carry their match provenance + download
    for f in top_files:
        add("File", f, attrs={
            "distance": f.get("distance"),
            "match": f.get("match"),
            "downloadurl": f.get("downloadurl"),
            "fileName": f.get("fileName"),
        })

    meeting_key_by_sid = {
        m.get("sid"): m.get("oparlKey") for m in related_objects.get("Meeting", [])
    }
    web_base = load_meeting_web_base() if meeting_web_base is _UNSET else meeting_web_base

    for node_type, objs in related_objects.items():
        for obj in objs:
            attrs = _pick_attrs(obj, node_type)
            attrs.update(_web_attrs(obj, node_type, meeting_key_by_sid, web_base))
            add(node_type, obj, attrs=attrs)

    # dedupe edges while preserving traversal order
    seen: set = set()
    out_edges: List[Dict[str, Any]] = []
    for e in edges:
        key = (e["source"], e["target"], e["relation"])
        if key in seen:
            continue
        seen.add(key)
        out_edges.append({
            "source": e["source"],
            "target": e["target"],
            "relation": e["relation"],
            "via": e.get("via"),
        })

    return {"nodes": list(nodes.values()), "edges": out_edges}


# ----------------------------------------------------------------------
# Generic neighborhood expansion (used by the /expand API endpoint)
# ----------------------------------------------------------------------
def parse_node_id(node_id_str: str) -> tuple[str, str]:
    """Split ``{Type}_{oparlKey}`` back into (type, oparl_key)."""
    type_, _, key = node_id_str.partition("_")
    if not type_ or not key:
        raise ValueError(f"Invalid node id {node_id_str!r}; expected '{{Type}}_{{oparlKey}}'")
    return type_, key


def _table_columns(conn, table: str) -> set:
    from sqlalchemy import inspect as sa_inspect

    return {c["name"] for c in sa_inspect(conn).get_columns(table)}


def _select_fields(tbl) -> List[Any]:
    """Columns for a generic neighbor fetch, taken from the shared Table
    object (mixing Table objects of the same name duplicates the FROM)."""
    wanted = ["sid", "id", "oparlKey", "oparlId", "name", "fileName",
              "date", "start_date", "end_date", "reference", "papertype",
              "number", "result", "role", "authoritative", "classification", "shortname", "downloadurl"]
    return [tbl.c[c] for c in wanted if c in tbl.c]


def _objs_from_rows(node_type: str, rows) -> List[Dict[str, Any]]:
    """Convert generic neighbor rows into the object dicts build_graph expects."""
    out = []
    for row in rows:
        obj = dict(row._mapping)
        obj["paperType"] = obj.pop("papertype", None)
        obj["shortName"] = obj.pop("shortname", None)
        if not obj.get("name"):
            obj["name"] = obj.get("fileName")
        out.append(obj)
    return out


@timed
def expand_neighbors(engine, node_id_str: str, limit_per_relation: int = 25) -> Dict[str, Any]:
    """Depth-1 neighborhood of a node, driven purely by ``ADJACENCY``.

    Returns a partial graph ``{"nodes": [...], "edges": [...]}`` — additive
    to any existing graph (client merges by node id). This is the same
    vocabulary the initial traversal logs; new relation types arrive as
    map rows, not code.
    """
    import sqlalchemy as sa
    from sqlalchemy import MetaData, Table, select

    node_type, oparl_key = parse_node_id(node_id_str)
    if node_type not in ADJACENCY or not ADJACENCY[node_type]:
        raise ValueError(f"No adjacency defined for node type {node_type!r}")

    metadata = MetaData()
    with engine.connect() as conn:
        item = Table(node_type, metadata, autoload_with=conn)
        row = conn.execute(
            select(item.c.sid).where(item.c.oparlKey == oparl_key).limit(1)
        ).first()
        if row is None:
            raise ValueError(f"Node {node_id_str!r} not found in table {node_type}")
        item_sid = row.sid

        edges: List[Dict[str, Any]] = []
        collected: Dict[str, List[Dict[str, Any]]] = {}

        for rel in ADJACENCY[node_type]:
            relation, target = rel["relation"], rel["target"]
            tgt_table = Table(target, metadata, autoload_with=conn)
            via = rel["via"]

            if via.startswith("FK:"):
                # direct FK on the SOURCE row pointing at the target's sid
                col_name = via.split(".", 1)[1]
                if col_name not in _table_columns(conn, node_type):
                    continue
                fk_row = conn.execute(
                    select(item.c[col_name]).where(item.c.sid == item_sid)
                ).first()
                neighbor_sids = [fk_row[0]] if fk_row and fk_row[0] is not None else []
                stmt = select(*_select_fields(tgt_table)).where(tgt_table.c.sid.in_(neighbor_sids))
                via_label = via
            else:
                # junction table; rel["src_key"] locates THIS node, rel["tgt_key"] the neighbor
                carrier = Table(via, metadata, autoload_with=conn)
                src_col = carrier.c[rel["src_key"]]
                tgt_col = carrier.c[rel["tgt_key"]]
                sub = select(tgt_col).where(src_col == item_sid).limit(limit_per_relation)
                neighbor_sids = [r[0] for r in conn.execute(sub)]
                stmt = select(*_select_fields(tgt_table)).where(tgt_table.c.sid.in_(neighbor_sids))
                via_label = via

            if not neighbor_sids:
                continue
            rows = conn.execute(stmt).fetchall()
            objs = _objs_from_rows(target, rows)
            if not objs:
                continue
            collected.setdefault(target, []).extend(objs)
            reverse = rel.get("reverse", False)
            for obj in objs:
                neighbor_id = node_id(target, obj["oparlKey"])
                own_id = node_id(node_type, oparl_key)
                edges.append({
                    "source": neighbor_id if reverse else own_id,
                    "target": own_id if reverse else neighbor_id,
                    "relation": relation,
                    "via": via_label,
                })

        related: Dict[str, List[Dict[str, Any]]] = {k: v for k, v in collected.items()}
        # source node itself must be present as a node
        src_row = conn.execute(select(*_select_fields(item)).where(item.c.sid == item_sid)).first()
        if src_row is not None:
            related.setdefault(node_type, []).extend(_objs_from_rows(node_type, [src_row]))

    return build_graph(related, edges, [])
