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


def _file_sids(engine, keys: Iterable[str]) -> Dict[str, int]:
    """Resolve File oparlKeys to sids (unknown keys silently dropped)."""
    keys = [k for k in keys if k]
    if not keys:
        return {}
    f = Table("File", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        rows = conn.execute(select(f.c.sid, f.c.oparlKey).where(f.c.oparlKey.in_(keys))).all()
    return {row.oparlKey: row.sid for row in rows}


def geo_available_for_keys(engine, agenda_item_keys: Iterable[str], file_keys: Iterable[str] = ()) -> bool:
    """True when any of the agenda items or files is linked to a street or
    district with geometry (single cheap existence check per table)."""
    agenda_sids = set(_agenda_item_sids(engine, agenda_item_keys).values())
    file_sids = set(_file_sids(engine, file_keys).values())
    if not agenda_sids and not file_sids:
        return False
    import sqlalchemy as sa

    with engine.connect() as conn:
        checks = [
            ("Streets_items_AgendaItems", "agendaitem_id", agenda_sids),
            ("Districts_items_AgendaItems", "agendaitem_id", agenda_sids),
            ("Streets_items_Files", "file_id", file_sids),
            ("Districts_items_Files", "file_id", file_sids),
        ]
        for assoc_name, col, ids in checks:
            if not ids or not _has_table(conn, assoc_name):
                continue
            tbl = Table(assoc_name, MetaData(), autoload_with=conn)
            n = conn.execute(
                select(sa.func.count()).select_from(tbl).where(tbl.c[col].in_(ids))
            ).scalar()
            if n:
                return True
    return False


def _has_table(conn, name: str) -> bool:
    import sqlalchemy as sa

    return sa.inspect(conn).has_table(name)


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


def _linked_file_features(
    engine,
    assoc_name: str,
    entity_table: str,
    entity_type: str,
    file_sids: set,
) -> List[Dict[str, Any]]:
    """Features of streets/districts linked directly to Files."""
    if not file_sids:
        return []
    metadata = MetaData()
    assoc = Table(assoc_name, metadata, autoload_with=engine)
    entity = Table(entity_table, metadata, autoload_with=engine)
    file_tbl = Table("File", metadata, autoload_with=engine)

    with engine.connect() as conn:
        rows = conn.execute(
            select(entity.c.id, entity.c.name, entity.c.geo, file_tbl.c.oparlKey)
            .select_from(
                assoc.join(entity, assoc.c[f"{entity_type.lower()}_id"] == entity.c.id)
                .join(file_tbl, assoc.c.file_id == file_tbl.c.sid)
            )
            .where(assoc.c.file_id.in_(file_sids))
        ).all()

    features: List[Dict[str, Any]] = []
    per_entity: Dict[int, Dict[str, Any]] = {}
    for entity_id, name, geo, file_key in rows:
        entry = per_entity.setdefault(entity_id, {"name": name, "files": set(), "geo": geo})
        if file_key:
            entry["files"].add(file_key)

    for entry in per_entity.values():
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
            feature["properties"]["files"] = sorted(entry["files"])
            features.append(feature)
    return features


def collect_geo(engine, agenda_item_keys: Iterable[str], file_keys: Iterable[str] = ()) -> Dict[str, Any]:
    """GeoJSON FeatureCollection for the streets/districts linked to the
    given agenda items AND files (WGS84, ready for Leaflet)."""
    agenda_sids = set(_agenda_item_sids(engine, agenda_item_keys).values())
    file_sids = set(_file_sids(engine, file_keys).values())
    features: List[Dict[str, Any]] = []
    features += _linked_features(engine, "Streets_items_AgendaItems", "Street", "street", agenda_sids)
    features += _linked_features(engine, "Districts_items_AgendaItems", "District", "district", agenda_sids)
    features += _linked_file_features(engine, "Streets_items_Files", "Street", "street", file_sids)
    features += _linked_file_features(engine, "Districts_items_Files", "District", "district", file_sids)
    return {"type": "FeatureCollection", "features": features}
