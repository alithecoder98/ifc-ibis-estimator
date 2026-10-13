# IFC-to-IBIS Estimator

Automates matching IFC building elements to a Dutch construction company's internal
element list and IBIS cost codes, with a human-in-the-loop review step. See
[CLAUDE.md](CLAUDE.md) for the full project charter and
[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the build plan.

## Layout

```
/apps/web     Next.js 15 frontend (TypeScript, Tailwind, shadcn/ui)
/apps/api     FastAPI backend + RQ worker (Python, managed with uv)
/scripts      offline tooling (IFC audits, code-list cleaning, evaluation)
/data         client-provided reference files + generated reports (git-ignored)
/docs         planning docs, prompts, guides
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Postgres+pgvector,
  Redis, Garage for local dev)
- [uv](https://docs.astral.sh/uv/) for the Python backend
- [pnpm](https://pnpm.io/) for the frontend
- Node.js 20+, Python 3.12+

## Local setup

```bash
# 1. Infra: Postgres (pgvector), Redis, Garage
cp .env.example .env
docker compose up -d

# 2. Backend
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed-admin --email you@example.com --password <password>
uv run uvicorn app.main:app --reload --port 8000

# 3. Worker (separate terminal) — processes background jobs (IFC extraction, etc.)
cd apps/api
uv run rq worker --worker-class rq.worker.SimpleWorker
# ^ RQ's default worker uses os.fork(), unavailable on Windows — use SimpleWorker there.
# On Linux/macOS/CI, plain `uv run rq worker` works too.

# 4. Frontend (separate terminal)
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

API: http://localhost:8000 · Frontend: http://localhost:3000 · Garage S3 API:
http://localhost:3900 (no web console — it's API-only)

## Tests

```bash
cd apps/api && uv run pytest
cd apps/web && pnpm lint
```

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on every
push/PR: ruff + black + pytest for the backend (against real Postgres/Redis service
containers), eslint + build for the frontend, then builds all three Docker images to
catch a broken Dockerfile early. **No deploy step yet** — staging/production hosting
isn't decided (see CLAUDE.md "Still open").

## Docker images

```bash
docker build -f apps/api/Dockerfile apps/api          # API
docker build -f apps/api/Dockerfile.worker apps/api   # worker
docker build -f apps/web/Dockerfile apps/web          # frontend
```

All three are verified against the real docker-compose stack, not just "it compiles" —
run `docker build` above, then run the resulting image on the `ifc-ibis-estimator_default`
network with `DATABASE_URL`/`REDIS_URL` pointing at the compose Postgres/Redis
containers.

## Working agreement

One sub-phase of [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) per git
branch/session; see [docs/PROMPTS.md](docs/PROMPTS.md) for how each session is run.
