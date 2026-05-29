"""
TagManager — unified PostgreSQL helper (migrated to src2).

Original implementation lived in ``src/pgTagMgr.py`` and instantiated its own
SQLAlchemy engine per instance.  The refactored version uses the shared
``src2.db`` module for engine creation, session handling and table existence
checks.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    delete,
    exists,
    select,
    text,
)
from sqlalchemy.orm import sessionmaker

# ----------------------------------------------------------------------
# Shared DB utilities
# ----------------------------------------------------------------------
from src2.db import get_engine, Base, table_exists

# ----------------------------------------------------------------------
# Constants – unchanged from original
# ----------------------------------------------------------------------
_ID_COL = Column("id", Integer, primary_key=True, autoincrement=True)
_TAG_NAME_COL = Column("tag", String(255), nullable=False, unique=True)
_OPAL_KEY_COL = "oparlKey"


def _make_tag_table(name: str) -> Table:
    """Build a ``Table`` for the tag entity."""
    return Table(
        name,
        Base.metadata,
        _ID_COL,
        _TAG_NAME_COL,
        extend_existing=True,
    )


def _make_assoc_table(tag_table_name: str, item_table_name: str) -> Table:
    """Build the many‑to‑many association table."""
    assoc_name = f"{tag_table_name}_assoc"
    return Table(
        assoc_name,
        Base.metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(
            "tag_id",
            Integer,
            ForeignKey(f"{tag_table_name}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("oparl_key", String(500), nullable=False),
        extend_existing=True,
    )


class TagManager:
    """Manage tags for an external item table over PostgreSQL.

    ``engine`` is now optional – if omitted the singleton engine from
    ``src2.db`` is used.  The public API remains unchanged.
    """

    def __init__(
        self,
        item_table: str,
        tags: Optional[List[str]] = None,
        engine=None,
    ) -> None:
        # Use shared engine if none supplied
        self._engine = engine or get_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._item_table_name = item_table

        # Derive table names from the item table name.
        self._tag_table_name = f"{item_table}_tags"
        self._assoc_table_name = f"{self._tag_table_name}_assoc"

        # ---- Validate that the item table exists -------------------------
        if not table_exists(item_table):
            raise ValueError(
                f"Item table {item_table!r} does not exist in the database."
            )

        # ---- Build (or reflect) tag + assoc tables -----------------------
        if tags is not None:
            # Create tables and seed them with the provided tags.
            self._tag_table = _make_tag_table(self._tag_table_name)
            self._assoc_table = _make_assoc_table(
                self._tag_table_name, item_table
            )
            Base.metadata.create_all(self._engine, checkfirst=True)
            self._ensure_tags_exist(tags)
        else:
            # Reflect existing tables.
            if not table_exists(self._tag_table_name):
                raise ValueError(
                    f"Tag table {self._tag_table_name!r} not found; "
                    "provide a tag list to create it."
                )
            if not table_exists(self._assoc_table_name):
                raise ValueError(
                    f"Association table {self._assoc_table_name!r} not found; "
                    "provide a tag list to create it."
                )
            self._tag_table = _make_tag_table(self._tag_table_name)
            self._assoc_table = _make_assoc_table(
                self._tag_table_name, item_table
            )
            Base.metadata.create_all(self._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Public methods (unchanged logic, but use the shared session factory)
    # ------------------------------------------------------------------
    def add_tags(self, oparl_key: str, tags: List[str]) -> None:
        """Associate one or more tags with an item identified by *oparl_key*."""
        self._ensure_tags_exist(tags)
        tag_ids = self._resolve_tag_ids(tags)
        with self._session_factory() as session:
            for tid in tag_ids:
                already = session.execute(
                    select(
                        exists().where(
                            self._assoc_table.c.tag_id == tid,
                            self._assoc_table.c.oparl_key == oparl_key,
                        )
                    )
                ).scalar()
                if not already:
                    session.execute(
                        self._assoc_table.insert().values(tag_id=tid, oparl_key=oparl_key)
                    )
            session.commit()

    # ------------------------------------------------------------------
    # Helper methods (kept identical, only minor refactoring of queries)
    # ------------------------------------------------------------------
    def _ensure_tags_exist(self, tags: List[str]) -> None:
        existing = set(
            session.execute(
                select(self._tag_table.c.tag).where(self._tag_table.c.tag.in_(tags))
            ).scalars()
        )
        missing = [t for t in tags if t not in existing]
        if missing:
            with self._session_factory() as session:
                session.execute(
                    self._tag_table.insert().values([{"tag": t} for t in missing])
                )
                session.commit()

    def _resolve_tag_ids(self, tags: List[str]) -> List[int]:
        rows = (
            self._session_factory()
            .execute(select(self._tag_table.c.id, self._tag_table.c.tag).where(self._tag_table.c.tag.in_(tags)))
            .all()
        )
        return [row.id for row in rows]
