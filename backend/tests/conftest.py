import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Isolated settings for every test run — must be set before `config` is imported.
# Default: a throwaway SQLite file. Set TEST_DATABASE_URL to run the suite on PostgreSQL
# (e.g. the `upily_test` database from docker-compose.yml) — it is wiped before each run.
_DB = BACKEND / "tests" / ".test.db"
_TEST_PG = os.environ.get("TEST_DATABASE_URL")
if _TEST_PG and not _TEST_PG.rstrip("/").split("?")[0].endswith("_test"):
    raise SystemExit("TEST_DATABASE_URL must point at a database whose name ends in _test (it gets wiped).")
os.environ.update({
    "DATABASE_URL": _TEST_PG or f"sqlite+aiosqlite:///{_DB.as_posix()}",
    "RUN_PIPELINE_ON_STARTUP": "false",
    "LLM_PROVIDER": "groq",
    "GROQ_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "GNEWS_API_KEY": "",
    "NEWS_API_KEY": "",
    "SERPAPI_API_KEY": "",
    "SERPER_API_KEY": "",
    "TWELVE_DATA_API_KEY": "",
    "ADMIN_API_KEY": "test-admin-token",
})


def _reset_postgres(url: str) -> None:
    import asyncio

    import asyncpg
    from sqlalchemy.engine import make_url

    u = make_url(url)

    async def reset():
        conn = await asyncpg.connect(user=u.username, password=u.password, host=u.host,
                                     port=u.port, database=u.database)
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.close()

    asyncio.run(reset())


@pytest.fixture(scope="session", autouse=True)
def _clean_db():
    if _TEST_PG:
        _reset_postgres(_TEST_PG)
        yield
        return
    if _DB.exists():
        _DB.unlink()
    yield
    if _DB.exists():
        try:
            _DB.unlink()
        except PermissionError:
            pass
