from __future__ import annotations

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Table, MetaData, select, Column, Integer, String, DateTime, inspect, create_engine
)

# Import helper to create DB engine
from sqlalchemy import create_engine as sa_create_engine  # needed for openDb

from src.local_geo_matching import prepare_street_matcher


def openDb():
    """Create and return a SQLAlchemy engine based on the shared DB layer.

    Connection settings are resolved by ``src.db`` (``private.py`` ->
    environment variables -> safe defaults).
    """
    from src.db import get_engine

    return get_engine()


def create_streets_agendaitems_table(engine):
    # type: (Any) -> Table
    """Create the Streets_items_AgendaItems table if it doesn't exist.

    This table links streets to agenda items when a street name appears
    in the agenda item name.

    Args:
        engine: SQLAlchemy Engine instance

    Returns:
        Table object for the created/existing table
    """
    metadata = MetaData()
    inspector = inspect(engine)

    if "Streets_items_AgendaItems" not in inspector.get_table_names():
        table = Table(
            "Streets_items_AgendaItems",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("street_id", Integer, nullable=False),
            Column("agendaitem_id", Integer, nullable=False),
            Column("name_match", String(255), nullable=False),
            Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
        )
        metadata.create_all(engine)
    else:
        table = Table("Streets_items_AgendaItems", metadata, autoload_with=engine)

    return table


def add_street_agendaitem_refs(street_table, agendaitem_table, progress_every=500, gate=True):
    # type: (Table, Table, int, bool) -> int
    """Add Street -> AgendaItem relations efficiently.

    Performance characteristics:
    - compile the complete Street vocabulary once into one boundary-aware regex;
    - preload existing relation pairs once instead of SELECT-per-match;
    - batch INSERT and COMMIT every `progress_every` AgendaItems;
    - print progress after each committed batch.

    With *gate* (default), newly inserted links are classified by the LLM
    GeoGate (change: geo-gating) — permissive: gate failures leave the rows
    ungated (visible) for the cleanup pass.
    """
    engine = openDb()
    metadata = MetaData()

    street_table = Table("Street", metadata, autoload_with=engine)
    agendaitem_table = Table("AgendaItem", metadata, autoload_with=engine)
    ref_table = Table("Streets_items_AgendaItems", metadata, autoload_with=engine)

    with engine.connect() as conn:
        streets = [
            (row.id, row.name)
            for row in conn.execute(
                select(street_table.c.id, street_table.c.name)
            ).fetchall()
            if row.name
        ]
        streets_by_id = {sid: name for sid, name in streets}
        matcher = prepare_street_matcher(streets)

        agendaitems = conn.execute(
            select(agendaitem_table.c.sid, agendaitem_table.c.name)
            .order_by(agendaitem_table.c.id)
        ).fetchall()
        total = len(agendaitems)

        existing_pairs = {
            (int(row.street_id), int(row.agendaitem_id))
            for row in conn.execute(
                select(ref_table.c.street_id, ref_table.c.agendaitem_id)
            ).fetchall()
        }

        inserted_count = 0
        pending = []
        new_pairs = []  # change: geo-gating — for post-insert gating
        processed = 0

        for agendaitem_row in agendaitems:
            processed += 1
            agendaitem_id = int(agendaitem_row.sid)
            agendaitem_name = agendaitem_row.name

            if agendaitem_name:
                # The combined regex is longest-first and finditer returns
                # non-overlapping matches, preserving longest-match-wins.
                matches = matcher.matches(agendaitem_name)
                matched_street_ids = []
                seen = set()
                for match in matches:
                    if match.item_id not in seen:
                        seen.add(match.item_id)
                        matched_street_ids.append(match.item_id)

                now = datetime.now(timezone.utc)
                for street_id in matched_street_ids:
                    pair = (int(street_id), agendaitem_id)
                    if pair not in existing_pairs:
                        existing_pairs.add(pair)
                        pending.append({
                            "street_id":street_id,
                            "agendaitem_id":agendaitem_id,
                            "name_match":agendaitem_name,
                            "created_at":now,
                        })
                        new_pairs.append({
                            "entity_id": int(street_id),
                            "entity_name": streets_by_id.get(int(street_id), ""),
                            "item_sid": agendaitem_id,
                            "item_name": agendaitem_name or "",
                        })

            if processed % progress_every == 0:
                if pending:
                    conn.execute(ref_table.insert(), pending)
                    inserted_count += len(pending)
                    conn.commit()
                    pending.clear()
                conn.commit()
                print(
                    f"Processed {processed}/{total} AgendaItems; "
                    f"inserted {inserted_count} street references",
                    flush=True,
                )

        if pending:
            conn.execute(ref_table.insert(), pending)
            inserted_count += len(pending)
            pending.clear()
        conn.commit()

        # change: geo-gating — gate the newly inserted links (permissive:
        # gate failures leave rows ungated/visible)
        if gate and new_pairs:
            try:
                from src.geoGate import GeoGate

                GeoGate(engine=engine).gate_agenda_links(
                    "Streets_items_AgendaItems", "street_id", new_pairs)
            except Exception as exc:  # noqa: BLE001
                print(f"  geo gate unavailable ({exc}) — rows left ungated",
                      flush=True)
        return inserted_count

def _no_gate_arg() -> bool:
    import sys as _sys

    return "--no-gate" in _sys.argv


def main():
    # type: () -> None
    """Main entry point for the street-agendaitem reference creator.

    Creates the Streets_items_AgendaItems table if it doesn't exist
    and populates it with all street-agenda item pairs where the street
    name appears in the agenda item name.

    Args:
        None

    Returns:
        None
    """
    engine = openDb()
    metadata = MetaData()

    # Get references to existing tables
    street_table = Table("Street", metadata, autoload_with=engine)
    agendaitem_table = Table("AgendaItem", metadata, autoload_with=engine)

    # Create the reference table
    ref_table = create_streets_agendaitems_table(engine)

    # Add references
    count = add_street_agendaitem_refs(
        street_table, agendaitem_table,
        gate=not _no_gate_arg(),
    )
    print(f"Added {count} street-agendaitem references")


if __name__ == "__main__":
    main()
