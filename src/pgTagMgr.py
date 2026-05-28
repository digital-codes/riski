"""
TagManager — SQLAlchemy-based tag management for PostgreSQL.

Provides a tag table, an association table linking tags to items
(via the item's ``oparlKey`` column), and CRUD-style operations.
"""

from __future__ import annotations

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

from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ID_COL = Column("id", Integer, primary_key=True, autoincrement=True)
_TAG_NAME_COL = Column("tag", String(255), nullable=False, unique=True)
_OPAL_KEY_COL = "oparlKey"


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _make_tag_table(name: str) -> Table:
    """Build a ``Table`` for the tag entity.

    Parameters
    ----------
    name : str
        Fully qualified table name (may include schema).

    Returns
    -------
    Table
        A SQLAlchemy ``Table`` with columns ``id`` and ``tag``.
    """
    return Table(
        name,
        Base.metadata,
        _ID_COL,
        _TAG_NAME_COL,
        extend_existing=True,
    )


def _make_assoc_table(tag_table_name: str, item_table_name: str) -> Table:
    """Build the many-to-many association table.

    Parameters
    ----------
    tag_table_name : str
        Name of the tag table (used to derive the association table name).
    item_table_name : str
        Name of the item table (for the FK constraint name only; the actual
        column ``oparlKey`` is *not* a foreign key because the item table is
        considered external and is never touched).

    Returns
    -------
    Table
        A SQLAlchemy ``Table`` with columns ``id``, ``tag_id`` (FK to tag
        table), and ``oparl_key`` (plain string).
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TagManager:
    """Manage tags for an external item table over PostgreSQL.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine bound to a PostgreSQL database.
    item_table : str
        Name of the item table (e.g. ``"test_items"``).  This table must
        exist and have a column ``oparlKey``.
    tags : list[str] | None
        Optional list of tag names to insert into the tag table.  When
        provided, both the tag table and the association table will be
        created (if they do not already exist).  When ``None`` the caller
        guarantees those tables already exist---an error is raised otherwise.

    Raises
    ------
    ValueError
        If *tags* is ``None`` and the required tables are missing, or if the
        item table does not exist.
    """

    def __init__(
        self,
        engine: Engine,
        item_table: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine)
        self._item_table_name = item_table

        # Derive table names from the item table name.
        self._tag_table_name = f"{item_table}_tags"
        self._assoc_table_name = f"{self._tag_table_name}_assoc"

        # ---- Validate that the item table exists -------------------------
        if not self._table_exists(item_table):
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
            if not self._table_exists(self._tag_table_name):
                raise ValueError(
                    f"Tag table {self._tag_table_name!r} not found; "
                    "provide a tag list to create it."
                )
            if not self._table_exists(self._assoc_table_name):
                raise ValueError(
                    f"Association table {self._assoc_table_name!r} not found; "
                    "provide a tag list to create it."
                )
            self._tag_table = _make_tag_table(self._tag_table_name)
            self._assoc_table = _make_assoc_table(
                self._tag_table_name, item_table
            )
            # Bind the existing tables to the metadata.
            Base.metadata.create_all(self._engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def add_tags(self, oparl_key: str, tags: List[str]) -> None:
        """Associate one or more tags with an item identified by *oparl_key*.

        Tags that are not already in the tag table are inserted first.
        Duplicate associations are silently ignored.

        Parameters
        ----------
        oparl_key : str
            Value of the item's ``oparlKey`` column.
        tags : list[str]
            Tag names to associate.
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

        Parameters
        ----------
        tags : list[str]
            Tag names that must all be present.

        Returns
        -------
        list[str]
            Matching ``oparlKey`` values.
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
        """Return ``oparlKey`` values of items that have **any** of the tags.

        Parameters
        ----------
        tags : list[str]
            Tag names to search for (at least one must match).

        Returns
        -------
        list[str]
            Matching ``oparlKey`` values (distinct).
        """
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
        """Return all tag names associated with the given item.

        Parameters
        ----------
        oparl_key : str
            The item's ``oparlKey`` value.

        Returns
        -------
        list[str]
            Tag names (sorted alphabetically).
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
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]

    def add_tags_to_catalog(self, tags: List[str]) -> None:
        """Add new tag names to the tag catalog (if not already present).

        Parameters
        ----------
        tags : list[str]
            Tag names to insert.  Duplicates are ignored.
        """
        self._ensure_tags_exist(tags)

    def remove_tags_from_catalog(self, tags: List[str]) -> None:
        """Remove tag names **and** all their associations from the database.

        Parameters
        ----------
        tags : list[str]
            Tag names to delete.
        """
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

    def _table_exists(self, name: str) -> bool:
        """Check if a table exists in the current database."""
        with self._engine.connect() as conn:
            return conn.dialect.has_table(conn, name)

    def _ensure_tags_exist(self, tags: Sequence[str]) -> None:
        """Insert tags that are not yet in the tag table (idempotent).

        Uses a simple check-then-insert approach that works across all
        dialects supported by SQLAlchemy 1.4.
        """
        with self._session_factory() as session:
            for tag in tags:
                already = session.execute(
                    select(exists().where(self._tag_table.c.tag == tag))
                ).scalar()
                if not already:
                    session.execute(self._tag_table.insert().values(tag=tag))
            session.commit()

    def _resolve_tag_ids(self, tags: Sequence[str]) -> List[int]:
        """Return the primary key values for the given tag names.

        Returns an empty list when *tags* is empty or none of the names
        exist in the database.
        """
        if not tags:
            return []
        stmt = (
            select(self._tag_table.c.id)
            .where(self._tag_table.c.tag.in_(tags))
        )
        with self._session_factory() as session:
            return [row[0] for row in session.execute(stmt).all()]
