# 🧠 AI Knowledge System

A personal AI-powered news knowledge system using a multi-agent architecture.
Fetches, understands, stores, explains, and lets you chat about daily news — **no MCP layer**.

---

## Architecture

```
Frontend (React + Vite)
        │
        ▼
FastAPI (REST API)
        │
        ├─► NewsAgent        — fetch + deduplicate + rank articles
        ├─► SummarizerAgent  — AI enrichment (summary / explanation / GK)
        ├─► QAAgent          — answer questions (memory-first, web fallback)
        ├─► TrendAgent       — identify trending topics
        └─► OrchestratorAgent — coordinates the daily pipeline
                │
                ├─► NewsService    — NewsAPI / RSS feeds
                ├─► SearchService  — web search (Serper / DuckDuckGo) + pgvector memory
                └─► LLMService     — OpenAI / Anthropic unified interface
                        │
                        ▼
              PostgreSQL + pgvector
```

---

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 with **pgvector** extension

```bash
# Create DB and enable pgvector
psql -U postgres -c "CREATE DATABASE ai_knowledge;"
psql -U postgres -d ai_knowledge -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Backend

```bash
cd backend

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# → Open .env and add your API keys

uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## API Keys

| Key | Where | Required? |
|---|---|---|
| `OPENAI_API_KEY` | platform.openai.com | ✅ AI features |
| `NEWS_API_KEY` | newsapi.org (free tier) | ⚠️ Optional — RSS fallback available |
| `SERPER_API_KEY` | serper.dev (2500 free/mo) | ⚠️ Optional — DuckDuckGo fallback available |
| `ANTHROPIC_API_KEY` | console.anthropic.com | ⚠️ Alternative to OpenAI |

> **Zero API keys?** The app still works — RSS feeds provide news, and AI responses show a placeholder until a key is set.

---

## Usage

1. Open **http://localhost:3000**
2. Click **Fetch News Now** in the sidebar → pipeline runs in background (~2 min)
3. Browse articles on the **Dashboard** with category filters
4. Click any article for AI-generated summary, deep explanation, and GK background
5. Hit **Ask AI about this article** on the article page for contextual chat
6. Use the **Ask AI** page for open-ended news questions

---

## Project Structure

```
ai-knowledge-system/
├── backend/
│   ├── main.py                     # FastAPI app + lifespan
│   ├── config.py                   # Environment settings
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── agents/
│   │   ├── news_agent.py           # Fetch + importance ranking
│   │   ├── summarizer_agent.py     # AI enrichment per article
│   │   ├── qa_agent.py             # Memory-first Q&A with web fallback
│   │   ├── trend_agent.py          # Trending topic analysis
│   │   └── orchestrator.py        # Daily pipeline coordinator
│   │
│   ├── services/
│   │   ├── news_service.py         # NewsAPI + RSS fetching
│   │   ├── search_service.py       # Web search + pgvector memory search + embeddings
│   │   └── llm_service.py          # Unified OpenAI / Anthropic client
│   │
│   ├── db/
│   │   ├── database.py             # Async SQLAlchemy engine + init
│   │   └── models.py               # Article, QAPair, TrendReport, DailyDigest
│   │
│   ├── api/routes/
│   │   ├── news.py                 # GET /api/news, GET /api/news/:id, POST /api/news/fetch
│   │   ├── chat.py                 # POST /api/chat
│   │   ├── trending.py             # GET /api/trending
│   │   └── health.py               # GET /api/health
│   │
│   └── scheduler/
│       └── daily_pipeline.py       # APScheduler cron (6 AM UTC by default)
│
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── tailwind.config.js
    ├── package.json
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js                  # Axios API client
        ├── index.css
        ├── components/
        │   ├── Layout.jsx          # Sidebar + navigation
        │   ├── ArticleCard.jsx     # News card with category + tags
        │   ├── ChatPanel.jsx       # Reusable chat UI component
        │   └── Spinner.jsx         # Loading spinner
        └── pages/
            ├── Dashboard.jsx       # Article feed with category filter
            ├── ArticlePage.jsx     # Article detail + inline chat
            ├── ChatPage.jsx        # Standalone AI chat
            └── TrendingPage.jsx    # Trends + category bar chart
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/news` | List articles (`?category=&trending=&page=&limit=`) |
| `GET` | `/api/news/{id}` | Single article |
| `POST` | `/api/news/fetch` | Trigger pipeline manually |
| `POST` | `/api/chat` | Ask AI (`{ question, article_id? }`) |
| `GET` | `/api/trending` | Latest trend report |
