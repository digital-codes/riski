# TagManager — PostgreSQL Tag Management via SQLAlchemy

## Overview

`TagManager` provides a lightweight, table‑agnostic tagging system for any
PostgreSQL table that has an `oparlKey` column. The tag data lives in two
dynamically created tables:

| Table | Purpose |
|---|---|
| `{item_table}_tags` | Tag catalog (`id`, `tag`) |
| `{item_table}_tags_assoc` | Many‑to‑many link (`id`, `tag_id` → `tags.id`, `oparl_key`) |

The **item table is never modified** — all metadata is kept in these two
supplementary tables.

## Quick start

```python
from sqlalchemy import create_engine
from tag_manager import TagManager

engine = create_engine("postgresql://user:pass@localhost/db", future=True)

# Create tables + seed initial tags
tm = TagManager(engine, "meetings", tags=["public", "private"])

# Tag an item
tm.add_tags("oparl:abc123", ["public"])

# Find items with ALL of the given tags
tm.find_items_with_all_tags(["public", "internal"])

# Find items with ANY of the given tags
tm.find_items_with_any_tag(["public", "urgent"])

# Read tags for an item
tm.get_tags_for_item("oparl:abc123")

# Add new tags to the catalog (no associations yet)
tm.add_tags_to_catalog(["internal", "urgent"])

# Remove tags + all their associations
tm.remove_tags_from_catalog(["private"])
```

## Constructor

```python
TagManager(engine, item_table, tags=None)
```

| Argument | Type | Description |
|---|---|---|
| `engine` | `Engine` | SQLAlchemy engine (PostgreSQL). |
| `item_table` | `str` | Name of the item table (must exist, must have `oparlKey`). |
| `tags` | `list[str]` | If provided, the tag & association tables are created (if missing) and seeded. If `None`, the tables must already exist. |

Raises `ValueError` when required tables are missing.

## Public API

### `add_tags(oparl_key, tags)`

Associate one or more tags with an item. New tag names are inserted into the
catalog automatically. Duplicate associations are silently ignored.

### `find_items_with_all_tags(tags) → list[str]`

Return `oparlKey` values whose items have **every** tag in the list.
Uses `GROUP BY` / `HAVING` for correctness.

### `find_items_with_any_tag(tags) → list[str]`

Return *distinct* `oparlKey` values whose items have **at least one** of the
given tags.

### `get_tags_for_item(oparl_key) → list[str]`

Return all tag names for an item, sorted alphabetically.

### `add_tags_to_catalog(tags)`

Insert new tag names into the catalog table. Already‑present names are
skipped (idempotent).

### `remove_tags_from_catalog(tags)`

Delete the given tag names **and** every association row that references
them. Non‑existent names are ignored.

## Running the tests

```bash
# The test suite creates/drops test_items, test_items_tags,
# and test_items_tags_assoc.
DATABASE_URL=postgresql://user:pass@localhost/db pytest test_tag_manager.py -v
```

**Database user must have** `CREATE TABLE` / `DROP TABLE` privileges.

## Test coverage

All 20 tests pass against PostgreSQL.  The test suite (`test_tag_manager.py`) covers the following scenarios:

| Class | Tests | What is verified |
|---|---|---|
| **TestTagManagerInit** | 4 | Table creation with/without tag list, error on missing item table, error on missing tag tables |
| **TestAddTags** | 3 | Single and multi-tag association, auto-creation of new tag names |
| **TestFindItemsWithAllTags** | 3 | `AND` match returns correct items, empty when any tag is missing from catalog |
| **TestFindItemsWithAnyTag** | 2 | `OR` match returns distinct items, empty list returns empty |
| **TestGetTagsForItem** | 2 | Unknown key returns empty list, returned tags are sorted |
| **TestAddTagsToCatalog** | 2 | Adding new tags works, duplicate add is idempotent |
| **TestRemoveTagsFromCatalog** | 3 | Removing a tag also removes its associations, nonexistent tag is safe, tag is gone from catalog |
| **TestIntegration** | 1 | Full workflow: multi-tag add, `AND` query, catalog removal, add-then-associate new tags |

The `item_table` fixture seeds 10 random items into a temporary `test_items` table.
The `tm` fixture creates a `TagManager` seeded with tags `["red", "green", "blue"]`
and pre-assigns each item one of `[red]`, `[green]`, `[blue]`, or `[red, green]`
(cycling), ensuring every test starts with known tag-item associations.

## Table naming convention

Given an item table named `documents`:

- Tag table → `documents_tags`
- Association table → `documents_tags_assoc`

This keeps the namespace predictable and avoids collisions when multiple
item tables are tagged independently in the same database.

## Design notes

- The item table's `oparlKey` column is a plain string column in the
  association table, **not** a foreign key. This keeps `TagManager`
  fully decoupled from the item table schema.
- Foreign key on `tag_id` uses `ON DELETE CASCADE` for database‑level
  referential integrity.
- `remove_tags_from_catalog` also removes associations explicitly
  (not relying solely on `CASCADE`) so the behaviour is consistent even
  on databases without FK enforcement.
- Sessions are created via `sessionmaker(bind=engine)` stored as
  `self._session_factory`, following the SQLAlchemy 1.4+ idiomatic
  pattern.  All database interactions use
  `with self._session_factory() as session:`.
