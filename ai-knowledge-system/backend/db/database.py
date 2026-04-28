from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import asyncio

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from sqlalchemy.engine import make_url
from config import settings

# Normalization and Engine Creation
_url = settings.DATABASE_URL
is_sqlite = _url.startswith("sqlite")

if not is_sqlite:
    if _url.startswith("postgresql://"):
        _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif _url.startswith("postgres://"):
        _url = _url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Postgres specific SSL/Pooler normalization
    parsed = make_url(_url)
    query = dict(parsed.query)
    if "sslmode" in query:
        sslmode = query.pop("sslmode")
        if sslmode:
            query["ssl"] = sslmode
    query.pop("channel_binding", None)
    _url = parsed.set(query=query).render_as_string(hide_password=False)

    engine = create_async_engine(
        _url, 
        echo=settings.DEBUG, 
        pool_pre_ping=True,
        connect_args={"command_timeout": 60}
    )
else:
    # SQLite basic engine
    engine = create_async_engine(_url, echo=settings.DEBUG)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db():
    if is_sqlite:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[DB] Local SQLite Database ready")
        return

    retry_delay = 30
    attempt = 1
    while True:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
            print("[DB] Cloud Database ready")
            return
        except Exception as e:
            print(f"[DB WARNING] Database connection attempt {attempt} failed: {repr(e)}. Retrying in {retry_delay}s...")
            attempt += 1
            await asyncio.sleep(retry_delay)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
