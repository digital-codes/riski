"""
NameVecs — Manage text embeddings as pgvector vectors in PostgreSQL.

Stores 1024-dimensional ``vector`` type values (pgvector extension) keyed
by ``oparlKey`` in a table named ``{item_table}_name_vecs``.  Embeddings
are fetched from an OpenAI-compatible API, normalized to unit length, and
searched via the ``<=>`` cosine-distance operator.
"""

from __future__ import annotations

from typing import Any, List, Tuple

import numpy as np
import requests
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    String,
    Table,
    delete,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class NameVecs:
    """Manage text embeddings as pgvector vectors.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine bound to a PostgreSQL database with the
        ``vector`` extension installed.
    item_table : str
        Name of the item table (must exist, must have an ``oparlKey``
        column).  This table is never modified.
    embedding_url : str
        URL of an OpenAI-compatible embedding endpoint.
    embedding_model : str
        Model name (e.g. ``"text-embedding-3-small"``, ``"bge-m3-Q4_K_M"``).
    api_key : str
        API key for the embedding endpoint.
    """

    DIM = 1024

    def __init__(
        self,
        engine: Engine,
        item_table: str,
        embedding_url: str,
        embedding_model: str,
        api_key: str,
    ) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine)
        self._item_table_name = item_table
        self._vec_table_name = f"{item_table}_name_vecs"
        self._embedding_url = embedding_url.rstrip("/")
        self._embedding_model = embedding_model
        self._api_key = api_key

        if not self._table_exists(item_table):
            raise ValueError(
                f"Item table {item_table!r} does not exist in the database."
            )

        self._vec_table = Table(
            self._vec_table_name,
            Base.metadata,
            Column("oparl_key", String(500), primary_key=True),
            Column("embedding", Vector(self.DIM), nullable=False),
            extend_existing=True,
        )
        Base.metadata.create_all(self._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(self, oparl_key: str, text: str) -> None:
        """Insert or update the vector for *oparl_key* by embedding *text*.

        Parameters
        ----------
        oparl_key : str
            The item's ``oparlKey`` value.
        text : str
            Source text to embed.
        """
        vec = self._embed(text)
        with self._session_factory() as session:
            existing = session.execute(
                select(self._vec_table).where(
                    self._vec_table.c.oparl_key == oparl_key
                )
            ).first()
            if existing is None:
                session.execute(
                    self._vec_table.insert().values(
                        oparl_key=oparl_key, embedding=vec
                    )
                )
            else:
                session.execute(
                    self._vec_table.update()
                    .where(self._vec_table.c.oparl_key == oparl_key)
                    .values(embedding=vec)
                )
            session.commit()

    def remove(self, oparl_key: str) -> None:
        """Remove the vector entry for *oparl_key*.

        Parameters
        ----------
        oparl_key : str
            The item's ``oparlKey`` value.
        """
        with self._session_factory() as session:
            session.execute(
                delete(self._vec_table).where(
                    self._vec_table.c.oparl_key == oparl_key
                )
            )
            session.commit()

    def find_similar(
        self,
        text: str,
        k: int = 5,
        cutoff: float = 0.4,
    ) -> List[Tuple[str, float]]:
        """Find the *k* most similar items to *text* via cosine similarity.

        Uses the pgvector ``<=>`` (cosine distance) operator.  Results are
        sorted by similarity descending; only entries with similarity
        **>** *cutoff* are returned.

        Parameters
        ----------
        text : str
            Query text to embed.
        k : int
            Maximum number of results (default 5).
        cutoff : float
            Minimum cosine similarity threshold (default 0.4).  Only
            results strictly greater than this value are included.

        Returns
        -------
        list[tuple[str, float]]
            List of ``(oparl_key, similarity)`` pairs, highest similarity
            first.
        """
        query_vec = self._embed(text)

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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _table_exists(self, name: str) -> bool:
        with self._engine.connect() as conn:
            return conn.dialect.has_table(conn, name)

    def _embed(self, text: str) -> np.ndarray:
        """Call the embedding API and return a normalized float64 array."""
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        resp = requests.post(
            f"{self._embedding_url}/embeddings",
            headers=headers,
            json={
                "model": self._embedding_model,
                "input": text,
                "dimensions": self.DIM,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = np.array(data["data"][0]["embedding"], dtype=np.float64)
        norm = np.linalg.norm(raw)
        if norm > 0:
            raw /= norm
        return raw
