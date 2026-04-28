from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

# Explicitly load .env to ensure stability on this system
load_dotenv()

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Knowledge System"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./knowledge_base.db"

    # LLM
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "groq"           # Defaulting to Groq for stable local performance

    LLM_MODEL: str = "llama-3.3-70b-versatile"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # News
    NEWS_API_KEY: Optional[str] = None     # newsapi.org
    GNEWS_API_KEY: Optional[str] = None    # gnews.io

    # Web search
    SERPER_API_KEY: Optional[str] = None   # serper.dev
    SERPAPI_API_KEY: Optional[str] = None  # serpapi.com

    # MCP Server
    MCP_SERVER_URL: str = "http://localhost:8002"  # standalone MCP news server

    # Scheduler
    DAILY_FETCH_HOUR: int = 6
    DAILY_FETCH_MINUTE: int = 0
    FETCH_INTERVAL_HOURS: int = 4

    # Limits
    MAX_ARTICLES_PER_RUN: int = 50
    MAX_ARTICLES_PER_CATEGORY: int = 5  # Reduced from 8 to keep DB lean

    class Config:
        env_file = ".env"


settings = Settings()
