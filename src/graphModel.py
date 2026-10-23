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
    ],
    "Meeting": [
        {"relation": "agendaItem", "target": "AgendaItem", "via": "Meeting__agendaItem__AgendaItem", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "auxiliaryFile", "target": "File", "via": "Meeting__auxiliaryFile__File", "src_key": "srcSid", "tgt_key": "tgtSid"},
        {"relation": "organization", "target": "Organization", "via": "Meeting__organization__Organization", "src_key": "srcSid", "tgt_key": "tgtSid"},
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
    "AgendaItem": ("number", "result"),
    "Consultation": ("role", "authoritative"),
    "Organization": ("classification", "shortName"),
    "AuxFile": ("fileName",),
}


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
            "name": obj.get("name") or obj.get("fileName") or f"{node_type} {obj.get('id', key)}",
            "date": _pick_date(obj, node_type),
            "oparlId": obj.get("oparlId"),
            "attrs": {k: v for k, v in (attrs or {}).items() if v is not None},
        }

    # seed File nodes (search hits) carry their match provenance
    for f in top_files:
        add("File", f, attrs={
            "distance": f.get("distance"),
            "match": f.get("match"),
        })

    for node_type, objs in related_objects.items():
        for obj in objs:
            add(node_type, obj, attrs=_pick_attrs(obj, node_type))

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
