"""
TagManager — unified PostgreSQL helper (migrated to src).

Original implementation lived in ``src/pgTagMgr.py`` and instantiated its own
SQLAlchemy engine per instance.  The refactored version uses the shared
``src.db`` module for engine creation, session handling and table existence
checks.  The public API is identical to the original; only the constructor
gained an optional ``engine`` argument (defaulting to the shared engine).
"""

from __future__ import annotations

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from typing import List, Optional, Sequence

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
from src.db import get_engine, Base, table_exists

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
    """Build the many-to-many association table.

    The item's ``oparlKey`` column is *not* a foreign key because the item
    table is external and is never touched by the tag manager.
    """
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

    ``engine`` is optional – if omitted the singleton engine from
    ``src.db`` is used.  The public API is unchanged from the original
    ``src/pgTagMgr.py``.
    """

    def __init__(
        self,
        item_table: str,
        tags: Optional[List[str]] = None,
        engine=None,
    ) -> None:
        self._engine = engine or get_engine()
        self._session_factory = sessionmaker(bind=self._engine)
        self._item_table_name = item_table

        # Derive table names from the item table name.
        self._tag_table_name = f"{item_table}_tags"
        self._assoc_table_name = f"{self._tag_table_name}_assoc"

        # ---- Validate that the item table exists -------------------------
        if not table_exists(item_table, engine=self._engine):
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
            if not table_exists(self._tag_table_name, engine=self._engine):
                raise ValueError(
                    f"Tag table {self._tag_table_name!r} not found; "
                    "provide a tag list to create it."
                )
            if not table_exists(self._assoc_table_name, engine=self._engine):
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
    # Public methods
    # ------------------------------------------------------------------

    def add_tags(self, oparl_key: str, tags: List[str]) -> None:
        """Associate one or more tags with an item identified by *oparl_key*.

        Tags that are not already in the tag table are inserted first.
        Duplicate associations are silently ignored.
        """
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
                        self._assoc_table.insert().values(
                            tag_id=tid, oparl_key=oparl_key
                        )
                    )
            session.commit()

    def find_items_with_all_tags(self, tags: List[str]) -> List[str]:
        """Return ``oparlKey`` values of items that have **every** tag listed.

        Uses ``GROUP BY`` / ``HAVING`` counting for correctness.
        """
        tag_ids = self._resolve_tag_ids(tags)
        if len(tag_ids) != len(tags):
            return []

        stmt = (
            select(self._assoc_table.c.oparl_key)
            .where(self._assoc_table.c.tag_id.in_(tag_ids))
            .group_by(self._assoc_table.c.oparl_key)
            .having(
                text(f"count(*) = {len(tag_ids)}")
            )
        )
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def find_items_with_any_tag(self, tags: List[str]) -> List[str]:
        """Return ``oparlKey`` values of items that have **any** of the tags."""
        tag_ids = self._resolve_tag_ids(tags)
        if not tag_ids:
            return []

        stmt = (
            select(self._assoc_table.c.oparl_key)
            .where(self._assoc_table.c.tag_id.in_(tag_ids))
            .distinct()
        )
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def get_tags_for_item(self, oparl_key: str) -> List[str]:
        """Return all tag names associated with the given item (sorted)."""
        stmt = (
            select(self._tag_table.c.tag)
            .select_from(
                self._assoc_table.join(
                    self._tag_table,
                    self._assoc_table.c.tag_id == self._tag_table.c.id,
                )
            )
            .where(self._assoc_table.c.oparl_key == oparl_key)
            .order_by(self._tag_table.c.tag)
        )
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def add_tags_to_catalog(self, tags: List[str]) -> None:
        """Add new tag names to the tag catalog (if not already present)."""
        self._ensure_tags_exist(tags)

    def remove_tags_from_catalog(self, tags: List[str]) -> None:
        """Remove tag names **and** all their associations from the database."""
        tag_ids = self._resolve_tag_ids(tags)
        if not tag_ids:
            return

        with self._session_factory() as session:
            # Remove associations first (FK cascade should handle this, but
            # we are explicit to support databases without FK enforcement).
            session.execute(
                delete(self._assoc_table).where(
                    self._assoc_table.c.tag_id.in_(tag_ids)
                )
            )
            session.execute(
                delete(self._tag_table).where(
                    self._tag_table.c.id.in_(tag_ids)
                )
            )
            session.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_tags_exist(self, tags: Sequence[str]) -> None:
        """Insert tags that are not yet in the tag table (idempotent)."""
        with self._session_factory() as session:
            for tag in tags:
                already = session.execute(
                    select(exists().where(self._tag_table.c.tag == tag))
                ).scalar()
                if not already:
                    session.execute(self._tag_table.insert().values(tag=tag))
            session.commit()

    def _resolve_tag_ids(self, tags: Sequence[str]) -> List[int]:
        """Return the primary key values for the given tag names."""
        if not tags:
            return []
        stmt = (
            select(self._tag_table.c.id)
            .where(self._tag_table.c.tag.in_(tags))
        )
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]
