"""One-shot loader: rebuilds the ``contentEmbeddings`` table from a local .npz file.

Migrated to src: the engine comes from the shared ``src.db`` layer and the
side-effectful module-level code of the original script is now wrapped in a
``rebuild()`` function (only executed via the CLI entry point).

Note:
    sudo -u postgres psql
    \\c riski_agentic
    CREATE EXTENSION vector;
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse

import numpy as np
from sqlalchemy import Column, Integer, String, create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector

from src.db import get_engine

Base = declarative_base()


class Embedding(Base):
    __tablename__ = "contentEmbeddings"
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector


def rebuild(npz_path: str, engine=None, embedding_model=Embedding) -> int:
    """Drop and recreate the embedding table, then bulk-insert from *npz_path*.

    The .npz file must contain ``vectors`` (N x dim float array) and ``files``
    (N file keys). Returns the number of inserted rows.
    """
    engine = engine or get_engine()

    # Drop the table if it exists
    inspector = inspect(engine)
    if inspector.has_table(embedding_model.__tablename__):
        embedding_model.__table__.drop(engine)

    # Create the table
    Base.metadata.create_all(engine, tables=[embedding_model.__table__])

    with np.load(npz_path, allow_pickle=True) as data:
        loaded_vectors = data["vectors"]
        loaded_files = data["files"]
        print(f"Loaded {len(loaded_vectors)} vectors and {len(loaded_files)} files from output.")

    embs = [
        embedding_model(oparlKey=str(int(name)), value=vec)
        for name, vec in zip(loaded_files, loaded_vectors)
    ]

    session = sessionmaker(bind=engine)()
    session.add_all(embs)
    session.commit()
    session.close()
    return len(embs)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Rebuild the contentEmbeddings table from a .npz vector dump."
    )
    ap.add_argument("npz", help="Path to the .npz file with 'vectors' and 'files' arrays")
    args = ap.parse_args()
    rebuild(args.npz)


if __name__ == "__main__":
    main()
