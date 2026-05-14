# 🤖 AI SEO Agent System

A production-ready, modular AI SEO agent system that crawls websites, identifies ranking opportunities, generates SEO-optimised content, optimises existing pages, and tracks performance over time — all with a continuous feedback loop.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                         │
│        Dashboard · Keywords · Content Review · Analytics        │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP / REST
┌─────────────────────────▼───────────────────────────────────────┐
│                      FastAPI Backend                            │
│   /projects · /keywords · /content · /analytics · /auth        │
└──────┬──────────────────────────────────────────────────────────┘
       │ Celery tasks via Redis Streams
┌──────▼──────────────────────────────────────────────────────────┐
│                        Agent Workers                            │
│                                                                 │
│  Orchestrator → Crawler → Keyword → SERP → ContentGen          │
│                                          → Optimizer           │
│                                                                 │
│  Tracker (daily cron) → Feedback Loop (weekly cron)            │
└──────┬──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                         Data Layer                              │
│  PostgreSQL (structured) · Redis (queue/cache) ·               │
│  ClickHouse (analytics) · MinIO/S3 (content blobs)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Task Queue | Celery + Redis Streams |
| LLM | Claude (Anthropic API) — `claude-sonnet-4-20250514` |
| Crawling | Playwright (JS-rendered), BeautifulSoup, extruct |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local) |
| SERP Data | DataForSEO API |
| GSC Data | Google Search Console API (OAuth2) |
| Database | PostgreSQL 16 |
| Analytics DB | ClickHouse 24 |
| Content Store | MinIO (S3-compatible) |
| Frontend | Next.js 14, React Query, Recharts, Tailwind CSS |
| CMS | WordPress REST API |
| Local Dev | Docker Compose |

---

## Quick start

### Prerequisites

