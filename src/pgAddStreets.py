from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import Table, MetaData, select, Column, Integer, String, DateTime, LargeBinary, inspect
from sqlalchemy import func

# Import helper to create DB engine
from sqlalchemy import create_engine  # needed for openDb

import json

# Copied from refs
def openDb():
    """Create and return a SQLAlchemy engine based on `private` settings.
    The `private` module defines the variables `RO_USER`, `RO_PWD`,
    `DB_HOST`, and `DB_NAME`. This function builds the PostgreSQL URL and
    returns an engine with `future=True` and connection pooling enabled.
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

    return create_engine(db_url, future=True, pool_pre_ping=True)



def main():
    import argparse
    import geopandas as gpd
    parser = argparse.ArgumentParser(description="Query the database for recent entries.")
    parser.add_argument("-i","--input_file", help="Path to street names input file", default=None)
    parser.add_argument("-s","--street_file", help="Path to geojson for streets names", default=None)
    args = parser.parse_args()

    if not args.input_file:
        print("Please provide an input file with street names using -i or --input_file")
        return

    engine = openDb()
    metadata = MetaData()

    # Check if Street table exists, create if not
    inspector = inspect(engine)
    if "Street" not in inspector.get_table_names():
        street_table = Table(
            "Street",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(255), nullable=False, unique=True),
            Column("text", String(255), nullable=False, unique=True),
            Column("year", Integer, nullable=True),
            Column("description", String(4096), nullable=True),
            Column("timestamp", DateTime, default=lambda: datetime.now(timezone.utc)),
            Column("districtName", String(255), nullable=True),
            Column("geo", LargeBinary, nullable=True),
        )
        metadata.create_all(engine)
    else:
        street_table = Table("Street", metadata, autoload_with=engine)

    with open(args.input_file, "r") as f:
        streets = json.load(f)

    if args.street_file:
        gdf = gpd.read_file(args.street_file)
        gdf = gdf.to_crs(epsg=4326)  # Ensure it's in WGS84

    with engine.connect() as conn:
        for street in streets:
            name = street.get("name")
            street_geo = gdf[gdf["name"] == name]
            if street_geo.empty:
                street["geo"] = None
            else:
                street["geo"] = street_geo.to_json()

            stmt = street_table.insert().values(
                name=street.get("name"),
                text=street.get("text"),
                year=street.get("year"),
                geo=bytearray(street.get("geo", "").encode("utf-8")) if street.get("geo") else None,
                timestamp=datetime.now(timezone.utc)
            )
            conn.execute(stmt)
        conn.commit()


if __name__ == "__main__":
    main()  