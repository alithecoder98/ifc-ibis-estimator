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
- **AI** — `Embedder` and `LLMClient` interfaces behind local/open-source models served
  by Ollama (decided 2026-10-13: bge-m3 for embeddings, qwen2.5:7b-instruct for the LLM
  — see decision log); a `JevClient` adapter, stubbed
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
- 2026-10-13 — **AI provider decided: local/open-source models via Ollama, not a paid
  API.** User has a local RTX 2060 Super (8GB VRAM) and explicitly chose self-hosted
  over OpenAI/Anthropic+embeddings/anything paid — no per-call cost, no client data
  leaving the machine. Embeddings: `bge-m3` (strong multilingual/Dutch support, 1024
  dims). LLM: `qwen2.5:7b-instruct` (fits comfortably in 8GB VRAM with headroom,
  reliable structured-JSON output, good Dutch quality) over a smaller/faster model or
  a bigger one needing more VRAM than this machine reliably has free. Served via a new
  `ollama` `docker-compose.yml` service with GPU passthrough — confirmed working for
  real (100% GPU offload per `ollama ps`, ~62 tok/s once warm, correct real LLM output
  and real pgvector similarity search, not mocked). `EMBEDDING_DIM` changed from the
  OpenAI-shaped placeholder (1536) to bge-m3's real 1024.

## Still open (don't block the engineering work, but block specific later sub-phases)

- jev API docs/access (Phase 3.5 stubs until then)
- Staging/production hosting target (Phase 1.7's deploy step; Phase 9)
- Client's real code lists, sample IFC files, ground truth, Excel template — blocks
  Phase 0 discovery tooling, Phase 2.1's real code-list import (2.1 itself used a
  generated test fixture, not client data), Phase 2.7 (extraction comparison report),
  and later QA/export phases. Does **not** block Phase 2.2–2.6's engineering work —
  those use test fixtures.

## Current status

**⚠ Priority changed back 2026-10-13: full plan resumed at 2.6.** Phase P (minimal
PoC, P.1–P.4) is done and was njderidder's actual near-term ask; the user explicitly
chose to resume the paused full 9-phase build from Phase 2.6 rather than wait for
njderidder's reply. No new client commitment has arrived — this is a deliberate choice
to keep building ahead of one, not a sign one came in. See `docs/IMPLEMENTATION_PLAN.md`'s
Phase P and the decision log above for the full history.

