"""Database engine and session management."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite-specific: allow async access
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Columns added to existing tables after initial model creation. Each tuple
# is (table, column, full column spec). We check PRAGMA table_info and add
# any missing columns so dev databases don't need to be wiped. When the
# project adopts Alembic, move these to versioned migrations and delete.
_COLUMN_BACKFILLS: list[tuple[str, str, str]] = [
    ("cases", "review_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
    # Phase B: reverse link from a vault item back to the EvidenceRequest that
    # spawned it. Nullable — pre-existing items have no source request.
    ("evidence_items", "source_request_id", "VARCHAR(36)"),
    # Phase C: strategic planner lifecycle.
    ("cases", "plan_status", "VARCHAR(20) NOT NULL DEFAULT 'idle'"),
    ("cases", "plan_generated_at", "DATETIME"),
    # Phase D: return-visit tracking.
    ("cases", "last_visited_at", "DATETIME"),
]


async def _apply_column_backfills(conn) -> None:
    """Idempotently ALTER TABLE ADD COLUMN for columns missing on SQLite."""
    if "sqlite" not in settings.database_url:
        return
    for table, column, spec in _COLUMN_BACKFILLS:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result.fetchall()}
        if column not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {spec}"))


async def init_db():
    """Create all tables. Used for dev; production uses Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_column_backfills(conn)
