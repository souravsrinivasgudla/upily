# Upily

**The day's news: gathered, ranked, explained.**

Upily reads RSS feeds from major newsrooms (BBC, The Guardian, NYT, The Hindu, TechCrunch, FXStreet, ESPN, and AI labs' own blogs such as OpenAI's and Google's) across ten sections, including AI, India and Forex. The Forex section also shows this week's economic calendar from Forex Factory. It ranks stories by importance and writes an AI analysis for each one: a summary, the full context, why it matters, and background. You can also ask follow-up questions about any story.

- **Frontend:** React 18, Vite and Tailwind, styled in a "Newsprint" design system (tokens live in `frontend/tailwind.config.js`).
- **Backend:** FastAPI, SQLAlchemy (async) and APScheduler.
- **LLM:** Groq (default), OpenAI or Anthropic.

---

## Quick start

### Prerequisites

- Python 3.12
- Node.js 20 or newer

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your keys (see below)
uvicorn main:app --reload --port 8000
```

On the first start the backend creates `backend/upily.db` (SQLite) and runs the news pipeline once.

### Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:3000, proxies /api to :8000
```

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

---

## Keys and configuration

All backend settings live in `backend/.env`. See [`backend/.env.example`](backend/.env.example) for the full list.

Real environment variables take precedence over `.env`.

| Variable | Needed for | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | AI analysis, chat, trending topics (**recommended**) | [console.groq.com/keys](https://console.groq.com/keys), free tier |
| `GEMINI_API_KEY` | Backup LLM: takes over automatically while the main provider is rate-limited or down | [aistudio.google.com/apikey](https://aistudio.google.com/apikey), free tier |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Alternatives to Groq; also set `LLM_PROVIDER` | platform.openai.com / console.anthropic.com |
| `GNEWS_API_KEY` | The Pulse (trending); tops up thin RSS sections | [gnews.io](https://gnews.io), 100 requests/day free |
| `SERPAPI_API_KEY` | The Pulse (Google News top stories) | [serpapi.com](https://serpapi.com), 100 searches/month free |
| `NEWS_API_KEY` | Optional extra news source | [newsapi.org](https://newsapi.org); the free tier only works from localhost |
| `TWELVE_DATA_API_KEY` | Optional: real previous close, day range and market status on the Forex tab | [twelvedata.com](https://twelvedata.com), free plan 800 credits/day |
| `SERPER_API_KEY` | Optional better web search in chat (otherwise DuckDuckGo is used) | [serper.dev](https://serper.dev) |
| `ADMIN_API_KEY` | Admin endpoints (see below) | Any long random string |
| `DATABASE_URL` | **Production only:** Postgres | e.g. [neon.tech](https://neon.tech) free tier |

With no keys at all, Upily still works: news comes from RSS and articles show the source excerpt. With only `GROQ_API_KEY`, everything except The Pulse works.

---

## Deployment: Railway (backend + PostgreSQL) and Vercel (frontend)

**1. Railway: database and API**

1. On [railway.com](https://railway.com), choose **New Project → Deploy from GitHub repo** and pick this repo. That creates a service for the backend.
2. In the project, choose **+ New → Database → PostgreSQL**.
3. In the backend service **Settings**:
   - **Root Directory:** `backend`
   - **Config file path:** `/backend/railway.json`. It holds the start command, the `/api/health` health check and the restart policy. The path is absolute because Railway doesn't apply the root directory to it.
   - **Networking → Generate Domain**, which gives e.g. `https://upily-api.up.railway.app`.
4. In the backend service **Variables**, set:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (a reference to the Railway database) |
   | `LLM_PROVIDER` | `groq` |
   | `GROQ_API_KEY` | your Groq key |
   | `GEMINI_API_KEY` | optional backup LLM, used while Groq is rate-limited |
   | `GNEWS_API_KEY` | your GNews key (for The Pulse) |
   | `TWELVE_DATA_API_KEY` | optional (Forex previous close and day range) |
   | `ADMIN_API_KEY` | a long random string |
   | `CORS_ORIGINS` | your Vercel URL, set after step 2 |

   Don't set `PORT`; Railway provides it. Python 3.12.7 comes from `backend/.python-version`.
5. Deploy. On startup the app runs the Alembic migrations, then fetches and analyses the first news batch in the background. Check `https://<your-domain>/api/health`.

**2. Vercel: frontend**

1. **Add New → Project**, import the repo, and set **Root Directory** to `frontend`. Vite is detected automatically.
2. Add the environment variable `VITE_API_URL=https://<your-railway-domain>`, the origin only, without `/api`. The build fails on purpose if it's missing.
3. Deploy, and note the URL, e.g. `https://upily.vercel.app`.

**3. Connect them**

In Railway, set `CORS_ORIGINS=https://<your-vercel-url>` and redeploy the backend. Separate several URLs with commas.

The Groq, GNews and Twelve Data free tiers are shared between your local app and the deployed one when both use the same keys. Stop the local backend, or use separate keys, to keep quota for production.

## API

| Method | Endpoint | Notes |
|---|---|---|
| `GET` | `/api/health` | Status, database check, which features are enabled |
| `GET` | `/api/categories` | The ten sections |
| `GET` | `/api/news` | `?category=&trending=&page=&limit=` (limit up to 50) |
| `GET` | `/api/news/{id}` | One article, with its analysis |
| `POST` | `/api/news/{id}/analyze` | Writes the AI analysis on the server. Returns the saved analysis if it already exists. Rate-limited. |
| `POST` | `/api/news/refresh/{category}` | Adds new stories without deleting any. Rate-limited, with a cooldown per section. |
| `GET` | `/api/calendar` | This week's economic calendar from Forex Factory (`?impact=High,Medium`), cached for 1 hour |
| `GET` | `/api/search` | `?q=` keyword search over stored stories, one result per story group |
| `GET` | `/api/briefing` | Top story per section, an AI editor's note (cached 1h) and high-impact market events in the next 36h |
| `GET` | `/api/rates` | Live indicative rates for 8 major pairs (Coinbase, cached 30 s), with the change since the last ECB reference rate. Falls back to ECB rates if the live source is down (`live: false`) |
| `POST` | `/api/chat` | `{ question, article_id?, history? }`. Rate-limited. |
| `GET` | `/api/trending` | `?force=true` skips the 45-minute cache, at most once every 10 minutes (protects the GNews free quota) |
| `POST` | `/api/admin/pipeline` | Admin only (`X-Admin-Token` header): run the full pipeline now |
| `PATCH` | `/api/news/{id}/enrich` | Admin only: edit an article's analysis by hand |

---

## How the pipeline works

Every `FETCH_INTERVAL_HOURS` (default 4), the pipeline runs these steps for each section:

1. **Fetch** the RSS feeds, topping up from the news APIs when RSS is thin.
2. **Filter out** stories older than `FRESHNESS_HOURS` and stories already stored.
3. **Rank** the rest with the LLM.
4. **Store** the top `ARTICLES_PER_CATEGORY`.
5. **Clean up:** delete stories older than `RETENTION_HOURS` and keep at most `MAX_STORED_PER_CATEGORY` per section.
6. **Group** stories that different outlets wrote about the same event (see below).
7. **Analyse** the new stories. When the LLM provider rate-limits, the client waits as long as the provider asks and retries. The run stops after 3 other LLM failures in a row, so a bad key doesn't waste calls.

Other behaviour:

- On startup, the pipeline runs only if the stored news is older than the interval.
- All writes share one lock, so the scheduled runs and manual refreshes can't collide.

## Reader features

- **Search.** It's in the nav bar, with results at `/search?q=`. It uses the same ranking as the chat's retrieval, so it matches the evaluation harness's numbers.
- **Daily briefing** (`/briefing`). It shows the top story from each section, an AI editor's note written only from those headlines, and the next 36 hours of high-impact economic releases. **Listen** reads it aloud with the browser's built-in speech synthesis and highlights the story being read. No extra service or cost.
- **My Upily** (`/my`). A personal front page built from sections and topics you follow. Preferences are stored in the browser, so no account is needed.
- **Live currency rates** (Forex tab). Eight major pairs. The strip refreshes every 30 seconds while the tab is visible and flashes a pair when it moves. Three sources, each used for what it's good at:
  - **Prices:** Coinbase's public exchange-rates API, refreshed every 30 s. These are indicative mid-market prices; no key is needed.
  - **Previous close, day high/low and market open/closed:** Twelve Data (`TWELVE_DATA_API_KEY`, optional). The free plan allows 800 credits a day and each pair costs one, so quotes refresh every 15 minutes (~770 credits a day), with a hard cap below the limit.
  - **Fallback baseline:** the European Central Bank's daily reference rate, used when Twelve Data isn't configured.
  - If a source fails, the strip falls back and says which source it's showing.

## Local news

`/local` lets readers choose **India → state / union territory → district** from dropdowns. The choice is remembered in the browser and kept in the URL, so it can be shared. The page shows **"In {district}"** and **"Across {state}"**.

- **Locations:** `backend/data/india_districts.json` holds all 36 states and UTs and 780 districts. Each state's count was checked against the official total, including the 2022 Andhra Pradesh and 2024 Rajasthan reorganisations and recent renames.
- **Sources (hybrid):**
  - **Newspaper feeds:** The Hindu's state feeds (AP, Telangana, Karnataka, Kerala, Tamil Nadu) and city feeds from The Hindu and the Times of India. A city feed counts as its district's news; state and city stories that mention a district, including common spellings like Vizag or Anantapur, count for that district.
  - **Google News India:** a search for the district or state, keeping only stories whose headline names the place, and filtering out job-alert, price-listing and race-card pages. These are headline-only and link through a Google redirect.
- **Storage:** stories are stored as category `local` with the location (migration `0003`), so they open in the article page with chat. AI analysis runs only when a local story is opened, to protect the LLM quota. Results are cached per location for 20 minutes, and local stories never appear in the national sections or the ticker.
- **API:**
  - `GET /api/locations/states`
  - `GET /api/locations/districts?state=`
  - `GET /api/local?state=&district=`

## AI

The AI section combines the dedicated AI sections of The Guardian, TechCrunch, The Verge, WIRED, Ars Technica and MIT Technology Review with the official OpenAI and Google AI blogs. Like Forex, it keeps stories for 72 hours, because the labs' blogs post every few days. AI stories can also appear in Technology; AI is an overlapping section, so it never pulls stories out of Technology.

## Forex

- **News:** FXStreet and investingLive (formerly ForexLive). Forex Factory's own news pages block automated readers (Cloudflare returns 403), so Upily doesn't scrape them. Forex stories stay eligible for 72 hours instead of 24, because forex desks go quiet at weekends.
- **Economic calendar:** Forex Factory's official public weekly feed (`nfs.faireconomy.media`). It gives each event's currency, time, impact, forecast and previous value. It's fetched at most once an hour for all visitors, and the last good copy is served if a fetch fails.

## Story grouping

When several outlets cover the same event, Upily shows it once, with an "N outlets" badge and an **Also reported by** list on the article page. The chat's retrieval also returns one hit per story, so its context covers distinct stories.

`services/clustering.py` compares every pair of recent stories. A pair is grouped when all three hold:
- They come from **different outlets**. The same outlet's stories on one topic were the main source of false matches.
- Their headlines share **at least two** terms.
- Their **TF-IDF cosine similarity** (headline weighted double, plus the source's lead text) is at least 0.42.

Groups join transitively (union-find). Each group's id is its smallest article id, so it stays stable as new coverage arrives. The 0.42 threshold was chosen from a sweep over hand-labelled pairs; see the next section.

## Evaluation

`backend/evals/` measures retrieval and grouping quality against a frozen snapshot of stories, so results are reproducible as the live news changes.

```bash
cd backend
python -m evals.run_eval                 # offline: no network, no LLM (~2s)
python -m evals.run_eval --answers 5     # + LLM-graded end-to-end answers
python -m evals.build_dataset            # rebuild the snapshot from the current DB
```

Latest results are in [`backend/evals/results/latest.md`](backend/evals/results/latest.md), and the method and findings are in [`backend/evals/README.md`](backend/evals/README.md). A pytest gate (`tests/test_evals.py`) fails if the scores drop below their floors.

## Local PostgreSQL (Docker) + DBeaver

Local development runs on PostgreSQL 16 in Docker, the same database engine as production.

```bash
cp .env.example .env            # repo root; set a POSTGRES_PASSWORD
docker compose up -d            # PostgreSQL on 127.0.0.1:5433 (5433 avoids clashing with other local Postgres)
# backend/.env:
#   DATABASE_URL=postgresql://upily:<POSTGRES_PASSWORD>@localhost:5433/upily
```

- The backend applies the Alembic migrations on startup, or you can run `alembic upgrade head` yourself.
- Data persists in the `upily-pgdata` Docker volume. `docker compose down -v` deletes it.
- To move stories from an old SQLite file, run `python -m scripts.copy_sqlite_to_postgres` from `backend/`. It keeps ids and resets the id sequence.
- Without `DATABASE_URL`, the backend still falls back to SQLite (`backend/upily.db`).

**DBeaver:** create a new connection with **PostgreSQL** and these settings:

| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `5433` |
| Database | `upily` |
| Username | `upily` |
| Password | `POSTGRES_PASSWORD` from the repo-root `.env` |

The stories are in `public.articles`, and `public.alembic_version` shows the schema revision.

**Tests on PostgreSQL:** the suite runs on SQLite by default. To run it against the `upily_test` database, which is wiped each run, use:

```bash
TEST_DATABASE_URL=postgresql://upily:<password>@localhost:5433/upily_test pytest
```

The suite refuses any database whose name doesn't end in `_test`.

## Database migrations

The schema is managed with **Alembic** (`backend/migrations/`). The app applies pending migrations automatically at startup. A database created before migrations existed is detected and marked as the baseline, so no data is lost.

```bash
cd backend
alembic upgrade head                         # apply migrations
alembic revision --autogenerate -m "add x"   # after changing db/models.py
alembic downgrade -1                         # roll back one step
```

A test (`test_migrations_match_models`) fails if `db/models.py` and the migrations drift apart.

## Project layout

```
backend/
  main.py            FastAPI app, CORS, lifespan
  config.py          Settings (.env)
  api/routes/        news, chat, trending, health
  api/deps.py        Rate limiting and admin-token auth
  agents/            orchestrator (pipeline), news_agent (ranking), summarizer_agent, qa_agent
  services/          news_service (feeds and APIs), llm_service, search_service,
                     clustering (story grouping), dates, text, tasks
  db/                Engine, migrations runner and the Article model
  migrations/        Alembic migrations (0001 baseline, 0002 story groups)
  evals/             Retrieval and grouping evaluation (dataset, runner, results)
  scheduler/         APScheduler job
  tests/             pytest suite, including the evaluation quality gate
frontend/
  src/components/    ui.jsx (design primitives), Layout, Ticker, ArticleCard, ChatPanel, ErrorBoundary
  src/pages/         Dashboard (front page), ArticlePage, TrendingPage (The Pulse), ChatPage
  tailwind.config.js Newsprint design tokens
```