- Docker Desktop (with Compose v2)
- API keys:
  - [Anthropic API key](https://console.anthropic.com)
  - [DataForSEO account](https://dataforseo.com) (login + password)
  - Google Cloud Console project with Search Console API enabled

### 1. Clone and configure

```bash
git clone <repo>
cd seo-agent
cp .env.example .env
# Edit .env and fill in your API keys
```

### 2. One-time setup

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This starts the infrastructure, waits for health checks, and runs DB migrations.

### 3. Start everything

```bash
docker compose up
```

### 4. Seed demo data (optional)

```bash
docker compose run --rm api python scripts/seed.py
```

### 5. Open the apps

| App | URL |
|---|---|
| Frontend dashboard | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Celery Flower (task monitor) | http://localhost:5555 |
| MinIO console (content storage) | http://localhost:9001 |

---

## Agent descriptions

### Orchestrator agent
Entry point for all SEO runs. Decomposes work into a task DAG, dispatches Celery tasks in the correct order, and tracks completion to gate downstream agents.

**Trigger:** `POST /api/v1/projects/{id}/run`

### Crawler agent
Crawls a website using Playwright (JS-rendered pages) and BeautifulSoup. Extracts: title, meta, H-tags, canonical, robots, hreflang, JSON-LD structured data, internal link graph, word count, Core Web Vitals, and a full issue list. Stores normalised records in PostgreSQL.

**Queue:** `crawl` · **Concurrency:** 3 browser workers

### Keyword agent
Pulls 16 months of query-level data from Google Search Console, clusters keywords using sentence-transformer embeddings + AgglomerativeClustering, classifies search intent (informational/commercial/transactional/navigational), and scores each keyword's ranking opportunity (0–100). Persists enriched records to PostgreSQL.

**Queue:** `keywords` · **Schedule:** every 6 hours (GSC refresh)

### SERP analysis agent
Fetches top-10 SERP results per keyword via DataForSEO, then fetches each result page to extract: word count, H2 headings, entities, schema types, People Also Ask questions, and featured snippet presence. Results are cached in Redis for 24 hours.

**Queue:** `serp` · **Rate limit:** 60 req/min

### Content generation agent
Builds a competitive brief (target word count, required entities, PAA questions, competitor H2 gaps) and passes it to Claude API with a structured system prompt. Output is a fully structured JSON article (title, meta, sections, FAQ, schema suggestions). Scores semantic coverage before saving to S3.

**Queue:** `content` · **Rate limit:** 10 req/min

### Content optimizer agent
Analyses existing pages against SERP benchmarks, identifies gaps (word count, schema, topic coverage, entities), and generates a targeted edit-set (not a full rewrite). Each edit includes type, priority, instruction, content suggestion, and rationale. Persists as a ContentVersion for human review.

**Queue:** `optimize`

### Performance tracker agent
Runs daily (6am UTC). Pulls fresh ranking data from GSC, computes position/click/impression deltas vs previous snapshots, writes time-series rows to ClickHouse, and updates 30-day rank-delta on published ContentVersions.

**Queue:** `tracker` · **Schedule:** daily 6am UTC

### Feedback loop agent
Runs weekly (Monday 7am UTC). Joins content edit-types with 30-day rank-delta outcomes, computes which edit types correlate with improvements, and persists a weighted prompt config to S3. This config is read by ContentGen and Optimizer agents to emphasise high-signal edit types in future prompts.

**Queue:** `optimize` · **Schedule:** weekly Monday 7am UTC

---

## Key workflows

### Full analysis run (end-to-end)

```
POST /api/v1/projects/{id}/run
  → Orchestrator creates task DAG
  → Crawler (queue: crawl)
  → Keyword agent (queue: keywords)
  → SERP agent (queue: serp)
  → [parallel] Content gen (queue: content)
              Content optimizer (queue: optimize)
  → Daily tracker picks up new content performance
  → Weekly feedback loop adjusts prompt weights
```

### Manual content approval

```
1. Draft generated → status: draft
2. Human reviews at /content
3. Click Approve → status: approved
4. Click "Send to WordPress" → publishes as draft post
5. Editor reviews in WordPress, clicks Publish
6. Tracker measures rank improvement after 30 days
7. Feedback loop records signal
```

### On-demand keyword content

```
POST /api/v1/projects/{id}/run/content
Body: ["keyword-uuid-1", "keyword-uuid-2"]
  → Dispatches generate_content_task per keyword
  → Returns task IDs for polling
```

---

## Database schema

### PostgreSQL (relational)
- `projects` — websites being managed
- `pages` — crawled pages with all SEO signals
- `keywords` — queries with GSC data, scoring, clustering
- `serp_snapshots` — SERP results per keyword per scrape
- `content_versions` — all content drafts, diffs, and published versions
- `tasks` — agent task lifecycle tracking

### ClickHouse (analytics)
- `rankings_daily` — time-series positions/clicks/impressions per keyword
- `content_performance` — content version performance over time
- `crawl_summaries` — per-crawl audit snapshots
- `feedback_signals` — edit-type → rank-delta correlations

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `DATAFORSEO_LOGIN` | ✅ | DataForSEO login |
| `DATAFORSEO_PASSWORD` | ✅ | DataForSEO password |
| `GSC_CLIENT_ID` | ✅ | Google OAuth2 client ID |
| `GSC_CLIENT_SECRET` | ✅ | Google OAuth2 client secret |
| `SECRET_KEY` | ✅ | 64-char random string for JWT signing |
| `DATABASE_URL` | auto | Set by Docker Compose |
| `REDIS_URL` | auto | Set by Docker Compose |

---

## Adding a new agent

1. Create `backend/agents/my_agent.py` with a class following the `run()` → `dict` pattern
2. Create `backend/workers/tasks/my_tasks.py` with a Celery task wrapping it
3. Register the task in `workers/celery_app.py` under `include` and `task_routes`
4. Add orchestration logic in `agents/orchestrator.py`
5. Add API endpoint in `api/routers/` if user-facing

---

## Production deployment checklist

- [ ] Replace MinIO with AWS S3 (update `S3_ENDPOINT` env var — leave empty for AWS)
- [ ] Switch PostgreSQL to RDS with connection pooling (PgBouncer)
- [ ] Switch Redis to ElastiCache
- [ ] Switch ClickHouse to managed ClickHouse Cloud
- [ ] Set `ENVIRONMENT=production` (disables SQL echo, enables JSON logging)
- [ ] Rotate `SECRET_KEY` to a 64-char random string
- [ ] Enable HTTPS and set correct CORS origins
- [ ] Set up Alembic migration pipeline (do not use `create_all` in production)
- [ ] Configure Celery worker autoscaling
- [ ] Add Sentry for error tracking (insert `sentry_sdk.init()` in `api/main.py`)
- [ ] Encrypt GSC tokens at rest (use AWS Secrets Manager or Vault)

---

## Project structure

```
seo-agent/
├── docker-compose.yml
├── .env.example
├── scripts/
│   ├── setup.sh
│   └── seed.py
├── infra/
│   ├── postgres/init.sql
│   └── clickhouse/init.sql
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── crawler_agent.py
│   │   ├── keyword_agent.py
│   │   ├── serp_agent.py
│   │   ├── content_gen_agent.py
│   │   ├── optimizer_agent.py
│   │   ├── tracker_agent.py
│   │   └── feedback_agent.py
│   ├── api/
│   │   ├── main.py
│   │   └── routers/
│   │       ├── projects.py
│   │       ├── tasks.py
│   │       ├── keywords.py
│   │       ├── content.py
│   │       ├── analytics.py
│   │       ├── auth.py
│   │       └── wordpress.py
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── workers/
│   │   ├── celery_app.py
│   │   └── tasks/
│   │       ├── crawl_tasks.py
│   │       ├── keyword_tasks.py
│   │       ├── serp_tasks.py
│   │       ├── content_tasks.py
│   │       ├── tracker_tasks.py
│   │       └── feedback_tasks.py
│   ├── integrations/
│   │   ├── gsc/client.py
│   │   ├── serp/dataforseo_client.py
│   │   ├── llm/claude_client.py
│   │   └── wordpress/client.py
│   └── services/
│       └── storage.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx          (dashboard)
    │   ├── projects/page.tsx
    │   ├── keywords/page.tsx
    │   ├── content/page.tsx
    │   ├── analytics/page.tsx
    │   ├── jobs/page.tsx
    │   └── settings/page.tsx
    ├── components/
    │   └── Sidebar.tsx
    └── lib/
        └── api.ts
```
