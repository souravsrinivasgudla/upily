import asyncio
import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

log = logging.getLogger(__name__)


def _normalize_url(raw: str) -> str:
    """Accept plain postgres:// URLs (Neon, Render, Heroku style) and adapt them for asyncpg."""
    if raw.startswith("sqlite"):
        return raw
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = make_url(raw)
    query = dict(parsed.query)
    # asyncpg uses `ssl` instead of libpq's `sslmode`, and doesn't know channel_binding
    sslmode = query.pop("sslmode", None)
    if sslmode:
        query["ssl"] = sslmode
    query.pop("channel_binding", None)
    return parsed.set(query=query).render_as_string(hide_password=False)


DATABASE_URL = _normalize_url(settings.DATABASE_URL)
_url = DATABASE_URL
is_sqlite = _url.startswith("sqlite")
BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "0001"

if is_sqlite:
    engine = create_async_engine(_url, echo=settings.DEBUG)
else:
    engine = create_async_engine(
        _url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        connect_args={"command_timeout": 60},
    )

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


def _migrate(sync_conn) -> None:
    """Bring the schema to the latest Alembic revision (runs inside the app's connection)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = sync_conn

    tables = inspect(sync_conn).get_table_names()
    if "articles" in tables and "alembic_version" not in tables:
        # Created by create_all before migrations existed — its schema is the baseline
        log.info("Existing database without migration history: stamping baseline %s", BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")


async def init_db(max_attempts: int = 5, retry_delay: float = 5.0) -> None:
    """Run migrations. Retries a few times (cold-starting cloud DBs), then fails loudly."""
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(_migrate)
            log.info("Database ready (%s, migrations at head)", "sqlite" if is_sqlite else "postgres")
            return
        except Exception as e:
            if attempt == max_attempts:
                log.error("Database unavailable after %d attempts", attempt)
                raise
            log.warning("Database setup attempt %d failed (%s); retrying in %.0fs",
                        attempt, type(e).__name__, retry_delay)
            await asyncio.sleep(retry_delay)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
