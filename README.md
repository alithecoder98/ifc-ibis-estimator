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
  Redis, MinIO for local dev)
- [uv](https://docs.astral.sh/uv/) for the Python backend
- [pnpm](https://pnpm.io/) for the frontend
- Node.js 20+, Python 3.12+

## Local setup

```bash
# 1. Infra: Postgres (pgvector), Redis, MinIO
cp .env.example .env
docker compose up -d

# 2. Backend
cd apps/api
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

API: http://localhost:8000 · Frontend: http://localhost:3000 · MinIO console:
http://localhost:9001

## Tests

```bash
cd apps/api && uv run pytest
cd apps/web && pnpm lint
```

## Working agreement

One sub-phase of [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) per git
branch/session; see [docs/PROMPTS.md](docs/PROMPTS.md) for how each session is run.
