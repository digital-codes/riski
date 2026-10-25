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

from src.local_geo_matching import name_matches

def openDb():
    """Create and return a SQLAlchemy engine based on the shared DB layer.

    Connection settings are resolved by ``src.db`` (``private.py`` ->
    environment variables -> safe defaults).
    """
    from src.db import get_engine

    return get_engine()


def create_districts_agendaitems_table(engine):
    # type: (Any) -> Table
    """Create the Districts_items_AgendaItems table if it doesn't exist.

    This table links districts to agenda items when a district name appears
    in the agenda item name.

    Args:
        engine: SQLAlchemy Engine instance

    Returns:
        Table object for the created/existing table
    """
    metadata = MetaData()
    inspector = inspect(engine)

    if "Districts_items_AgendaItems" not in inspector.get_table_names():
        table = Table(
            "Districts_items_AgendaItems",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("district_id", Integer, nullable=False),
            Column("agendaitem_id", Integer, nullable=False),
            Column("name_match", String(255), nullable=False),
            Column("created_at", DateTime, default=lambda: datetime.now(timezone.utc)),
        )
        metadata.create_all(engine)
    else:
        table = Table("Districts_items_AgendaItems", metadata, autoload_with=engine)

    return table


def add_district_agendaitem_refs(district_table, agendaitem_table, gate=True):
    # type: (Table, Table, bool) -> int
    """Process all agenda items for all districts and add name matches.

    This function finds all pairs where a district name appears in an agenda item name
    and adds entries to the Districts_items_AgendaItems table.

    Args:
        district_table: SQLAlchemy Table object for District table
        agendaitem_table: SQLAlchemy Table object for AgendaItem table

    Returns:
        Number of new references inserted
    """
    engine = openDb()
    metadata = MetaData()

    # Ensure we have the correct table reference
    district_table = Table("District", metadata, autoload_with=engine)
    agendaitem_table = Table("AgendaItem", metadata, autoload_with=engine)
    ref_table = Table("Districts_items_AgendaItems", metadata, autoload_with=engine)

    with engine.connect() as conn:
        # Get all districts
        district_stmt = select(district_table.c.id, district_table.c.name)
        districts = conn.execute(district_stmt).fetchall()

        # Get all agenda items with their names
        agendaitem_stmt = select(agendaitem_table.c.sid, agendaitem_table.c.name)
        agendaitems = conn.execute(agendaitem_stmt).fetchall()

        # For each district, check all agenda items
        inserted_count = 0
        new_pairs = []  # change: geo-gating — for post-insert gating
        for district_row in districts:
            district_id = district_row.id
            district_name = district_row.name
            if not district_name:
                continue

            for agendaitem_row in agendaitems:
                agendaitem_id = agendaitem_row.sid
                agendaitem_name = agendaitem_row.name
                if not agendaitem_name:
                    continue

                # Boundary-aware literal match: e.g. Weststadt must not match
                # inside Nordweststadt.
                if name_matches(agendaitem_name, district_name):
                    # Check if this exact match already exists
                    check_stmt = select(ref_table.c.id).where(
                        (ref_table.c.district_id == district_id) &
                        (ref_table.c.agendaitem_id == agendaitem_id) &
                        (ref_table.c.name_match == agendaitem_name)
                    )
                    existing = conn.execute(check_stmt).fetchone()
                    if not existing:
                        insert_stmt = ref_table.insert().values(
                            district_id=district_id,
                            agendaitem_id=agendaitem_id,
                            name_match=agendaitem_name,
                            created_at=datetime.now(timezone.utc)
                        )
                        conn.execute(insert_stmt)
                        inserted_count += 1
                        new_pairs.append({
                            "entity_id": int(district_id),
                            "entity_name": district_name,
                            "item_sid": int(agendaitem_id),
                            "item_name": agendaitem_name or "",
                        })

        conn.commit()

        # change: geo-gating — gate the newly inserted links (permissive:
        # gate failures leave rows ungated/visible)
        if gate and new_pairs:
            try:
                from src.geoGate import GeoGate

                GeoGate(engine=engine).gate_agenda_links(
                    "Districts_items_AgendaItems", "district_id", new_pairs)
            except Exception as exc:  # noqa: BLE001
                print(f"  geo gate unavailable ({exc}) — rows left ungated",
                      flush=True)
        return inserted_count


def _no_gate_arg() -> bool:
    import sys as _sys

    return "--no-gate" in _sys.argv


def main():
    # type: () -> None
    """Main entry point for the district-agendaitem reference creator.

    Creates the Districts_items_AgendaItems table if it doesn't exist
    and populates it with all district-agenda item pairs where the district
    name appears in the agenda item name.

    Args:
        None

    Returns:
        None
    """
    engine = openDb()
    metadata = MetaData()

    # Get references to existing tables
    district_table = Table("District", metadata, autoload_with=engine)
    agendaitem_table = Table("AgendaItem", metadata, autoload_with=engine)

    # Create the reference table
    ref_table = create_districts_agendaitems_table(engine)

    # Add references
    count = add_district_agendaitem_refs(
        district_table, agendaitem_table,
        gate=not _no_gate_arg(),
    )
    print(f"Added {count} district-agendaitem references")


if __name__ == "__main__":
    main()
