from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import Table, MetaData, select, Column, Integer, String, DateTime, LargeBinary, inspect
from sqlalchemy import func

# Import helper to create DB engine
from sqlalchemy import create_engine  # needed for openDb

import geopandas as gp

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
    parser = argparse.ArgumentParser(description="Query the database for recent entries.")
    parser.add_argument("-i","--input_file", help="Path to districts geojson file", default=None)
    args = parser.parse_args()

    if not args.input_file:
        print("Please provide an input file with districts geojson using -i or --input_file")
        return

    engine = openDb()
    metadata = MetaData()

    # Check if District table exists, create if not
    inspector = inspect(engine)
    if "District" not in inspector.get_table_names():
        district_table = Table(
            "District",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(255), nullable=False, unique=True),
            Column("number", Integer, nullable=True),
            Column("timestamp", DateTime, default=lambda: datetime.now(timezone.utc)),
            Column("geo", LargeBinary, nullable=True),
        )
        metadata.create_all(engine)
    else:
        district_table = Table("District", metadata, autoload_with=engine)

    df = gp.read_file(args.input_file)

    with engine.connect() as conn:
        for n in list(df.NAME.values):
            g = df[df.NAME == n]
            stmt = district_table.insert().values(
                name=n,
                number=g.NUMMER.iloc[0],
                geo=g.to_json().encode("utf-8"),
                timestamp=datetime.now(timezone.utc)
            )
            conn.execute(stmt)
        conn.commit()


if __name__ == "__main__":
    main()  