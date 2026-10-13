# IFC-to-IBIS Estimator — Project Charter

## Who and why

Freelance project for a client who works with a Dutch construction company producing cost
estimates for residential buildings. Architects deliver 3D building models in IFC format
(walls, floors, foundations, roofs, materials, quantities). Today an estimator manually
walks each model, works out quantities, matches every element to the company's internal
standard element list and an IBIS cost code, assembles it in Excel, and imports that into
IBIS (their estimating software). **IBIS does the pricing — this app never calculates
prices.**

Goal: automate most of that mapping while keeping a human in control of anything uncertain.

## What we are building (MVP)

1. Estimator logs in, creates a project, uploads an IFC file.
2. IfcOpenShell extracts elements, properties, materials, layers, quantities (geometry
   fallback when quantities are missing from the file).
3. Pipeline suggests internal element + IBIS code per element: rules → embeddings
   shortlist (pgvector) → similar past approved examples → LLM (+ "jev", the client's
   existing AI classification tool) → calibrated confidence → auto-accept or review queue.
4. Estimator reviews in a table + 3D viewer (That Open Engine), approves/corrects, splits
   composite elements (e.g. a wall's material layers) into separate lines.
5. Every correction is stored, embedded, and reused as a future example. Repeated
   correction patterns become suggested rules an admin approves.
6. Approved quantities export to Excel in the client's IBIS import format.

## Non-goals

- No price calculation — strictly IBIS's job.
- No IFC authoring/editing — read-only extraction and viewing.
- No multi-tenant/public SaaS in MVP — single client, their estimators only.

## Stack (as fixed by docs/IMPLEMENTATION_PLAN.md and docs/PROMPTS.md)

- **Frontend** — `apps/web`: Next.js 15, TypeScript strict, Tailwind, shadcn/ui, React
  Query, typed API client generated from the FastAPI OpenAPI schema.
- **Backend** — `apps/api`: FastAPI, Python dependencies managed with `uv`, SQLAlchemy 2 +
  Alembic migrations, pydantic-settings, structured logging, a uniform
  `{"error": {"code","message"}}` error shape.
- **Worker** — RQ (Redis Queue) jobs for IFC parsing, extraction, quantity computation,
  classification; a `jobs` table tracks status/progress, polled by the frontend.
- **DB** — PostgreSQL 16 + pgvector (code-list and example-memory embeddings), Redis
  (queue + cache), both via `docker-compose.yml` for local dev.
- **Storage** — S3-compatible object storage for uploaded IFC files (presigned URL or
  chunked upload flow — decided in 1.1, see below).
- **Auth** — email/password, argon2 hashing, JWT in an httpOnly cookie, roles `admin` /
  `estimator` / `viewer`.
- **AI** — `Embedder` and `LLMClient` interfaces behind a provider implementation
  (provider TBD — needed before Phase 3, not Phase 1); a `JevClient` adapter, stubbed
  until jev API docs/access are available.
- **3D viewer** — That Open Engine (`@thatopen/components`), fragments converted from IFC
  for fast loading.
- **Hosting** — EU region; staging/production target not yet decided (see Phase 1.7 and
  Phase 9).
- **Tooling** — `uv` for Python deps, `pnpm` for JS deps, ruff + black + eslint + prettier
  via pre-commit, GitHub Actions CI, Playwright for E2E.

## Monorepo layout

```
/apps
  /web        Next.js 15 frontend
  /api        FastAPI backend + RQ worker code
/scripts      one-off/offline tooling (ifc_audit.py, prepare_codes.py, evaluate.py, ...)
/data         client-provided reference files + generated reports — git-ignored
/docs         planning docs, prompts, runbooks, guides (this plan lives here)
```

## Core data model (implemented as of sub-phase 1.3 — `apps/api/app/db/models/`)

Matches the first real Alembic migration (`08797541e51b_core_schema.py`). Changing
anything below now means a follow-up migration, not just an edit to this file.

| Table | Key fields |
|---|---|
| `users` | id, email, password_hash, role (admin/estimator/viewer), created_at |
| `projects` | id, name, status, created_by → users, created_at, updated_at |
| `ifc_files` | id, project_id, filename, storage_key, ifc_schema, size_bytes, uploaded_by, uploaded_at, status |
| `elements` | id, ifc_file_id, global_id, ifc_class, predefined_type, name, object_type, storey, is_external, load_bearing, materials/layers (JSON), psets (JSON), profile_text, group_hash |
| `quantities` | id, element_id, quantity_type (length/area_net/area_gross/volume_net/volume_gross/count), value, unit, source (qto/geometry) |
| `code_list` | id, ibis_code, internal_element, description, unit, family, embedding (vector), version, created_at |
| `classifications` | id, element_id, ibis_code, internal_element, reasoning, self_score, confidence, flags (JSON), status (auto_accepted/needs_review), source (rule/llm/jev), created_at |
| `reviews` | id, classification_id, user_id → users, action (approve/correct/split), before (JSON), after (JSON), comment, created_at |
| `example_memory` | id, profile_text, embedding (vector), final_ibis_code, final_internal_element, project_id, created_at |
| `rules` | id, conditions (JSON), result_ibis_code, result_internal_element, priority, status (suggested/active), source_corrections (JSON refs), created_at |
| `exports` | id, project_id, file_path, generated_by → users, generated_at, totals (JSON) |
| `jobs` | id, type, project_id, ifc_file_id, status, progress, error, created_at, updated_at |

## MVP targets

Extraction ≥ 95% · quantity deviation ≤ ±3% · overall classification accuracy ≥ 80% before
review · auto-accept precision ≥ 95% · unflagged errors ≤ 3% · 100 MB model processes in
< 10 min · review time reduced ≥ 50% vs. manual process.

## Gates

- **Design sign-off** (end week 1.5): scope, wireframes, data model, accuracy targets,
  Excel format.
- **AI accuracy checkpoint** (end week 6): `scripts/evaluate.py` meets interim targets
  (overall ≥ 75%, auto-accept precision ≥ 95%) or the approach is adjusted.
- **UAT and go-live** (end week 11): client sign-off.

## How we work together

Full detail in [docs/PROMPTS.md](docs/PROMPTS.md) — summary:

- Build strictly in the phase/sub-phase order in
  [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — **one sub-phase per
  session, one sub-phase per git branch** (`phase-<X.Y>-<slug>`).
- Each sub-phase: Claude proposes a plan (≤10 bullets), files to touch, and any new
  dependency with its reason — then waits for an explicit **"go"** before coding.
- After coding: run tests/linters, show results, tick the sub-phase's checkbox in
  `docs/IMPLEMENTATION_PLAN.md`, update "Current status" below, and suggest a commit
  message.
- Keep changes small and scoped to the sub-phase; don't refactor unrelated code.
- Ask when something is unclear (domain terms, data model, thresholds) instead of
  guessing — especially where the plan itself says "ask me if unsure."
- User is comfortable with Python/automation; explain frontend and 3D-viewer parts in a
  bit more depth than backend ones.

## Open decisions log

- 2026-10-12 — Adopted the detailed phase/prompt plan (now in `docs/`) over the earlier
  placeholder drafts; tech stack choices above are taken as fixed unless noted TBD.
- 2026-10-12 — Installing `pnpm` + `uv` globally for this project, matching the plan as
  written, instead of falling back to `npm`/`pip`.
- 2026-10-12 — Local/staging S3-compatible storage is MinIO via `docker-compose.yml`
  (self-hosted, same API as real S3) until a real EU provider is chosen for production.
- 2026-10-13 — Added `AUTH_DISABLED` dev-mode toggle (`apps/api/app/core/deps.py`) so
  local testing doesn't need a login each time. Off by default, guarded so it can't
  start outside `ENVIRONMENT=development`, tests always run with real auth regardless
  of local `.env`. **Must stay off for anything beyond local dev** — this is a
  convenience toggle, not a decision to drop RBAC from the MVP.

## Still open (don't block the engineering work, but block specific later sub-phases)

- LLM provider for `LLMClient` (needed before Phase 3.4)
- jev API docs/access (Phase 3.5 stubs until then)
- Staging/production hosting target (Phase 1.7's deploy step; Phase 9)
- Client's real code lists, sample IFC files, ground truth, Excel template — blocks
  Phase 0 discovery tooling, Phase 2.1's real code-list import (2.1 itself used a
  generated test fixture, not client data), Phase 2.7 (extraction comparison report),
  and later QA/export phases. Does **not** block Phase 2.2–2.6's engineering work —
  those use test fixtures.

## Current status

**Phase:** 2 — IFC processing engine, started (sub-phase 2.1 done).
**Phase 1:** done except 1.7's staging-deploy step (deliberately skipped — no hosting
target chosen; CI + Dockerfiles are done and verified, see git history for sub-phase
1.7). Known Windows quirks worth remembering: `rq worker` needs `--worker-class
rq.worker.SimpleWorker` locally (no `os.fork()` on Windows — containers are Linux, so
Dockerfiles don't need this); this shadcn/ui install is on Base UI primitives, not Radix
(`render` prop, not `asChild`); git's autocrlf here needs `endOfLine: "auto"` in
apps/web/.prettierrc.json or every fresh checkout flags as unformatted; Git Bash mangles
`/garage` paths in `docker compose exec` — prefix with `MSYS_NO_PATHCONV=1`.
**Last session:** 2026-10-13 — sub-phase 2.1 (projects CRUD + IFC upload API) done:
`POST/GET /projects`, `POST /projects/{id}/files` (server-proxied multipart upload,
validates with ifcopenshell, stores in Garage, creates an `ifc_files` row and a stub
`extract` job). Provisioned the real Garage bucket + access key (deferred from 1.1).
Verified live against the real stack, not just pytest: real login → real upload → file
confirmed in the Garage bucket → job completed via the real worker.
**Correction to an earlier assumption:** Phase 2's engineering sub-phases (2.1–2.6) do
**not** need the client's real IFC files/code lists — a generated test fixture
(`apps/api/tests/fixtures/sample.ifc`, built via ifcopenshell's own API, not downloaded)
is enough. Only **2.7** (extraction comparison report against `data/ground_truth.csv`)
and later QA/export phases are actually blocked on client data — see "Still open" below.
**Also this session:** added the `AUTH_DISABLED` dev-mode login bypass (own commit, not
part of 2.1) — see decision log above. `/` now redirects to `/projects` instead of
`/login` as a side effect (the protected layout's own 401-redirect still sends an
unauthenticated visitor to `/login` when auth is enabled).
**Next up:** sub-phase 2.2 — Element extraction (walls, slabs, roofs, etc. from IFC into
the `elements` table). The current `sample.ifc` fixture (one wall) should probably grow
to cover more element types before or during 2.2 so extraction logic gets exercised
meaningfully.
