import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Isolated settings for every test run — must be set before `config` is imported
_DB = BACKEND / "tests" / ".test.db"
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_DB.as_posix()}",
    "RUN_PIPELINE_ON_STARTUP": "false",
    "LLM_PROVIDER": "groq",
    "GROQ_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "GNEWS_API_KEY": "",
    "NEWS_API_KEY": "",
    "SERPAPI_API_KEY": "",
    "SERPER_API_KEY": "",
    "TWELVE_DATA_API_KEY": "",
    "ADMIN_API_KEY": "test-admin-token",
})


@pytest.fixture(scope="session", autouse=True)
def _clean_db():
    if _DB.exists():
        _DB.unlink()
    yield
    if _DB.exists():
        try:
            _DB.unlink()
        except PermissionError:
            pass
