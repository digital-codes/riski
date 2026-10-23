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

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Float,
    String,
    Table,
    delete,
    exists,
    inspect,
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

# Provenance columns on association rows (additive on-demand migration,
# see TagManager.__init__): facet scheme, derivation source, confidence.
_VALID_SOURCES = {"papertype", "oparl-keyword", "name-regex", "llm", "manual"}


def _make_tag_table(name: str) -> Table:
    """Build a ``Table`` for the tag entity.

    Columns are created fresh per call: module-level ``Column`` objects can
    only be assigned to a single ``Table``, which breaks constructing tag
    tables for multiple item tables in one process.
    """
    return Table(
        name,
        Base.metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tag", String(255), nullable=False, unique=True),
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
        # Fresh Column objects per call — see _make_tag_table.
        Column("scheme", String(64), nullable=True),
        Column("source", String(32), nullable=True),
        Column("confidence", Float, nullable=False, server_default="1.0"),
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

        self._migrate_assoc_columns()

    def _migrate_assoc_columns(self) -> None:
        """Add the provenance columns to existing association tables.

        ``create_all`` never alters existing tables, so previously created
        ``*_tags_assoc`` tables are migrated on demand with additive
        ``ADD COLUMN IF NOT EXISTS`` statements. New tables already carry
        the columns; the guard keeps that case a cheap no-op.
        """
        insp = inspect(self._engine)
        cols = {c["name"] for c in insp.get_columns(self._assoc_table_name)}
        stmts = []
        if "scheme" not in cols:
            stmts.append(f'ALTER TABLE "{self._assoc_table_name}" ADD COLUMN IF NOT EXISTS scheme VARCHAR(64)')
        if "source" not in cols:
            stmts.append(f'ALTER TABLE "{self._assoc_table_name}" ADD COLUMN IF NOT EXISTS source VARCHAR(32)')
        if "confidence" not in cols:
            stmts.append(
                f'ALTER TABLE "{self._assoc_table_name}" ADD COLUMN IF NOT EXISTS confidence REAL NOT NULL DEFAULT 1.0'
            )
        if stmts:
            with self._engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def add_tags(
        self,
        oparl_key: str,
        tags: List[str],
        scheme: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 1.0,
    ) -> None:
        """Associate one or more tags with an item identified by *oparl_key*.

        Tags that are not already in the tag table are inserted first.
        Duplicate associations are silently ignored. When *scheme* is given,
        the association is scheme-scoped: the same tag name may exist under
        several schemes as separate associations.

        *source* must be one of ``_VALID_SOURCES`` (papertype, oparl-keyword,
        name-regex, llm, manual) or None; *confidence* defaults to 1.0.
        """
        if source is not None and source not in _VALID_SOURCES:
            raise ValueError(
                f"Invalid tag source {source!r}; expected one of {sorted(_VALID_SOURCES)}"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1], got {confidence!r}")

        self._ensure_tags_exist(tags)
        tag_ids = self._resolve_tag_ids(tags)
        with self._session_factory() as session:
            for tid in tag_ids:
                dup_filter = [
                    self._assoc_table.c.tag_id == tid,
                    self._assoc_table.c.oparl_key == oparl_key,
                ]
                if scheme is None:
                    dup_filter.append(self._assoc_table.c.scheme.is_(None))
                else:
                    dup_filter.append(self._assoc_table.c.scheme == scheme)
                already = session.execute(
                    select(exists().where(*dup_filter))
                ).scalar()
                if not already:
                    session.execute(
                        self._assoc_table.insert().values(
                            tag_id=tid,
                            oparl_key=oparl_key,
                            scheme=scheme,
                            source=source,
                            confidence=confidence,
                        )
                    )
            session.commit()

    @staticmethod
    def _scheme_filter(scheme_column, scheme: Optional[str]):
        """No-op for ``scheme=None`` (all associations); equality otherwise."""
        return [] if scheme is None else [scheme_column == scheme]

    def find_items_with_all_tags(
        self, tags: List[str], scheme: Optional[str] = None
    ) -> List[str]:
        """Return ``oparlKey`` values of items that have **every** tag listed.

        Uses ``GROUP BY`` / ``HAVING`` counting for correctness. With
        *scheme* set, only associations under that scheme count.
        """
        tag_ids = self._resolve_tag_ids(tags)
        if len(tag_ids) != len(tags):
            return []

        stmt = (
            select(self._assoc_table.c.oparl_key)
            .where(self._assoc_table.c.tag_id.in_(tag_ids))
            .group_by(self._assoc_table.c.oparl_key)
            .having(text(f"count(distinct tag_id) = {len(tag_ids)}"))
        )
        for f in self._scheme_filter(self._assoc_table.c.scheme, scheme):
            stmt = stmt.where(f)
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def find_items_with_any_tag(
        self, tags: List[str], scheme: Optional[str] = None
    ) -> List[str]:
        """Return ``oparlKey`` values of items that have **any** of the tags.

        With *scheme* set, only associations under that scheme count.
        """
        tag_ids = self._resolve_tag_ids(tags)
        if not tag_ids:
            return []

        stmt = (
            select(self._assoc_table.c.oparl_key)
            .where(self._assoc_table.c.tag_id.in_(tag_ids))
            .distinct()
        )
        for f in self._scheme_filter(self._assoc_table.c.scheme, scheme):
            stmt = stmt.where(f)
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def get_tags_for_item(
        self, oparl_key: str, scheme: Optional[str] = None
    ) -> List[str]:
        """Return all tag names associated with the given item (sorted).

        With *scheme* set, only tags associated under that scheme are
        returned.
        """
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
        for f in self._scheme_filter(self._assoc_table.c.scheme, scheme):
            stmt = stmt.where(f)
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def get_tag_details_for_item(
        self, oparl_key: str, scheme: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return association metadata for the item's tags.

        Each entry has ``tag``, ``scheme``, ``source`` and ``confidence``;
        legacy rows yield ``scheme=None``, ``source=None``, ``confidence=1.0``.
        """
        stmt = (
            select(
                self._tag_table.c.tag,
                self._assoc_table.c.scheme,
                self._assoc_table.c.source,
                self._assoc_table.c.confidence,
            )
            .select_from(
                self._assoc_table.join(
                    self._tag_table,
                    self._assoc_table.c.tag_id == self._tag_table.c.id,
                )
            )
            .where(self._assoc_table.c.oparl_key == oparl_key)
            .order_by(self._tag_table.c.tag)
        )
        for f in self._scheme_filter(self._assoc_table.c.scheme, scheme):
            stmt = stmt.where(f)
        with self._session_factory() as session:
            return [
                {
                    "tag": row.tag,
                    "scheme": row.scheme,
                    "source": row.source,
                    "confidence": row.confidence,
                }
                for row in session.execute(stmt).all()
            ]

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
