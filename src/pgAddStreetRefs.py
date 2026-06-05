from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Table, MetaData, select, Column, Integer, String, DateTime, inspect, create_engine
)

# Import helper to create DB engine
from sqlalchemy import create_engine as sa_create_engine  # needed for openDb


# Copied from refs
def openDb():
    # type: (...) -> Any
    """Create and return a SQLAlchemy engine based on `private` settings.

    The `private` module defines the variables `RO_USER`, `RO_PWD`,
    `DB_HOST`, and `DB_NAME`. This function builds the PostgreSQL URL and
    returns an engine with `future=True` and connection pooling enabled.

    Returns:
        Engine configured with database connection parameters.
    """
    try:
        import private as pr

        db_url = (
            f"postgresql+psycopg2://{pr.DB_USER}:{pr.DB_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
        )
    except ImportError as exc:
        raise ImportError(
            "Could not import private for DB connection settings"
        ) from exc

    return sa_create_engine(db_url, future=True, pool_pre_ping=True)


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


def add_street_agendaitem_refs(street_table, agendaitem_table):
    # type: (Table, Table) -> int
    """Process all agenda items for all streets and add name matches.

    This function finds all pairs where a street name appears in an agenda item name
    and adds entries to the Streets_items_AgendaItems table.

    Args:
        street_table: SQLAlchemy Table object for Street table
        agendaitem_table: SQLAlchemy Table object for AgendaItem table

    Returns:
        Number of new references inserted
    """
    engine = openDb()
    metadata = MetaData()

    # Ensure we have the correct table reference
    street_table = Table("Street", metadata, autoload_with=engine)
    agendaitem_table = Table("AgendaItem", metadata, autoload_with=engine)
    ref_table = Table("Streets_items_AgendaItems", metadata, autoload_with=engine)

    with engine.connect() as conn:
        # Get all streets
        street_stmt = select(street_table.c.id, street_table.c.name)
        streets = conn.execute(street_stmt).fetchall()

        # Get all agenda items with their names
        agendaitem_stmt = select(agendaitem_table.c.id, agendaitem_table.c.name)
        agendaitems = conn.execute(agendaitem_stmt).fetchall()

        # For each street, check all agenda items
        inserted_count = 0
        for street_row in streets:
            street_id = street_row.id
            street_name = street_row.name
            if not street_name:
                continue

            for agendaitem_row in agendaitems:
                agendaitem_id = agendaitem_row.id
                agendaitem_name = agendaitem_row.name
                if not agendaitem_name:
                    continue

                # Check if street name is present in agenda item name
                # Case-insensitive match
                if street_name.lower() in agendaitem_name.lower():
                    # Avoid duplicates
                    check_stmt = select(ref_table.c.id).where(
                        ref_table.c.street_id == street_id
                    ).where(
                        ref_table.c.agendaitem_id == agendaitem_id
                    )
                    existing = conn.execute(check_stmt).fetchone()
                    if not existing:
                        insert_stmt = ref_table.insert().values(
                            street_id=street_id,
                            agendaitem_id=agendaitem_id,
                            name_match=agendaitem_name,
                            created_at=datetime.now(timezone.utc)
                        )
                        conn.execute(insert_stmt)
                        inserted_count += 1

        conn.commit()
        return inserted_count


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
    count = add_street_agendaitem_refs(street_table, agendaitem_table)
    print(f"Added {count} street-agendaitem references")


if __name__ == "__main__":
    main()
