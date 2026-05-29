"""
Tests for TagManager against a real PostgreSQL database.

The caller is expected to provide a database URL via the environment
variable ``DATABASE_URL`` (default: ``postgresql://localhost/octest``).

A temporary table ``test_items`` is created for each test run and dropped
afterward.
"""

from __future__ import annotations

import os
import uuid
from typing import Generator, List

# Add ../src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from sqlalchemy import Column, String, Table, create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker


from pgTagMgr import TagManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

try:
    import private as pr
    DATABASE_URL = f"postgresql+psycopg2://{pr.DB_USER}:{pr.DB_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
except (ImportError, KeyError):
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://localhost/octest"
    )   



@pytest.fixture(scope="session")
def engine():
    """Create a SQLAlchemy engine to the test database."""
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def item_table(engine):
    """Create a temporary ``test_items`` table and seed it with random rows.

    The table has at least ``oparlKey`` (text) plus a dummy ``name`` column.
    It is dropped after each test function.
    """
    meta = MetaData()
    tbl = Table(
        "test_items",
        meta,
        Column("id", String(36), primary_key=True),
        Column("oparlKey", String(500), nullable=False),
        Column("name", String(200)),
    )
    meta.create_all(engine, checkfirst=True)

    items = []
    with sessionmaker(bind=engine)() as session:
        for _ in range(10):
            pk = str(uuid.uuid4())
            opk = f"oparl:{uuid.uuid4().hex[:12]}"
            session.execute(
                tbl.insert().values(id=pk, oparlKey=opk, name=f"item_{pk[:8]}")
            )
            items.append(opk)
        session.commit()

    yield tbl
    with sessionmaker(bind=engine)() as session:
        session.execute(text("DROP TABLE IF EXISTS test_items_tags_assoc"))
        session.execute(text("DROP TABLE IF EXISTS test_items_tags CASCADE"))
        session.execute(text("DROP TABLE IF EXISTS test_items CASCADE"))
        session.commit()


@pytest.fixture
def tm(engine, item_table) -> Generator[TagManager, None, None]:
    """Return a TagManager that creates tag + assoc tables automatically.

    The tables are dropped after the test to keep a clean state.
    """
    mgr = TagManager(engine, "test_items", tags=["red", "green", "blue"])
    with sessionmaker(bind=engine)() as session:
        result = session.execute(text("SELECT \"oparlKey\" FROM test_items"))
        keys = [row[0] for row in result]
    for i, key in enumerate(keys):
        tags_for_item = [["red"], ["green"], ["blue"], ["red", "green"]][i % 4]
        mgr.add_tags(key, tags_for_item)
    yield mgr
    with sessionmaker(bind=engine)() as session:
        session.execute(text("DROP TABLE IF EXISTS test_items_tags_assoc"))
        session.execute(text("DROP TABLE IF EXISTS test_items_tags CASCADE"))
        session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTagManagerInit:
    """Tests around construction and table validation."""

    def test_init_with_tags_creates_tables(self, engine, item_table):
        mgr = TagManager(engine, "test_items", tags=["a", "b"])
        assert mgr._table_exists("test_items_tags")
        assert mgr._table_exists("test_items_tags_assoc")

    def test_init_without_tags_raises_when_missing(self, engine, item_table):
        with pytest.raises(ValueError, match="not found"):
            TagManager(engine, "test_items")

    def test_init_without_tags_ok_when_exist(self, engine, item_table):
        # First create them.
        TagManager(engine, "test_items", tags=["x", "y"])
        # Should not raise.
        mgr = TagManager(engine, "test_items")
        assert mgr is not None

    def test_init_raises_on_missing_item_table(self, engine):
        with pytest.raises(ValueError, match="does not exist"):
            TagManager(
                engine, "nonexistent_items", tags=["a"]
            )


class TestAddTags:
    """Adding associations to items."""

    def test_add_single_tag(self, tm: TagManager):
        key = tm.find_items_with_any_tag(["red"])[0]
        tm.add_tags(key, ["green"])
        tags = tm.get_tags_for_item(key)
        assert "green" in tags

    def test_add_multiple_tags(self, tm: TagManager):
        keys = tm.find_items_with_any_tag(["red"])
        key = keys[0]
        tm.add_tags(key, ["green", "blue"])
        tags = tm.get_tags_for_item(key)
        assert "green" in tags
        assert "blue" in tags

    def test_add_new_tag_creates_it(self, tm: TagManager):
        key = tm.find_items_with_any_tag(["red"])[0]
        tm.add_tags(key, ["yellow"])
        assert "yellow" in tm.get_tags_for_item(key)


