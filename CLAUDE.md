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
- 2026-10-13 — **Scope realignment: Phase P (minimal PoC) now supersedes Phases 0–9 as
  the current priority** (see `docs/IMPLEMENTATION_PLAN.md`). The person driving this
  (njderidder) is self-financing a trust-based ~1–2 day proof of concept to convince
  the actual end client to commit at all — no contract exists yet. His ask is much
  smaller than the full plan: extract → match via jev alone → basic results + flag
  uncertain ones → compare against manually-verified calcs. The full-MVP engineering
  already done (auth/RBAC, Docker/CI, DB schema, full frontend shell) is real and
  correct but was built ahead of what's actually being asked for right now — paused,
  not wasted, resumes only if the client commits. Full context:
  `~/.claude/projects/e--FIVERR-DCC/memory/client_brief_and_context.md`.

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

**⚠ Priority changed 2026-10-13: Phase P (minimal PoC) is current, not Phase 2.6.**
See `docs/IMPLEMENTATION_PLAN.md`'s Phase P and the decision log above. Phases 1–2.5
below are done and real, just paused ahead of where they're needed — resume only on
an explicit decision to go back to the full build.

**Phase:** 2 — IFC processing engine, 2.1–2.5 done, **paused here** (not continuing to
2.6/2.7 — see Phase P above).
**Phase 1:** done except 1.7's staging-deploy step (deliberately skipped — no hosting
target chosen; CI + Dockerfiles are done and verified, see git history for sub-phase
1.7).
**Known Windows/environment quirks worth remembering:** `rq worker` needs
`--worker-class rq.worker.SimpleWorker` locally (no `os.fork()` on Windows — containers
are Linux, so Dockerfiles don't need this); this shadcn/ui install is on Base UI
primitives, not Radix (`render` prop, not `asChild`); git's autocrlf here needs
`endOfLine: "auto"` in apps/web/.prettierrc.json or every fresh checkout flags as
unformatted; Git Bash mangles `/garage` paths in `docker compose exec` — prefix with
`MSYS_NO_PATHCONV=1`; a file's `AREAUNIT`/`VOLUMEUNIT` can be declared independently of
`LENGTHUNIT` in IFC, not derived from it — always get each unit type's scale
separately via `ifcopenshell.util.unit.calculate_unit_scale(file, unit_type)`, never
assume area = length_scale².
**Process hygiene (bit twice already):** killing background dev processes by port
(`Get-NetTCPConnection`) only catches the API/web servers — `rq worker` doesn't bind a
port, so that pattern never touches it. To actually kill a worker: find it via
`Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'uv.exe' -and
$_.CommandLine -match 'rq' }` (filter by `Name`, not just `CommandLine`, or the
PowerShell query can match its own command text), then `taskkill /F /T /PID <pid>` on
the root of its process tree, then re-run the same query and confirm it's empty —
don't trust a single kill attempt.
**Running `pnpm build` while `pnpm dev` is active against the same `apps/web/.next`
directory corrupts the dev server every time** (`ENOENT ... _buildManifest.js.tmp...`,
then 500s on every route) — bitten twice now during routine audits. Either stop the
dev server first, or expect to `rm -rf apps/web/.next` and restart it after a `pnpm
build` check.
**Test cleanup helpers must track every FK that points at what they're deleting** —
each new table (quantities → elements, in 2.3) breaks any existing test cleanup that
doesn't know about it, causing silent row leaks that surface later as confusing
UNIQUE-constraint failures in unrelated tests. When adding a table with a new FK,
grep existing `_cleanup()` helpers for the table it references.
**Correction to an earlier assumption:** Phase 2's engineering sub-phases (2.1–2.6) do
**not** need the client's real IFC files/code lists — test fixtures are enough (see
`apps/api/tests/fixtures/README.md`: a synthetic one covering all 12 supported element
types, plus a real public-domain sample with authoring-tool messiness). Only **2.7**
(extraction comparison report against `data/ground_truth.csv`) and later QA/export
phases are actually blocked on client data — see "Still open" below.
**Last session:** 2026-10-13 — Phase P.1–P.3 (jev client, classification, minimal CSV
export) done: `app/ai/jev.py` (`StubJevClient` until real credentials exist — the real
`JevClient` deliberately raises rather than guessing at an undocumented API contract),
`app/ai/classify.py` (one jev call per unique `group_hash`, one `Classification` row
per element, routes everything to `needs_review` since stub confidence is always 0.0),
`app/ai/export.py` + `GET /projects/{id}/export` (a downloadable CSV — chosen over
Excel/a frontend page to stay inside the 1-2 day budget). All wired into the existing
extraction pipeline as its final step. Verified via pytest (60/60) and live: a real
upload of `real_sample.ifc` produced a real CSV with real quantities and an honest
"jev not yet configured" reasoning per row — not fabricated data.
**A real recurring bug, fixed properly this time:** the new `classifications` table
broke 4 separate test files' local cleanup copies (same class of bug as 2.3/2.4).
Instead of patching each again, extracted one shared `cleanup_project_cascade()` into
`tests/conftest.py`, used by all 5 files now — the next new FK-bearing table updates
one function, not N.
Also recently: sub-phases 2.1–2.5 (full extraction pipeline); the `AUTH_DISABLED`
dev-mode login bypass; the Phase P scope realignment itself (see decision log above).
**Still not proven:** behavior on a genuinely large file (biggest fixture is 92KB).
**Blocked:** P.4 (accuracy comparison) needs the manually-verified reference
calculations njderidder said he's gathering — not received yet.
**Next up:** nothing buildable right now without new input. Either njderidder's real
jev credentials (making P.1/P.2 fully real instead of stubbed) or his reference files
(unblocking P.4) — whichever arrives first.
