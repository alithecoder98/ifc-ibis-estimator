# IFC-to-IBIS Estimator

An internal tool that automates most of the manual work a construction cost estimator does
today: open a 3D building model (IFC), identify every wall/floor/foundation/roof element,
work out its quantities, and match it to an internal standard element list and an IBIS cost
code. The estimator reviews and corrects the suggestions in a table + 3D viewer; **IBIS
itself still does all the pricing** — this app only produces the quantities and code
mapping that feed into it.

## Problem statement & objectives

Estimators currently walk each IFC model by hand, compute quantities, look up the matching
internal element/IBIS code, and assemble an Excel sheet for import into IBIS. That's slow
and repetitive, and consistency depends entirely on the individual estimator's experience.

The goal here is **not** to remove the estimator from the loop — it's to get the easy,
high-confidence matches out of their way automatically and surface only the genuinely
uncertain ones for review, while every correction they make is captured and reused to make
future suggestions better.

## Key features

- **IFC extraction** — walls, floors, foundations, roofs, materials/layers, quantities
  (from Qto property sets where present, computed from geometry otherwise), for every
  supported element type.
- **Automated classification pipeline** — rule matching → pgvector similarity shortlist
  against a code list → similar past-corrected examples → an LLM call (local, via Ollama)
  and/or the client's own "jev" classification tool → a calibrated confidence score that
  decides auto-accept vs. send-to-review.
- **Review table + 3D viewer** — a virtualized, filterable/groupable element table synced
  with a That Open Engine 3D view (click an element in either one, it highlights/opens in
  the other); approve, correct, or bulk-approve a whole group of elements; undo any review.
- **Composite element splitting** — split a wall's multiple material layers into separate
  line items when they need separate cost codes.
- **Rule auto-suggestion** — repeated correction patterns become a suggested rule an admin
  can approve, so the same correction isn't needed twice.
- **Example memory** — every correction is embedded and reused as a retrieval example for
  future similar elements.
- **Export** — CSV and Excel export of the final reviewed quantities/codes.
- **Recoverable processing** — if an upload's background job is ever lost (e.g. an
  infrastructure restart), a "Process file" button re-triggers it; nothing gets silently
  stuck.

## Technology stack & architecture

