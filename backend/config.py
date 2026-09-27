from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent

# Model used when LLM_MODEL is not set, per provider
DEFAULT_MODELS = {
    "groq":      "llama-3.3-70b-versatile",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",          # unknown/legacy keys in .env must not crash startup
    )

    # App
    APP_NAME: str = "Upily"
    APP_VERSION: str = "5.0.0"
    DEBUG: bool = False
    # Comma-separated list of browser origins allowed to call the API directly
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Database — SQLite for local dev; use Postgres (e.g. Neon) in production
    DATABASE_URL: str = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'upily.db').as_posix()}"

    # LLM
    LLM_PROVIDER: str = "groq"            # groq | openai | anthropic
    LLM_MODEL: Optional[str] = None       # defaults per provider, see DEFAULT_MODELS
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: float = 30.0

    # News sources (all optional — RSS works without keys)
    GNEWS_API_KEY: Optional[str] = None    # gnews.io
    NEWS_API_KEY: Optional[str] = None     # newsapi.org
    SERPAPI_API_KEY: Optional[str] = None  # serpapi.com (trending page)

    # Web search for chat (optional — DuckDuckGo fallback)
    SERPER_API_KEY: Optional[str] = None   # serper.dev

    # Protects admin-only endpoints (manual pipeline run, manual article edits).
    # Leave empty to disable those endpoints entirely.
    ADMIN_API_KEY: Optional[str] = None

    # Pipeline
    FETCH_INTERVAL_HOURS: int = 4
    RUN_PIPELINE_ON_STARTUP: bool = True   # only runs if stored news is older than the interval
    FRESHNESS_HOURS: int = 24              # ignore articles published longer ago than this
    RETENTION_HOURS: int = 48              # delete stored articles older than this
    ARTICLES_PER_CATEGORY: int = 6         # new articles stored per category per run
    MAX_STORED_PER_CATEGORY: int = 30      # hard cap per category after cleanup
    REFRESH_COOLDOWN_SECONDS: int = 300    # min gap between manual refreshes of one category

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _normalize_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in DEFAULT_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}")
        return v

    @property
    def llm_model(self) -> str:
        return self.LLM_MODEL or DEFAULT_MODELS[self.LLM_PROVIDER]

    @property
    def llm_api_key(self) -> Optional[str]:
        return {
            "groq":      self.GROQ_API_KEY,
            "openai":    self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
        }[self.LLM_PROVIDER]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
