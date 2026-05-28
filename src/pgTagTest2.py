from __future__ import annotations
from typing import List, Sequence, Tuple, Optional
from sqlalchemy import (
BigInteger,
String,
Text,
DateTime,
ForeignKey,
UniqueConstraint,
Index,
func,
select,
literal_column,
)
from sqlalchemy.orm import (
relationship,
declarative_base,
Session,
Mapped,
mapped_column,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert # PostgreSQL‑specific INSERT

Base = declarative_base()
class Item(Base):
    __tablename__ = "test_items"

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationship back‑ref to tags via the association table
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="test_item_tags",
        back_populates="items",
        lazy="selectin",
    )


class Tag(Base):
    __tablename__ = "test_tags"

    id = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name = mapped_column(String, nullable=False)
    slug = mapped_column(String, nullable=False, unique=True)
    description = mapped_column(Text, nullable=True)
    parent_id = mapped_column(
        BigInteger, ForeignKey("test_tags.id", ondelete="SET NULL"), nullable=True
    )

    # self‑referencing relationship for hierarchies
    parent: Mapped[Optional["Tag"]] = relationship(
        "Tag", remote_side=[id], backref="children", lazy="joined"
    )

    # back‑ref to items
    items: Mapped[List[Item]] = relationship(
        "Item", secondary="test_item_tags", back_populates="tags", lazy="selectin"
    )


