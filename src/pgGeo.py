"""Georeference collection for map views (change: add-map-view).

Streets and districts are linked to agenda items via the association
tables built by `pgAddStreetRefs` / `pgAddDistrictRefs`; their geometries
live in `Street.geo` / `District.geo` as GeoJSON FeatureCollection bytes,
already in WGS84 (spike 1.1 — no reprojection needed).

`collect_geo` turns a set of agenda-item oparlKeys into one GeoJSON
FeatureCollection for the map: each feature of a linked street/district
gets `properties: {name, type, agendaItems}` — the names let the map
render popups, the agendaItems trace back to the answer set.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import json
from typing import Any, Dict, Iterable, List

from sqlalchemy import MetaData, Table, select

EMPTY_FEATURE_COLLECTION = {"type": "FeatureCollection", "features": []}


def _agenda_item_sids(engine, keys: Iterable[str]) -> Dict[str, int]:
    """Resolve agenda-item oparlKeys to sids (unknown keys silently dropped)."""
    keys = [k for k in keys if k]
    if not keys:
        return {}
    agenda = Table("AgendaItem", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        rows = conn.execute(
            select(agenda.c.sid, agenda.c.oparlKey).where(agenda.c.oparlKey.in_(keys))
        ).all()
    return {row.oparlKey: row.sid for row in rows}


def geo_available_for_keys(engine, agenda_item_keys: Iterable[str]) -> bool:
    """True when any of the agenda items is linked to a street or district
    with geometry (single cheap existence check)."""
    sids = _agenda_item_sids(engine, agenda_item_keys)
    if not sids:
        return False
    import sqlalchemy as sa

    with engine.connect() as conn:
        for assoc in ("Streets_items_AgendaItems", "Districts_items_AgendaItems"):
            tbl = Table(assoc, MetaData(), autoload_with=conn)
            n = conn.execute(
                select(sa.func.count()).select_from(tbl).where(tbl.c.agendaitem_id.in_(set(sids.values())))
            ).scalar()
            if n:
                return True
    return False


def _linked_features(
    engine,
    assoc_name: str,
    entity_table: str,
    entity_type: str,
    sids: set,
) -> List[Dict[str, Any]]:
    """Features of all streets/districts linked to the given agenda items.

    Each entity's stored FeatureCollection is parsed and its features are
    re-tagged with {name, type, agendaItems}.
    """
    if not sids:
        return []
    metadata = MetaData()
    assoc = Table(assoc_name, metadata, autoload_with=engine)
    entity = Table(entity_table, metadata, autoload_with=engine)
    agenda = Table("AgendaItem", metadata, autoload_with=engine)

    with engine.connect() as conn:
        rows = conn.execute(
            select(entity.c.id, entity.c.name, entity.c.geo, agenda.c.oparlKey)
            .select_from(
                assoc.join(entity, assoc.c[f"{entity_type.lower()}_id"] == entity.c.id)
                .join(agenda, assoc.c.agendaitem_id == agenda.c.sid)
            )
            .where(assoc.c.agendaitem_id.in_(sids))
        ).all()

    features: List[Dict[str, Any]] = []
    # group links per entity so agendaItems accumulate across agenda items
    per_entity: Dict[int, Dict[str, Any]] = {}
    for entity_id, name, geo, agenda_key in rows:
        entry = per_entity.setdefault(entity_id, {"name": name, "agendaItems": set(), "geo": geo})
        if agenda_key:
            entry["agendaItems"].add(agenda_key)

    for entity_id, entry in per_entity.items():
        if not entry["geo"]:
            continue
        try:
            fc = json.loads(bytes(entry["geo"]))
        except (ValueError, TypeError):
            continue
        for feature in fc.get("features", []):
            feature.setdefault("properties", {})
            feature["properties"]["name"] = entry["name"]
            feature["properties"]["type"] = entity_type
            feature["properties"]["agendaItems"] = sorted(entry["agendaItems"])
            features.append(feature)
    return features


def collect_geo(engine, agenda_item_keys: Iterable[str]) -> Dict[str, Any]:
    """GeoJSON FeatureCollection for the streets/districts linked to the
    given agenda items (WGS84, ready for Leaflet)."""
    sids = set(_agenda_item_sids(engine, agenda_item_keys).values())
    if not sids:
        return dict(EMPTY_FEATURE_COLLECTION)

    features = []
    features += _linked_features(engine, "Streets_items_AgendaItems", "Street", "street", sids)
    features += _linked_features(engine, "Districts_items_AgendaItems", "District", "district", sids)
    return {"type": "FeatureCollection", "features": features}