| Layer | Stack |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript (strict), Tailwind CSS v4, shadcn/ui (Base UI primitives), TanStack Query + TanStack Table/Virtual, a typed API client generated from the backend's OpenAPI schema |
| Backend | FastAPI, SQLAlchemy 2 + Alembic migrations, pydantic-settings, Python managed with `uv` |
| Worker | RQ (Redis Queue) background jobs for IFC extraction, quantity computation, and classification; job status/progress is polled by the frontend |
| Database | PostgreSQL 16 + pgvector (code-list and example-memory embeddings) |
| Queue/cache | Redis |
| Object storage | Any S3-compatible store (local dev uses self-hosted [Garage](https://garagehq.deuxfleurs.fr/)) for uploaded IFC files |
| AI | A local Ollama instance serving `bge-m3` for embeddings and `qwen2.5:7b-instruct` for classification, behind `Embedder`/`LLMClient` interfaces; a `JevClient` adapter for the client's own classification tool (stubbed until API access exists) |
| 3D viewer | That Open Engine (`@thatopen/components`, `@thatopen/fragments`) — IFC is converted to That Open "fragments" server-side for fast client-side loading |
| Auth | Email/password, argon2 password hashing, JWT in an httpOnly cookie, roles `admin`/`estimator`/`viewer` |

**Architecture, end to end:** an estimator uploads an IFC file → the API stores it in
object storage and enqueues an extraction job → the worker parses the file with
IfcOpenShell, computes quantities, converts it to a fragments binary for the 3D viewer, and
runs it through the classification pipeline → the frontend polls the job and then shows
the results in the review table/3D viewer → every approval or correction is written back
and embedded for future retrieval → the estimator exports the reviewed data for IBIS import.

## Project structure

```
/apps
  /web        Next.js 15 frontend
  /api        FastAPI backend + RQ worker code
    /app
      /routers      API endpoints
      /ai            classification pipeline (rules, embeddings, LLM, jev, confidence)
      /ifc           IFC extraction, quantities, fragments conversion
      /db/models     SQLAlchemy models
      /workers       RQ job functions
    /alembic/versions   database migrations
    /scripts      one-off/offline tooling (evaluation, calibration, rule loading, extraction
                  comparison) — run with `uv run python scripts/<name>.py` from apps/api
    /tests
/data         client-provided reference files + generated reports — git-ignored, see
              data/README.md for what's expected there
/docs         planning docs, prompts, runbooks
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (runs Postgres+pgvector,
  Redis, Garage, and Ollama locally)
- [uv](https://docs.astral.sh/uv/) for the Python backend
- [pnpm](https://pnpm.io/) for the frontend
- Node.js 20+, Python 3.12+
- An NVIDIA GPU is strongly recommended for local Ollama inference (CPU works, just much
  slower) — see [Known limitations](#known-limitations--outstanding-deployment-requirements)
  for what this means for hosted deployment.

## Local setup

```bash
# 1. Infra: Postgres (pgvector), Redis, Garage, Ollama
cp .env.example .env
docker compose up -d

# 1b. One-time: give Garage a layout and an API key (MSYS_NO_PATHCONV=1 only needed on
# Windows Git Bash, which otherwise mangles the /garage path). Skip if already done.
MSYS_NO_PATHCONV=1 docker compose exec garage /garage status   # note the node ID
MSYS_NO_PATHCONV=1 docker compose exec garage /garage layout assign <node-id> -z dc1 -c 1G
MSYS_NO_PATHCONV=1 docker compose exec garage /garage layout apply --version 1
MSYS_NO_PATHCONV=1 docker compose exec garage /garage bucket create ifc-uploads
MSYS_NO_PATHCONV=1 docker compose exec garage /garage key create ifc-ibis-api-key
MSYS_NO_PATHCONV=1 docker compose exec garage /garage bucket allow --read --write ifc-uploads --key ifc-ibis-api-key
# ^ copy the printed Key ID / Secret key into apps/api/.env as S3_ACCESS_KEY/S3_SECRET_KEY

# 1c. One-time: pull the Ollama models used for embeddings/classification
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull qwen2.5:7b-instruct

# 2. Backend
cd apps/api
cp .env.example .env   # then fill in S3_ACCESS_KEY/S3_SECRET_KEY from step 1b
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed-admin --email you@example.com --password <password>
uv run uvicorn app.main:app --reload --port 8000

# 3. Worker (separate terminal) — processes background jobs (IFC extraction, etc.)
cd apps/api
cd node_fragments && npm install && cd ..
# ^ one-time: the worker shells out to node_fragments/convert.mjs (IFC -> That Open
# fragments for the 3D viewer) — JS-only, no Python equivalent.
uv run rq worker --worker-class rq.worker.SimpleWorker
# ^ RQ's default worker uses os.fork(), unavailable on Windows — use SimpleWorker there.
# On Linux/macOS/CI (and in the Docker image), plain `uv run rq worker` works too.

# 4. Frontend (separate terminal)
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

API: http://localhost:8000 · Frontend: http://localhost:3000 · Garage S3 API:
http://localhost:3900 (no web console — it's API-only)

### Skipping login during local dev

Set `AUTH_DISABLED=true` in `apps/api/.env` and restart the API — every request then
becomes a fixed `dev@local.test` admin user, no login screen, no cookie needed. It's
guarded: the app refuses to start if this is `true` and `ENVIRONMENT` isn't
`development`, so it can't accidentally reach a hosted environment. Tests always run
with real auth regardless of this setting.

## Environment variables

Copy each app's `.env.example` and fill in the real values. **Never commit a `.env` file**
— they're already git-ignored.

**`apps/api/.env`:**

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql+psycopg://user:pass@host:5432/db` |
| `REDIS_URL` | Redis connection string, e.g. `redis://host:6379/0` |
| `S3_ENDPOINT_URL` | S3-compatible storage endpoint |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Storage credentials — placeholders only, generate real ones for your own environment |
| `S3_BUCKET` / `S3_REGION` | Storage bucket name/region |
| `JWT_SECRET` | Random secret, minimum 32 bytes, used to sign auth cookies — generate a unique one per environment |
| `JWT_EXPIRES_MINUTES` | Session length |
| `AUTH_DISABLED` | Dev-only login bypass — must stay `false` outside local development |
| `OLLAMA_BASE_URL` / `OLLAMA_EMBEDDING_MODEL` / `OLLAMA_LLM_MODEL` | Local AI model serving |
| `JEV_API_URL` / `JEV_API_KEY` | The client's own classification tool — left blank until real API access exists |
| `ENVIRONMENT` | `development` / `production` |
| `PORT` | Overrides the listening port (used by the Docker image, defaults to 8000) |

**`apps/web/.env.local`:**

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the backend API. Inlined at **build** time, not read at runtime — see [Deploying on Render](#deploying-on-render-with-docker). |

## Required data files

`data/` is where client-provided reference material goes for local development (sample
IFC files, the client's real code list, ground-truth calculations) — it's git-ignored and
currently empty on a fresh checkout. See [`data/README.md`](data/README.md) for exactly
what's expected there and which parts of the app need it. The core extraction/
classification pipeline works without any of it (the test suite ships its own fixtures);
only the real client code-list import and the accuracy-comparison tooling in
`apps/api/scripts/` need real data supplied separately.

## Running the tests

```bash
cd apps/api && uv run pytest
cd apps/web && pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs both on every push/PR
against real Postgres/Redis service containers, then builds all three Docker images to
catch a broken Dockerfile early.

## Running with Docker

```bash
docker build -f apps/api/Dockerfile apps/api          # API
docker build -f apps/api/Dockerfile.worker apps/api    # worker
docker build -f apps/web/Dockerfile apps/web \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 # frontend
```

All three have been built and smoke-tested against the real `docker compose` stack (not
just "it compiles") — run `docker build` above, then run the resulting image on the
`ifc-ibis-estimator_default` network with the same env vars as `apps/api/.env.example`/
`apps/web/.env.example` pointed at the compose services.

## API overview

The backend exposes its full interactive docs at `/docs` (Swagger UI) once running.
Highlights:

| Endpoint | Purpose |
|---|---|
| `POST /auth/login`, `GET /auth/me` | Authentication |
| `POST /projects`, `GET /projects/{id}` | Project CRUD |
| `POST /projects/{id}/files` | Upload an IFC file (enqueues extraction) |
| `POST /projects/{id}/files/{file_id}/reprocess` | Retry extraction for a file stuck "uploaded"/"failed" |
| `POST /projects/{id}/files/{file_id}/classify` | Re-run classification on an already-extracted file |
| `GET /projects/{id}/elements` | Full element list for the review table |
| `GET /projects/{id}/elements/{element_id}` | Element detail: properties, quantities, AI reasoning, candidate codes |
| `POST /projects/{id}/elements/{element_id}/reviews` | Approve/correct a single element |
| `POST /projects/{id}/groups/{group_hash}/reviews` | Bulk-approve/correct a whole group |
| `POST /projects/{id}/elements/{element_id}/split` | Split a composite element's material layers |
| `GET /projects/{id}/export`, `GET /projects/{id}/export.xlsx` | Export reviewed data |
| `GET /projects/{id}/files/{file_id}/model` | That Open fragments binary for the 3D viewer |
| `GET /codes`, `POST /codes/import`, `GET /codes/search` | Code list browse/import/semantic search |
| `GET /rules`, `POST /rules`, `POST /rules/suggest` | Classification rules + auto-suggestion |
| `GET/PATCH /settings/threshold` | Auto-accept confidence threshold |

## Troubleshooting

- **`rq worker` hangs or never processes a job on Windows** — use
  `uv run rq worker --worker-class rq.worker.SimpleWorker` (RQ's default worker uses
  `os.fork()`, unavailable on Windows). Linux/macOS and the Docker image don't need this.
- **Postgres/Redis connection errors right after starting** — make sure Docker Desktop
  (or your Docker engine) is actually running; `docker compose ps` should show all
  services healthy before starting the API/worker.
- **A file stays stuck on "Uploaded" and never progresses** — click "Process file" on
  that file's row (added specifically to recover from a lost background job, e.g. after
  a Redis restart). If it's still stuck after that, check the worker process is actually
  running and pointed at the same Redis instance as the API.
- **Garage path errors in `docker compose exec` on Windows Git Bash** — prefix the
  command with `MSYS_NO_PATHCONV=1` (Git Bash otherwise mangles `/garage`-style paths).

## Deploying on Render with Docker

Both the API and worker Dockerfiles respect Render's `PORT` env var (the API binds to
`0.0.0.0:$PORT`, falling back to 8000 when unset; the worker has no HTTP port). The web
Dockerfile's Next.js standalone server does the same automatically.

1. **Provision the managed pieces Render offers directly:**
   - A **PostgreSQL** instance. `CREATE EXTENSION vector;` must be run once against it —
     Render's managed Postgres supports the `pgvector` extension, confirm it's enabled for
     your plan before running migrations.
   - A **Redis/Key Value** instance.
2. **Provision the pieces Render does not offer, from an external provider:**
   - **S3-compatible object storage** for uploaded IFC files — a real AWS S3 bucket,
     Cloudflare R2, Backblaze B2, or a self-hosted Garage instance somewhere Render can
     reach. Render has no built-in equivalent.
   - **An Ollama endpoint reachable over the network** for embeddings/classification.
     Render's standard web/worker services don't include GPU access on most plans, and
     `qwen2.5:7b-instruct` is impractically slow on CPU-only. Either point `OLLAMA_BASE_URL`
     at a GPU host you run elsewhere, or swap the `Embedder`/`LLMClient` implementations
     for a hosted API — this is a real architecture decision, not something this prep
     changed or assumed an answer for.
3. **Create three Render services from this repo**, each a "Docker" web/background
   service pointed at the relevant Dockerfile and build context:
   - **API** — Web Service, `apps/api/Dockerfile`, context `apps/api`. Set every
     `apps/api/.env.example` variable as a Render environment variable with real values
     (`DATABASE_URL`/`REDIS_URL` from steps 1 above, `S3_*`/`OLLAMA_BASE_URL` from step 2,
     a freshly generated `JWT_SECRET`, `ENVIRONMENT=production`, `AUTH_DISABLED=false`).
     Leave `PORT` unset — Render sets it.
   - **Worker** — Background Worker, `apps/api/Dockerfile.worker`, context `apps/api`.
     Same environment variables as the API (it needs the same DB/Redis/storage/AI access).
   - **Web** — Web Service, `apps/web/Dockerfile`, context `apps/web`. Set the
     `NEXT_PUBLIC_API_URL` **Docker build argument** (not just an environment variable —
     it's inlined into the client bundle at build time) to the API service's public
     Render URL once that's known.
4. Run `alembic upgrade head` against the production database once (e.g. via a Render
   one-off job or shell) before the API serves real traffic.
5. Seed an initial admin user the same way as local setup (`python -m app.cli seed-admin`)
   against the production database.

## Known limitations & outstanding deployment requirements

- **jev integration is stubbed.** The client's real classification tool API docs/
  credentials haven't arrived yet; `JevClient` deliberately raises rather than guessing at
  an undocumented contract, and the stub routes everything to manual review.
- **No real client ground truth yet.** Accuracy/calibration tooling in `apps/api/scripts/`
  (`evaluate.py`, `calibrate.py`, `compare_accuracy.py`) is self-tested against synthetic
  fixtures only — none of its output is a validated real-world accuracy number.
- **Render has no managed equivalent for self-hosted Ollama or Garage** (see
  [Deploying on Render](#deploying-on-render-with-docker) above) — both need an external
  provider or a different architecture decision before a hosted deployment can actually
  run the full AI pipeline.
- **Auth bypass exists for local dev only** (`AUTH_DISABLED`) — guarded to refuse startup
  outside `ENVIRONMENT=development`, but worth knowing it's in the codebase.
- **No staging environment has existed yet** — every "verified live" claim in this
  project's history was against a local Docker Compose stack, not a hosted deployment.