class TestFindItemsWithAllTags:
    """``AND``-style tag search."""

    def test_no_items_when_none_match(self, tm: TagManager):
        # No item has both "red" and "nonexistent_tag_xyz".
        result = tm.find_items_with_all_tags(["red", "nonexistent_tag_xyz"])
        assert result == []

    def test_items_with_exactly_one_tag(self, tm: TagManager):
        keys = tm.find_items_with_any_tag(["red"])
        if not keys:
            pytest.skip("no items tagged 'red'")
        result = tm.find_items_with_all_tags(["red"])
        assert len(result) == len(keys)

    def test_items_with_multiple_tags(self, tm: TagManager):
        keys = tm.find_items_with_any_tag(["red"])[:2]
        for k in keys:
            tm.add_tags(k, ["green"])
        result = tm.find_items_with_all_tags(["red", "green"])
        for k in keys:
            assert k in result


class TestFindItemsWithAnyTag:
    """``OR``-style tag search."""

    def test_empty_list_returns_empty(self, tm: TagManager):
        assert tm.find_items_with_any_tag([]) == []

    def test_returns_distinct_items(self, tm: TagManager):
        res = tm.find_items_with_any_tag(["red", "green", "blue"])
        assert len(res) == len(set(res))


class TestGetTagsForItem:
    """Retrieving tags for an item."""

    def test_no_tags_returns_empty(self, tm: TagManager):
        # Pick an oparlKey that has no tags yet by using green (assuming
        # green has fewer initial associations).
        keys = tm.find_items_with_any_tag(["green"])
        # Untag an item by removing green from catalog (or use a new key).
        key = f"oparl:{uuid.uuid4().hex[:12]}"
        result = tm.get_tags_for_item(key)
        assert result == []

    def test_returns_sorted_tags(self, tm: TagManager):
        key = tm.find_items_with_any_tag(["red"])[0]
        tm.add_tags(key, ["zebra", "apple", "mango"])
        tags = tm.get_tags_for_item(key)
        assert tags == sorted(tags)


class TestAddTagsToCatalog:
    """Adding new tags to the tag catalog."""

    def test_add_new_tags(self, tm: TagManager):
        tm.add_tags_to_catalog(["purple", "orange"])
        # Now associate one and verify it works.
        keys = tm.find_items_with_any_tag(["red"])
        if keys:
            tm.add_tags(keys[0], ["purple"])
            assert "purple" in tm.get_tags_for_item(keys[0])

    def test_add_duplicate_is_idempotent(self, tm: TagManager):
        tm.add_tags_to_catalog(["violet"])
        tm.add_tags_to_catalog(["violet"])  # should not raise


class TestRemoveTagsFromCatalog:
    """Removing tags from the catalog (cascades to associations)."""

    def test_remove_tag_removes_associations(self, tm: TagManager):
        key = tm.find_items_with_any_tag(["red"])[0]
        tm.add_tags(key, ["green"])
        tm.remove_tags_from_catalog(["green"])
        assert "green" not in tm.get_tags_for_item(key)

    def test_remove_nonexistent_tag(self, tm: TagManager):
        tm.remove_tags_from_catalog(["nonexistent_tag_xyz"])

    def test_tag_no_longer_in_catalog(self, tm: TagManager):
        tm.remove_tags_from_catalog(["blue"])
        ids = tm._resolve_tag_ids(["blue"])
        assert ids == []


class TestIntegration:
    """End-to-end scenario."""

    def test_random_workflow(self, tm: TagManager):
        # Add several tags to a few items.
        keys = tm.find_items_with_any_tag(["red"])[:3]
        for k in keys:
            tm.add_tags(k, ["green", "blue", "cyan"])

        # Check all-tags match.
        assert len(tm.find_items_with_all_tags(["red", "green", "blue"])) == len(keys)

        # Remove "cyan" from catalog and verify it disappears.
        tm.remove_tags_from_catalog(["cyan"])
        for k in keys:
            assert "cyan" not in tm.get_tags_for_item(k)

        # Add a brand-new tag via catalog.
        tm.add_tags_to_catalog(["magenta"])
        for k in keys:
            tm.add_tags(k, ["magenta"])
        for k in keys:
            assert "magenta" in tm.get_tags_for_item(k)