**Phase 3 — AI classification engine: fully complete (3.1–3.8).** Phase 2 (2.1–2.7)
complete. **Phase 4 (frontend) in progress: 4.1–4.4 done.**
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
assume area = length_scale². **`pnpm add <package>` installs whatever "latest" tag
currently points to, which is not always the well-established API a plan or
tutorial means** — `@tanstack/react-table` (4.4) resolved to v9, a from-scratch
rewrite with no `useReactTable`/`getCoreRowModel()`/etc. at all, nothing like the
stable v8 API the rest of the ecosystem's docs and examples use. `tsc` caught it
immediately ("no exported member"), but the lesson is to check the installed
major version against what's actually being written/planned *before* writing
component code against it, for any TanStack (or similarly fast-moving) package —
pin an explicit version (`pnpm add pkg@8.x.x`) rather than trusting "latest" means
"the common one."
**Docker Desktop's WSL2 virtual disk doesn't shrink on its own.** `docker system
prune`/`image prune`/`builder prune` free space *inside* Docker's accounting, but the
host-side `.vhdx` file (`%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx`) stays the
same size until compacted — on this machine it grew to 25GB and ran C: down to 0.29GB
free mid-Ollama-pull. Fix: stop Docker Desktop, `wsl --shutdown`, then in an
**elevated** PowerShell: `diskpart` → `select vdisk file="<path>"` → `attach vdisk
readonly` → `compact vdisk` → `detach vdisk` → `exit`. Needs real admin rights — not
scriptable from a non-elevated session.
**A forced Docker Desktop/WSL restart leaves healthy-looking containers with stale
port-forwarding.** After the vhdx compaction above, `docker compose ps` reported every
container healthy but Postgres/Garage connections failed with
"connection closed"/`ConnectionClosedError` — the container itself was fine, only the
Windows-side port proxy was stale. Fix: `docker compose restart <service>` on the
affected ones (not full `docker compose up`, not a Docker Desktop restart) immediately
clears it.
**Process hygiene (bit four times now — 3.6's live test looked like a real bug for a
long while because of this, on top of 3.5's own instance of the same class of bug):**
killing background dev processes by port (`Get-NetTCPConnection`) only catches the
API/web servers — `rq worker` doesn't bind a port, so that pattern never touches it.
**The exact filter matters, not just "query by command line":**
`-match 'rq worker'` (as a contiguous phrase) does **not** match the actual
child-process command lines `uv run rq worker` spawns — `"rq.exe" worker
--worker-class ...` has a quote and a space between `rq.exe` and `worker`, so that
filter silently misses every real worker process and only ever catches the
top-level `uv.exe run rq worker` wrapper. **Use
`-match 'rq\.exe|rq worker|uvicorn'`** (covering the wrapper, the real child, and
the API server) and kill *every* PID it returns, every time, even when you only
meant to restart one. Multiple stray workers from earlier in the same session (each
from an earlier sub-phase's live test, surviving because the old filter never saw
them) can accumulate for the entire session and race a freshly started one for the
next job — the stale one can win, silently run old code, and produce a result that
looks like a real regression in brand-new code when the actual bug is "there were N
workers nobody could see." After killing, re-run the same (correct) query and
confirm it returns nothing before trusting any live test's result — don't trust a
single kill attempt, and don't assume "I started a new one" means "only one is
running," and don't assume your own filter is catching what you think it's catching
without actually listing full command lines at least once to check. **A live dev
worker left running is a correctness risk for the test suite, not just a staleness
risk for manual verification** — it and `pytest` share the same Redis instance
(`redis://localhost:6379/0`), so a leftover worker from an earlier live-verification
session will actually pick up and run a job a test just enqueued (e.g. the real
`extract` job from an upload test), racing that test's own direct DB manipulation
and producing a flaky, confusing failure with nothing to do with the code under
test (3.7: a test set `ifc_file.status = "extracted"` by hand to check the classify
endpoint's validation, and a stray worker overwrote it mid-test by actually
extracting the file for real). Before trusting *any* test failure that touches
jobs/uploads/worker-processed state, check for stray workers first.
**Any in-process cache keyed by content (not by a request/job ID) is unsafe across
long-lived worker processes if it holds ORM objects.** `app/ai/retrieval.py`'s
Phase 3.3 cache was a module-level dict keyed by `group_hash` — purely content-based,
so a second upload of a similar IFC file reused a previous job's `CodeList`
instances, still bound to that job's already-closed DB session
(`DetachedInstanceError`, only visible when the *same* fixture is processed twice in
one worker's lifetime — a single-job test can't see it). Fixed by making the cache
caller-scoped: the function takes a `cache` dict the caller creates fresh per call,
never a module-level one. The same question is worth asking of any future
`app/ai/*` cache: does its key only depend on content, and could two different
calls with the same key happen in the same process across two different DB
sessions? If yes, it can't be module-level.
**Running `pnpm build` while `pnpm dev` is active against the same `apps/web/.next`
directory corrupts the dev server every time** (`ENOENT ... _buildManifest.js.tmp...`,
then 500s on every route) — bitten twice now during routine audits. Either stop the
dev server first, or expect to `rm -rf apps/web/.next` and restart it after a `pnpm
build` check.
**Test cleanup helpers must track every FK that points at what they're deleting** —
each new table (quantities → elements, in 2.3) breaks any existing test cleanup that
doesn't know about it, causing silent row leaks that surface later as confusing
UNIQUE-constraint failures in unrelated tests. When adding a table with a new FK,
grep existing `_cleanup()` helpers for the table it references. **This isn't only
about brand-new tables** - `reviews` has existed since the original 1.3 schema but
was never exercised by a single test until 4.3's `corrected` count needed one,
and the exact same gap was there, just never triggered. When a test is about to
be the *first* one anywhere to touch a given table, that's also the moment to
check `cleanup_project_cascade()` knows about it - not just when the table itself
is new.
**Correction to an earlier assumption:** Phase 2's engineering sub-phases (2.1–2.6) do
**not** need the client's real IFC files/code lists — test fixtures are enough (see
`apps/api/tests/fixtures/README.md`: a synthetic one covering all 12 supported element
types, plus a real public-domain sample with authoring-tool messiness). Only **2.7**
(extraction comparison report against `data/ground_truth.csv`) and later QA/export
phases are actually blocked on client data — see "Still open" below.
**Last session:** 2026-10-13 — Phase P now fully done (P.1–P.4): jev client,
classification, minimal CSV export, and accuracy comparison. `app/ai/jev.py`
(`StubJevClient` until real credentials exist — the real `JevClient` deliberately
raises rather than guessing at an undocumented API contract), `app/ai/classify.py`
(one jev call per unique `group_hash`, one `Classification` row per element, routes
everything to `needs_review` since stub confidence is always 0.0), `app/ai/export.py`
+ `GET /projects/{id}/export` (a downloadable CSV — chosen over Excel/a frontend page
to stay inside the 1-2 day budget). All wired into the existing extraction pipeline as
its final step. Verified via pytest (60/60) and live: a real upload of
`real_sample.ifc` produced a real CSV with real quantities and an honest "jev not yet
configured" reasoning per row — not fabricated data.
**A real recurring bug, fixed properly this time:** the new `classifications` table
broke 4 separate test files' local cleanup copies (same class of bug as 2.3/2.4).
Instead of patching each again, extracted one shared `cleanup_project_cascade()` into
`tests/conftest.py`, used by all 5 files now — the next new FK-bearing table updates
one function, not N.
**P.4 (accuracy comparison)** — `app/ai/accuracy.py` (`compare_accuracy()` +
`load_ground_truth()`) and `scripts/compare_accuracy.py` (CLI:
`uv run python scripts/compare_accuracy.py <project_id> <ground_truth.csv>`), with
`scripts/example_ground_truth.csv` as the format template. Built and tested
**self-tested only, by explicit decision** — njderidder's real reference calculations
still haven't arrived, so `tests/test_accuracy.py` proves the comparison/mismatch
logic against our own fixture (jev's stub always returns `None`, so the test crafts a
controlled ground truth by hand), not a real accuracy number. Verified live too: a
real upload's real classifications ran through the real CLI. 63/63 pytest, run twice
to confirm no leaks.
Also recently: sub-phases 2.1–2.5 (full extraction pipeline); the `AUTH_DISABLED`
dev-mode login bypass; the Phase P scope realignment itself (see decision log above).
**This session:** 2.6 (fragments for the 3D viewer) done — resuming the full plan past
Phase P at the user's explicit direction (see the priority note at the top of this
section). `apps/api/node_fragments/convert.mjs` converts IFC -> That Open fragments via
`@thatopen/fragments` v3.4.8's `IfcImporter`/`SingleThreadedFragmentsModel` (verified by
installing the real package and reading its `.d.ts` before writing any code, then
running it for real against both fixtures and inside the actual built worker Docker
image — not just pytest). `app/ifc/fragments.py` invokes it via `subprocess` from the
worker pipeline (not a standalone service, not browser-side conversion — see
`docs/IMPLEMENTATION_PLAN.md`'s 2.6 entry for why). New migration `8c104e54e6a7` adds
`ifc_files.fragments_storage_key`/`fragment_id_map`. New endpoint
`GET /projects/{project_id}/files/{file_id}/model`. **New real dependency:** Node.js in
`Dockerfile.worker` (API image untouched — it only enqueues jobs) and
`actions/setup-node` in CI.
**Also this session:** 2.7 (extraction comparison report) done, same session as 2.6 —
**Phase 2 is now fully complete.** `app/ifc/extraction_report.py`
(`GroundTruthRow`/`load_ground_truth`/`compare_extraction`/`render_markdown_report`) +
`scripts/compare_extraction.py`. Ground-truth CSV format is PROMPTS.md's 0.3 spec
(`file, global_id, expected_ibis_code, expected_internal_element, expected_quantity,
unit, notes`) — 0.3's own loader was never built (Phase 0 still blocked on client
data), so this ships its own minimal validated loader rather than wait on a separate
phase. **Self-tested only, same caveat as P.4** — njderidder's reference calculations
still haven't arrived, so this proves the comparison logic against our own fixture,
not a real coverage number. **A real bug caught by the live smoke test, not pytest:**
`csv.DictReader` gives `""` for empty cells; Pydantic's `float | None` fields don't
coerce that to `None` and raise instead — fixed in `load_ground_truth()` before merge.
72/72 pytest, run twice, no leaks.
**Still not proven:** behavior on a genuinely large file (biggest fixture is 92KB).
**This session:** 3.1 (code list import + embeddings) done — see the 2026-10-13 AI
provider decision above and `docs/IMPLEMENTATION_PLAN.md`'s 3.1 entry for full detail.
Highlights: `docker-compose.yml`'s new `ollama` service (GPU passthrough, confirmed
working for real on the dev RTX 2060 Super); `EMBEDDING_DIM` 1536→1024 for bge-m3;
`app/ai/embedder.py`, `app/ai/codes.py`, `app/routers/codes.py`
(`POST /codes/import`, `GET /codes`, `GET /codes/search`). Verified live against the
real running Ollama (real embeddings stored in pgvector, real similarity search
ranked correctly, real qwen2.5 chat completion answered correctly), not just
`FakeEmbedder`. Also hit and fixed, mid-session, unrelated to this sub-phase's own
code: the C: drive disk-space crisis and the stale-port-forward issue, both now
documented above under "Known Windows/environment quirks."
**Also this session:** 3.2 (rule engine) done. `app/ai/rules.py` evaluates rules
**per element, not per `group_hash`** like jev — `group_hash` excludes `storey`, so a
storey-based rule can still split a jev group. Wired into `app/ai/classify.py` as the
first step: a matched element gets `confidence=1.0, source="rule", auto_accepted` and
never calls jev. Admin CRUD at `app/routers/rules.py`. `scripts/load_initial_rules.py`
+ `scripts/example_rules_initial.json`, self-tested only (no real client rules yet).
Verified live: added a rule matching `real_sample.ifc`'s actual `stone_sand-lime`
wall material (real data, not the fixture's literal "concrete"), confirmed 3 matching
walls got routed to the rule and skipped jev, a 4th wall with different material and
everything else correctly still went to jev. 94/94 pytest, run twice, no leaks.
**A process-hygiene miss, not a bug:** the live API server and RQ worker were both
started earlier in this session without `--reload`, before this sub-phase's code
existed — the first live test against them silently ran the *old* code (404 on the
new route, then 13/13 elements routed to jev with zero rule matches even after adding
a real rule) until both were restarted. Worth remembering: a 200 OK from a long-running
dev server doesn't confirm it's running today's code.
**Also this session:** 3.3 (retrieval) done. `app/ai/retrieval.py`: `guess_family()`
(ifc_class → code_list family, `IfcSlab` disambiguated via `predefined_type`),
`shortlist_codes()` (family-filtered, falls back to all families if too few),
`similar_examples()` (top-5 from `example_memory`), both wrapped in
`shortlist_and_examples()` with an in-process cache keyed by `group_hash` — same
"one lookup per group" reasoning as jev, since `group_hash` is deterministic per
group but `profile_text` isn't (quantities vary per element). **Not wired into
`classify.py` yet** — no consumer for its output (candidates + examples) until 3.4's
LLM prompt exists. **Another FK-onto-`projects` cleanup gap found and fixed:**
`example_memory.project_id` is `NOT NULL`, and `tests/conftest.py`'s shared
`cleanup_project_cascade()` never deleted it — exactly the bug class this file
already warns about, now fixed in the one shared function instead of a workaround in
this sub-phase's own tests. Verified live against real Ollama/pgvector (not just
`FakeEmbedder`): real shortlist, real family-fallback, real example ranking, real
cache hit. 100/100 pytest, run twice, no leaks.
**Also this session:** 3.4 (LLM classifier) done. `app/ai/llm.py`'s `OllamaLLMClient`
uses Ollama 0.40.3's real JSON-**schema**-constrained output (confirmed by hitting the
live API before writing code - it's not just `format: "json"`), with `self_score`'s
`minimum`/`maximum` in the schema itself so the model stays in range at generation
time. Prompt is the versioned `app/ai/prompts/classify_v1.txt`, reading
`docs/estimating_rules.md` (a placeholder - client's real estimating guidance hasn't
arrived). `classify_with_llm()` retries up to 3 total on bad JSON / out-of-range
score / an invalid code, fails safe (`flags=["llm_failed"]`) rather than raising, one
call per `group_hash`. **Not wired into `classify.py` yet** - that's 3.6/3.7's job.
Mocked-client tests (10, per the plan) plus `scripts/run_llm_classification.py` run
for real: real codes, real `real_sample.ifc` upload, real qwen2.5 inference -
correctly matched real materials to real codes, correctly refused a bad match on an
ambiguous roof slab, correctly flagged every proxy per the placeholder rules file.
13 elements (the fixture's full count, honestly short of the plan's "50"), real
token counts logged, $0.00 cost. 110/110 pytest, run twice, no leaks.
**Also this session:** 3.5 (jev adapter, parallel + agreement) done.
`projects.classification_engine` (`llm`/`jev`/`both`, **defaults to `"jev"`** -
defaulting to `"llm"` would make every worker-integration test, and CI, call the
real multi-GB Ollama model instead of the fast stub, a regression risk not a style
choice) + `classifications.agreement` (set only on llm/jev rows from a `"both"`
run). `PATCH /projects/{id}` (admin) changes it. `app/ai/classify.py` now reads the
project's engine after rule-matching and calls jev and/or the LLM per group,
writing two rows on `"both"` with `agreement` = whether their codes matched (both
`None` counts as agreement). 116/116 pytest, run twice, no leaks. **Verified live**
with engine `"both"` - every element got two rows, agreement computed correctly.
**The stray-worker bug (see "Process hygiene" above) bit again** mid-verification -
an old worker survived from an earlier live test and raced the fresh one, silently
processing the first live-test upload with pre-3.5 code and making it look like the
engine dispatch hadn't worked. Fixed by killing *every* PID matching `rq worker`,
not just the most recently started one, and confirming zero remain before trusting
the next result - now the strengthened standing rule, not just this session's fix.
**Also this session:** 3.6 (confidence + routing) done — **Phase 3 is now fully
complete except 3.7/3.8** (3.5 directly above was this same session too).
`app/ai/confidence.py` combines self_score/agreement/shortlist-rank/completeness
into `confidence` (`self_score` keeps the raw per-engine value — the schema already
had both columns for exactly this); hard flags force `needs_review` regardless of
score. Wired directly into `classify.py` this time (3.6 *is* the consumer 3.3/3.4
were waiting for). `scripts/calibrate.py` + `app/ai/calibrate.py` reuse P.4's
ground-truth loader, self-tested only (same blocker as P.4/2.7). 146/146 pytest,
run twice, no leaks.
**Two more real bugs caught live, neither by any test — both now fixed and covered
by regression tests:** (1) `app/ai/retrieval.py`'s cache was module-level and
content-keyed (`group_hash`), so a second upload of a similar file in the same
worker process reused a previous job's `CodeList` objects bound to an already-closed
session — see the new standing note above on content-keyed caches. (2) The real LLM
and `hard_flags()` independently report overlapping flags (e.g. both say
`proxy_element`), so stored rows showed duplicates until `_merge_flags()` deduped
them. **Diagnosing both took far longer than it should have because of a third bug:
the kill-worker filter used all session was itself wrong** (see the strengthened
"Process hygiene" note above) — every earlier "confirmed zero workers" this session
was actually leaving real worker processes alive, undetected, the entire time.
**Also this session:** 3.7 (classification job) done — **Phase 3 (3.1–3.7) is now
complete; only 3.8 remains.** `app/ai/classify.py` now commits per rule-matched
element/AI-engine group (not one transaction for the whole call) and takes
`progress_callback` + `force: bool = False` (skips already-classified elements -
true resumability after a crash, not just a retry that redoes everything).
`app/workers/classification.py` (new): `reclassify_ifc_file()` uses `force=True` -
re-running is supposed to re-evaluate everything, matching the project's existing
"latest classification wins" convention rather than deleting old rows.
`POST /projects/{project_id}/files/{file_id}/classify` (admin/estimator) triggers
it. 155/155 pytest, run twice, no leaks. **Verified live for real, including the
force=True path**: a real file's classification count doubled (13→26) after
calling the real endpoint, confirming every element was genuinely re-evaluated.
**A new variant of the process-hygiene problem, not a new bug class:** a worker
left running from an *earlier* sub-phase's live test was consuming the same Redis
queue pytest uses, so it picked up and actually ran a test's enqueued `extract` job,
racing that test's own manual DB state change and producing a confusing, flaky
failure unrelated to the code under test - now documented as a standing risk, not
just a staleness concern, in the "Process hygiene" note above.
**Also this session:** 3.8 (evaluation harness) done — **Phase 3 (3.1–3.8) is now
fully complete.** New migration `10d703fe08b6` adds
`classifications.prompt_tokens`/`completion_tokens` (null for rule/jev rows -
"not applicable" differs from "zero cost"), populated in `classify.py`'s llm
branch - without this, "cost per model" would've been fabricated, since the values
were already computed transiently but never persisted. `app/ai/evaluate.py`:
overall accuracy, auto-accept rate/precision, **unflagged error rate** (wrong
*and* `auto_accepted` - the dangerous silent case), accuracy by family, token
totals, real `$0.00` cost. `scripts/evaluate.py` writes a timestamped `.md`+`.json`
to `data/reports/eval/` (git-ignored). 165/165 pytest, run twice, no leaks.
**Verified live for real**: uploaded a file with `engine="llm"`, let the real
qwen2.5 classify it, ran the real CLI against a hand-built ground truth - 83.3%
accuracy, 100% auto-accept precision, 0% unflagged errors, real token totals
(9584+1429), correct per-family breakdown, valid `.md`/`.json` on disk.
**Also this session:** 4.1 (Projects pages) done - **first frontend sub-phase**.
Regenerated `schema.d.ts` from the live backend (stale since Phase 1 - missing
every endpoint built across Phases 2-3). Needed two small backend additions this
sub-phase surfaced, not pre-existing: `ProjectUpdate.name` + broadened
`PATCH /projects/{id}` to admin/estimator (renaming isn't an admin-only concern
like 3.5's `classification_engine` setting was), and `GET /projects/{project_id}/
files` (list) - didn't exist at all, so the frontend had no way to see a
project's files/status. `project.status` is still always `"draft"` (nothing
transitions it yet - a known gap, not fixed here); the Overview tab shows real
per-file status instead of fabricating a project-level one.
`src/lib/projects/*` hooks, `project-dialog.tsx` (shared create/rename),
`export-button.tsx` (a real working CSV download, not a placeholder).
`/projects` and `/projects/[id]` are real pages now; Elements/3D tabs are
explicitly labeled "coming in a later phase" rather than faked. New shadcn:
`badge`, `dialog`, `tabs`. 168/168 backend pytest, `tsc`/`eslint`/`pnpm build`
all clean. **Verification gap, flagged honestly rather than glossed over:** no
browser/computer-use tool was available in this environment, so every real API
call the hooks make was exercised directly against the live backend (confirmed
correct shapes/behavior), but the actual rendered UI was never click-tested in
a browser - that's still unverified, not just untested.
**Also this session:** 4.2 (upload flow) done. **"Chunked" wasn't built** - the
upload is still one server-proxied multipart POST (2.1's deliberate deferral);
what shipped is real upload-progress via `XMLHttpRequest` (neither `fetch` nor
the typed client fires upload-progress events). Surfaced two more real gaps:
`IfcFileOut.job_id` (nothing told the frontend which job to poll) and
`GET /jobs/{id}` got its first-ever auth check plus a real `JobOut` response
model (previously anyone, logged in or not, could poll any job). `useUploadFile`
/`useJob`/`jobStepLabel()` + `UploadDropzone` (idle/uploading/processing/done/
error, all real, no fabricated step granularity beyond what the backend
actually tracks). New shadcn: `progress`. 170/170 backend pytest, `tsc`/`eslint`/
`pnpm build` clean. **Verified live for real** via curl mirroring the hooks
exactly - real upload, real `job_id`, real polling to `done`, both real error
paths. Same honest gap as 4.1: no browser tool available, so the actual
rendered UI wasn't click-tested. **The stray-worker lesson bit a third variant
of itself**: started a live worker for this verification, forgot to stop it
before the next `pytest` run, got the exact 3.7-shaped race again. Standing
rule reinforced, not just re-learned: stop the worker *before* every pytest
run, not only after a restart.
**Also this session:** 4.3 (results overview) done. `app/ai/summary.py` +
`GET /projects/{project_id}/summary`: `corrected` is always `0` (honest -
reviews don't exist until Phase 6.1); totals-by-code picks exactly one
quantity per element (net > gross > length > count) to avoid double-counting;
warnings reuse 3.6's existing flags rather than new detection logic. **Three
real bugs found while building this, all fixed:** (1) "latest classification
per element" (here and already in `calibrate.py`/`evaluate.py`) wasn't
tie-broken on `created_at` ties, which `engine="both"` produces for real -
added `id DESC` to all three. (2) `Quantity.value` is `NUMERIC(14,4)`, so
psycopg returns a real `Decimal` despite the `Mapped[float]` hint - summing
it into a float accumulator raised `TypeError`; fixed with an explicit cast.
(3) `reviews` has existed since 1.3 but no test had ever touched it before -
`cleanup_project_cascade()` didn't know about it either, hit an FK violation,
and silently left stuck data (see the strengthened "Test cleanup helpers"
note above). Frontend: stat cards, warnings panel, a totals table via a
plain shadcn `table` (not TanStack Table - that's 4.4's own dependency to
introduce). 177/177 backend pytest, `tsc`/`eslint`/`pnpm build` clean.
**Verified live for real**: seeded real rows directly, hit the real endpoint,
every number matched exactly what was seeded. Same honest gap as 4.1/4.2: no
browser tool available, so the rendered UI wasn't click-tested.
**Also this session:** 4.4 (element table) done. New
`GET /projects/{project_id}/elements` returns the full row list (reusing 4.3's
`primary_quantity`/`latest_classifications_by_element` and 3.3's
`guess_family`) - no server-side pagination, same reasoning as 4.3's "virtualise,
don't paginate" call. All filtering/sorting/grouping/search is client-side via
`@tanstack/react-table` + `@tanstack/react-virtual`. **A real version trap caught
before writing component code**: `pnpm add @tanstack/react-table` installs v9 by
default, a from-scratch rewrite with none of the stable v8 API - pinned to
`8.21.3` instead (see the new standing note under "Known Windows/environment
quirks" above). Two more real bugs caught by `tsc`/`eslint`: the quantity column
would have sorted lexicographically against its display string instead of
numerically, and `elements ?? []` created a fresh array reference every render,
defeating every downstream `useMemo`. 182/182 backend pytest, `tsc`/`eslint`/
`pnpm build` clean. Verified live for real: a classified and an unclassified
element both matched exactly. Same honest gap as 4.1-4.3: no browser tool
available, and this is the sub-phase where that matters most (most of 4.4 *is*
interaction - filtering, sorting, grouping, the column picker).
**Also this session, at the user's request, unrelated to 4.4's scope**:
downloaded all 18 real-world IFC files from
[youshengCode/IfcSampleFiles](https://github.com/youshengCode/IfcSampleFiles)
into `data/sample_ifc_files/` (~176MB, git-ignored) for manual larger-scale
testing.
**Next up:** Phase 4.5 — element detail panel (side panel on row click:
properties, material layers, quantities with source, AI reasoning, candidates
with scores, similar examples, review history). No open decisions block it,
though review history will be empty (reviews don't exist until Phase 6.1,
same honest-zero situation as 4.3's "corrected" count) and
candidates/similar-examples need real `code_list`/`example_memory` data to be
meaningfully non-empty.
