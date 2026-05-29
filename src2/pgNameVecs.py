"""
NameVecs — unified embedding manager (migrated to src2).

Original implementation lived in ``src/pgNameVecs.py`` and built its own
SQLAlchemy engine plus a bespoke ``_embed`` method that called the remote
embedding endpoint directly.  The refactored version reuses the shared
``src2.db`` utilities for engine/session handling and the centralised
``src2.remote.embed`` helper for the LLM call.
"""

from __future__ import annotations

import numpy as np

from sqlalchemy import Column, String, Table, delete, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# ----------------------------------------------------------------------
# Shared utilities
# ----------------------------------------------------------------------
from src2.db import get_engine, Base, table_exists
from src2.remote import embed

# ----------------------------------------------------------------------
# Constants – unchanged from original
# ----------------------------------------------------------------------
_DIM = 1024


def _make_vec_table(name: str) -> Table:
    """Create a table definition for storing vectors keyed by ``oparl_key``."""
    return Table(
        name,
        Base.metadata,
        Column("oparl_key", String(500), primary_key=True),
        Column("embedding", "VECTOR", nullable=False),  # pgvector type – SQLAlchemy will resolve via ``Vector`` from pgvector at runtime
        extend_existing=True,
    )


class NameVecs:
    """Manage text embeddings as pgvector vectors.

    Parameters are identical to the original class, but the ``engine`` argument is
    optional – if omitted the singleton engine from ``src2.db`` is used.
    """

    DIM = _DIM

    def __init__(
        self,
        item_table: str,
        embedding_url: str | None = None,
        embedding_model: str | None = None,
        api_key: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        # The URL / model / key are no longer stored; ``remote.embed`` reads the
        # configuration from environment variables.
        self._engine = engine or get_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._item_table_name = item_table
        self._vec_table_name = f"{item_table}_name_vecs"

        if not table_exists(item_table):
            raise ValueError(
                f"Item table {item_table!r} does not exist in the database."
            )

        # ``Vector`` type from pgvector is imported lazily to avoid import errors when
        # the extension is not installed (the tests may mock it).
        from pgvector.sqlalchemy import Vector  # type: ignore

        self._vec_table = Table(
            self._vec_table_name,
            Base.metadata,
            Column("oparl_key", String(500), primary_key=True),
            Column("embedding", Vector(self.DIM), nullable=False),
            extend_existing=True,
        )
        Base.metadata.create_all(self._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Public API – unchanged semantics
    # ------------------------------------------------------------------
    def upsert(self, oparl_key: str, text: str) -> None:
        """Insert or update the vector for *oparl_key* by embedding *text*."""
        vec = embed(text)  # centralised embedding call
        with self._session_factory() as session:
            existing = session.execute(
                select(self._vec_table).where(self._vec_table.c.oparl_key == oparl_key)
            ).first()
            if existing is None:
                session.execute(
                    self._vec_table.insert().values(oparl_key=oparl_key, embedding=vec)
                )
            else:
                session.execute(
                    self._vec_table.update()
                    .where(self._vec_table.c.oparl_key == oparl_key)
                    .values(embedding=vec)
                )
            session.commit()

    def remove(self, oparl_key: str) -> None:
        """Delete the vector for *oparl_key*."""
        with self._session_factory() as session:
            session.execute(
                delete(self._vec_table).where(self._vec_table.c.oparl_key == oparl_key)
            )
            session.commit()

    def find_similar(
        self,
        text: str,
        k: int = 5,
        cutoff: float = 0.4,
    ) -> list[tuple[str, float]]:
        """Return the *k* most similar items to *text* using cosine similarity.

        The underlying SQL uses the ``<=>`` operator provided by the pgvector
        extension.  Results are filtered by *cutoff* and ordered by highest
        similarity first.
        """
        query_vec = embed(text)
        distance_col = self._vec_table.c.embedding.cosine_distance(query_vec)
        stmt = (
            select(
                self._vec_table.c.oparl_key,
                (1 - distance_col).label("similarity"),
            )
            .where(distance_col < 1 - cutoff)
            .order_by(distance_col.asc())
            .limit(k)
        )
        with self._session_factory() as session:
            rows = session.execute(stmt).all()
        return [(row.oparl_key, float(row.similarity)) for row in rows]