class ItemTag(Base):
    __tablename__ = "test_item_tags"
    __table_args__ = (
        UniqueConstraint("item_id", "tag_id", name="uq_item_tag"),
    )

    item_id = mapped_column(
        BigInteger, ForeignKey("test_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id = mapped_column(
        BigInteger, ForeignKey("test_tags.id", ondelete="CASCADE"), primary_key=True
    )
    added_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    added_by = mapped_column(BigInteger, nullable=True)   # optional user FK


#----------------------------------------------------------------------
#CRUD helpers
#----------------------------------------------------------------------
def get_or_create_tag(
session: Session,
name: str,
slug: Optional[str] = None,
description: Optional[str] = None,
parent: Optional[Tag] = None,
) -> Tag:
    """Insert a tag if it does not exist (matching on slug)."""
    slug = slug or name.lower().replace(" ", "-")
    stmt = select(Tag).where(Tag.slug == slug)
    tag = session.execute(stmt).scalar_one_or_none()
    if tag:
        if description and tag.description != description:
            tag.description = description
        if parent and tag.parent_id != parent.id:
            tag.parent = parent
        session.add(tag)
        return tag
    tag = Tag(name=name, slug=slug, description=description, parent=parent)
    session.add(tag)
    session.flush()
    return tag


def add_tag_to_item(
session: Session,
item: Item,
tag: Tag,
added_by: Optional[int] = None,
) -> None:
    """Attach a tag to an item, silently ignoring duplicate rows."""
    stmt = (
        pg_insert(ItemTag)
        .values(item_id=item.id, tag_id=tag.id, added_by=added_by)
        .on_conflict_do_nothing(index_elements=["item_id", "tag_id"])
    )
    session.execute(stmt)

def get_tags_for_item(session: Session, item_id: int) -> List[Tag]:
    stmt = (
        select(Tag)
        .join(ItemTag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id == item_id)
    )
    return session.scalars(stmt).all()

def get_items_with_any_tags(session: Session, tag_ids: Sequence[int]) -> List[Item]:
    stmt = (
        select(Item)
        .join(ItemTag, Item.id == ItemTag.item_id)
        .where(ItemTag.tag_id.in_(tag_ids))
        .distinct()
    )
    return session.scalars(stmt).all()

def get_items_with_all_tags(session: Session, tag_ids: Sequence[int]) -> List[Item]:
    tag_count = len(tag_ids)
    subq = (
        select(
            ItemTag.item_id,
            func.count(ItemTag.tag_id).label("matched")
        )
        .where(ItemTag.tag_id.in_(tag_ids))
        .group_by(ItemTag.item_id)
        .having(func.count(ItemTag.tag_id) == tag_count)
        .subquery()
    )
    stmt = select(Item).join(subq, Item.id == subq.c.item_id)
    return session.scalars(stmt).all()

def tag_usage_cloud(session: Session) -> List[Tuple[Tag, int]]:
    stmt = (
        select(Tag, func.count(ItemTag.item_id).label("freq"))
        .outerjoin(ItemTag, Tag.id == ItemTag.tag_id)
        .group_by(Tag.id)
        .order_by(literal_column("freq").desc())
    )
    return session.execute(stmt).all()

def get_items_under_tag_hierarchy(session: Session, root_tag_id: int) -> List[Item]:
    cte = (
        select(Tag.id)
        .where(Tag.id == root_tag_id)
        .cte(name="descendants", recursive=True)
    )
    parent = cte.alias()
    children = select(Tag.id).where(Tag.parent_id == parent.c.id)
    cte = cte.union_all(children)

    stmt = (
        select(Item)
        .join(ItemTag, Item.id == ItemTag.item_id)
        .join(cte, ItemTag.tag_id == cte.c.id)
        .distinct()
    )
    return session.scalars(stmt).all()



#----------------------------------------------------------------------
#Engine / session helpers (adjust DATABASE_URL as needed)
#----------------------------------------------------------------------
# Adjust the URL to match your Postgres credentials
DATABASE_URL = "postgresql+psycopg2://riski:riski@localhost:5432/riski_agentic"
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
#SessionLocal = sessionmaker(bind=engine.engine, expire_on_commit=False)

def demo():
    with SessionLocal() as db:
        print("Creating tables...")
        Base.metadata.drop_all(db.get_bind())  # start fresh
        Base.metadata.create_all(db.get_bind())
        # 1️⃣ Create / fetch tags
        try:
            red = get_or_create_tag(db, name="Red")
            blue = get_or_create_tag(db, name="Blue")
            green = get_or_create_tag(db, name="Green") 
        except Exception as e:
            print("Error creating tags:", e)
            return
        print("Tags created successfully.")
        print(f"Tags created: {red.name} (id={red.id}), {blue.name} (id={blue.id}), {green.name} (id={green.id})")

        # 2️⃣ Create an item (or fetch an existing one)
        item = Item(name="Sample product")
        db.add(item)
        item2 = Item(name="Sample product2")
        db.add(item2)
        item3 = Item(name="Sample product3")
        db.add(item3)
        db.flush()   # obtain item.id

        print(f"Item created: {item.name} (id={item.id})")
        print(f"Item created: {item2.name} (id={item2.id})")
        print(f"Item created: {item3.name} (id={item3.id})")
        print("Current tags for item:", [t.name for t in get_tags_for_item(db, item.id)])  # should be empty
        # 3️⃣ Tag it
        add_tag_to_item(db, item=item, tag=red, added_by=42)
        add_tag_to_item(db, item=item, tag=blue)

        add_tag_to_item(db, item=item2, tag=red)
        add_tag_to_item(db, item=item2, tag=green)
        add_tag_to_item(db, item=item3, tag=blue)

        db.commit()   # persist everything

        # 4️⃣ Query examples
        print("Tags for item:", [t.name for t in get_tags_for_item(db, item.id)])


        print("Items with any of [red, blue]:",
            [i.name for i in get_items_with_any_tags(db, [red.id, blue.id])])
        print("Items with both red AND blue:",
            [i.name for i in get_items_with_all_tags(db, [red.id, blue.id])])
        print("Tag usage cloud:", [(t.slug, cnt) for t, cnt in tag_usage_cloud(db)])
        print("Items under 'Red' hierarchy:",
            [i.name for i in get_items_under_tag_hierarchy(db, red.id)])

if __name__ == "__main__":
    demo()

