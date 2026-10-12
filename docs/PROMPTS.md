# Prompts for Claude Code (VS Code) — one per sub-phase

## How to use
1. Put `CLAUDE.md` in the repo root and `IMPLEMENTATION_PLAN.md` + this file in `/docs`.
2. Start a fresh Claude session for each sub-phase (clear the previous conversation).
3. Create a branch: `git checkout -b phase-2.3-qto-quantities`.
4. Paste the **Start template** with the sub-phase prompt filled in.
5. Claude proposes a plan → you check it → reply `go`.
6. When Claude finishes: review the diff, run the app, check the "Done when" yourself, commit, merge.
7. If something breaks, paste the error and say: "Fix this. Don't change unrelated code."

## Start template (paste at the start of every session)
```
Read CLAUDE.md and docs/IMPLEMENTATION_PLAN.md.
We are doing sub-phase <X.Y — name>.

<paste the sub-phase prompt below>

First: explain your plan in max 10 bullets, list files you will create or change, and any
new dependency with the reason. Wait for my "go" before writing code.
After coding: run tests and linters, show results, tick the box in IMPLEMENTATION_PLAN.md,
update "Current status" in CLAUDE.md, and suggest a commit message.
```

## Handy follow-up prompts
- "Show me how to test this manually, step by step."
- "Write the missing tests for what you just built."
- "Review your own diff for bugs, missing error handling and security issues."
- "Explain this file to me simply, I need to present it to the client."
- "We're at the end of the phase. Check every 'Done when' in this phase and report pass/fail."

---

## Phase 0 — Discovery tooling

### 0.1 IFC audit script
```
Create scripts/ifc_audit.py using ifcopenshell. Input: one or more IFC paths (or a folder).
For each file report: IFC schema, authoring application (IfcApplication), units, storeys,
element count per IFC class, % IfcBuildingElementProxy, % elements with any Qto set,
% with material layer sets, most common Pset names, and elements without storey.
Write a markdown report to data/reports/audit_<filename>.md and print a short summary.
Handle large files without loading geometry. Add a small pytest using a fixture IFC.
```

### 0.2 Code list cleaner
```
Create scripts/prepare_codes.py. Inputs: the IBIS code list and internal element list
(xlsx or csv, paths as args; column names configurable via a small YAML mapping).
Output data/codes_clean.csv with: ibis_code, internal_element, description, unit, family.
Validate rows with a Pydantic model; report duplicates, missing descriptions, unknown units.
Family = one of: foundation, wall, floor, roof, column, beam, stair, opening, finish, other
(rules from a configurable keyword map). Add tests.
```

### 0.3 Ground-truth format
```
Create the ground-truth template data/ground_truth_template.csv with columns: file, global_id,
expected_ibis_code, expected_internal_element, expected_quantity, unit, notes.
Add scripts/ground_truth.py with a loader and validator (Pydantic), checks that codes exist in
codes_clean.csv, and prints coverage stats. Tests with a 20-row sample fixture.
```

## Phase 1 — Foundation

### 1.1 Monorepo scaffold
```
Scaffold the monorepo exactly as in CLAUDE.md: apps/web (Next.js 15, TS strict, Tailwind,
shadcn/ui), apps/api (FastAPI, uv for dependencies), scripts, data (git-ignored), docs.
docker-compose.yml with postgres:16 + pgvector and redis. Add .env.example, .gitignore,
pre-commit (ruff, black, eslint, prettier) and a README with setup steps.
```

### 1.2 Backend skeleton
```
Build the FastAPI skeleton in apps/api: settings via pydantic-settings, structured logging,
global error handler returning {"error": {"code","message"}}, SQLAlchemy 2 engine/session,
Alembic setup, GET /health that checks database and redis. Add pytest config and one test.
```

### 1.3 Database schema
```
Create SQLAlchemy models and the first Alembic migration for: users, projects, ifc_files,
elements, quantities, code_list (with pgvector embedding column), classifications, reviews,
example_memory (pgvector), rules, exports, jobs. Use the fields from the "Core data model"
section of the MVP plan (ask me if unsure). Add indexes on foreign keys, global_id, status.
Test that the migration upgrades and downgrades cleanly.
```

### 1.4 Worker and jobs
```
Add an RQ worker in apps/api/app/workers with a helper to create jobs, update progress and
store errors in the jobs table. Endpoint GET /jobs/{id}. Add a demo job that sleeps and
reports progress, and a test that runs it with a fake queue.
```

### 1.5 Auth and roles
```
Implement auth: POST /auth/login, POST /auth/logout, GET /auth/me. Password hashing with
argon2, JWT in httpOnly cookie. Roles admin, estimator, viewer with a FastAPI dependency
require_role(...). Seed command to create the first admin. Tests for each role's access.
```

### 1.6 Frontend skeleton
```
Build the Next.js app shell: login page, protected layout with sidebar (Projects, Admin for
admins), user menu, logout. Generate a typed API client from the FastAPI OpenAPI schema into
apps/web/lib/api, set up React Query. Show an empty Projects page after login.
```

### 1.7 CI and staging
```
Add GitHub Actions: lint + test for api and web, build Docker images, deploy to staging on
merge to main (target: <my server / provider>). Add Dockerfiles for api, worker and web.
Document required secrets in README. Ask me for server details before writing deploy steps.
```

## Phase 2 — IFC processing engine

### 2.1 Projects and upload API
```
Implement projects CRUD (/projects) and POST /projects/{id}/files for IFC upload.
Support chunked/resumable upload or a presigned S3 URL flow (propose which). Store the file
in S3-compatible storage, validate with ifcopenshell.open, record schema and size, create a
processing job. Corrupt or non-IFC files return a clear error. Tests with fixtures.
```

### 2.2 Element extraction
```
In apps/api/app/ifc/extract.py, extract building elements (IfcWall, IfcWallStandardCase,
IfcSlab, IfcRoof, IfcFooting, IfcColumn, IfcBeam, IfcStair, IfcRailing, IfcDoor, IfcWindow,
IfcCovering, IfcPile, IfcBuildingElementProxy). For each: GlobalId, class, PredefinedType,
Name, ObjectType, storey (via containment), materials and material layer sets with thickness,
all Psets (ifcopenshell.util.element.get_psets), IsExternal and LoadBearing.
Save to the elements table in batches. Run as a worker job step with progress.
Tests on fixture IFC files assert counts and key fields.
```

### 2.3 Quantities from Qto
```
In apps/api/app/ifc/quantities.py read standard Qto sets (Qto_WallBaseQuantities,
Qto_SlabBaseQuantities, Qto_FootingBaseQuantities, etc.) and store length, net/gross area,
net/gross volume, count. Convert to SI using the file's unit assignment. source = "qto".
Tests with expected values from the fixture.
```

### 2.4 Geometry fallback
```
When Qto values are missing, compute quantities with ifcopenshell.geom (use world coords,
reuse settings, iterate efficiently). Walls: net side area with openings deducted, volume,
length. Slabs/footings: area and volume. Composites: quantity per material layer using layer
thickness. source = "geometry". Compare with Qto where both exist and log the deviation.
Keep memory usage under control on large files.
```

### 2.5 Element profiles and grouping
```
Create apps/api/app/ifc/profile.py that builds a deterministic, compact profile_text per
element (class, type, name, material layers with thickness, storey, IsExternal, LoadBearing,
top relevant Psets, quantities). Also compute a group_hash so identical element types are
classified once. Snapshot tests for profiles.
```

### 2.6 Fragments for the 3D viewer
```
Convert each uploaded IFC to That Open fragments for fast loading. Propose the approach
(Node worker using @thatopen/components IfcLoader, called from the Python worker, or
conversion in the browser on first load and cached). Store the result and expose
GET /files/{id}/model. Keep a mapping between viewer IDs and GlobalIds.
```

### 2.7 Extraction comparison report
```
Create scripts/compare_extraction.py: compare extracted elements and quantities with
data/ground_truth.csv. Report element coverage, missing elements by class, and quantity
deviation per expected code. Output markdown in data/reports/.
```

## Phase 3 — AI classification engine

### 3.1 Code list API and embeddings
```
Admin endpoints to upload codes (csv/xlsx in the codes_clean format), list, search and
version them. Create an Embedder interface with one provider implementation (configurable
via env). Embed "family + internal_element + description" per code and store in pgvector.
Add a similarity search function filtered by family. Tests with a fake embedder.
```

### 3.2 Rule engine
```
Create apps/api/app/ai/rules.py. Rule = JSON conditions on ifc_class, predefined_type,
material keywords, thickness range, IsExternal, LoadBearing, storey keywords → ibis code +
internal element, with priority. Evaluate before AI; matches get confidence 1.0 and
source "rule". Admin CRUD endpoints. Load initial rules from data/rules_initial.json.
Thorough unit tests.
```

### 3.3 Retrieval
```
Create apps/api/app/ai/retrieval.py: (a) shortlist top-15 codes for an element profile
within its family (fallback: all families if too few); (b) top-5 most similar approved
examples from example_memory with their codes. Cache per group_hash. Tests with seeded data.
```

### 3.4 LLM classifier
```
Create apps/api/app/ai/llm.py with an LLMClient interface and one provider implementation.
Prompt includes: role and task, element profile, candidate codes with descriptions, similar
approved examples, short estimating rules from docs/estimating_rules.md. The model must return
JSON: {ibis_code, internal_element, reasoning, self_score 0-1, flags[]}; code must be one of
the candidates or "NONE". Validate with Pydantic, retry up to 2 times, batch per group_hash,
log tokens and cost per project. Put the prompt in a versioned template file.
Tests with a mocked client; a manual script to run on 50 real elements.
```

### 3.5 jev adapter
```
Create apps/api/app/ai/jev.py with a JevClient interface. If I give you the jev API docs,
implement it; otherwise create a stub returning NONE. Run jev alongside the LLM when the
project engine setting is "both", store both results and whether they agree.
```

### 3.6 Confidence and routing
```
Create apps/api/app/ai/confidence.py. Final score combines self_score, rule/LLM/jev agreement,
distance of chosen code in the shortlist, and data completeness. Hard flags force review:
proxy element, missing quantity, composite element, unknown material, code "NONE".
Thresholds from settings. Add scripts/calibrate.py that uses ground truth to choose the lowest
threshold where auto-accepted precision >= 95%, and prints the resulting auto-accept rate.
```

### 3.7 Classification job
```
Wire the pipeline into the worker after extraction: rules → retrieval → LLM/jev → confidence
→ save classifications with status auto_accepted or needs_review. Progress updates per batch,
resumable on failure. Endpoint POST /files/{id}/classify to re-run. End-to-end test on fixture.
```

### 3.8 Evaluation harness
```
Create scripts/evaluate.py: run classification on reference files (or read stored results),
compare with ground truth, and report overall accuracy, auto-accept rate, precision of
auto-accepted items, unflagged errors, accuracy per family, cost per model. Save a timestamped
markdown + JSON report in data/reports/eval/. This is what we show at the week-6 gate.
```

## Phase 4 — Frontend application

### 4.1 Projects pages
```
Build the projects list (search, status badge, last activity), create/edit project dialog,
and project detail page shell with tabs: Overview, Elements, 3D, Export. Use React Query hooks.
```

### 4.2 Upload flow
```
On the project page add IFC upload with drag-and-drop, upload progress, then job progress
per step (validate, extract, quantities, classify) by polling /jobs/{id}. Clear error states.
```

### 4.3 Results overview
```
Overview tab: cards for total elements, auto-accepted, needs review, corrected; table of
totals per IBIS code with unit; warnings panel (missing quantities, proxies, unmapped).
```

### 4.4 Element table
```
Elements tab: TanStack Table with virtualisation. Columns: element, IFC class, storey,
material, quantity + unit, suggested code, internal element, confidence, status.
Filters: status, confidence range, family, storey; search; sort; group by group_hash;
column picker. Must stay smooth with 5,000+ rows. Server-side paging if needed.
```

### 4.5 Element detail panel
```
Side panel on row click: properties, material layers, quantities with source, AI reasoning,
candidate codes with scores, similar past examples, review history and comments.
```

### 4.6 Admin area
```
Admin pages: users and roles, code list import and browse/search, rules list (suggested vs
active, edit, activate), confidence threshold setting. Only visible to admins.
```

### 4.7 UX polish and E2E test
```
Add keyboard shortcuts (A approve, C correct, J/K next/previous), loading skeletons, empty and
error states, consistent spacing. Write a Playwright test: login → upload fixture → wait for
job → open elements → approve one item.
```

## Phase 5 — 3D viewer

### 5.1 Viewer component
```
Create a Viewer component with @thatopen/components: load the fragments from
GET /files/{id}/model, orbit/zoom, fit to model, storey filter, clipping plane, hide/isolate.
Load it only on the 3D tab (dynamic import, no SSR).
```

### 5.2 Table and viewer sync
```
Two-way selection: selecting a table row highlights and zooms the element by GlobalId;
clicking an element in 3D selects its row and opens the detail panel. Support multi-select
in the viewer for bulk review. Share selection state via a small store.
```

### 5.3 Colour modes
```
Add colour modes: by review status, by code family, and "flagged only" (others ghosted).
Add a legend.
```

### 5.4 Viewer performance
```
Test with the largest reference model. Measure load time and memory. Apply improvements
(lazy loading, culling, storey-by-storey loading). Show a friendly message if a model is too
large. Report the before/after numbers.
```

## Phase 6 — Review and learning loop

### 6.1 Review actions
```
API + UI for: approve, correct (searchable code picker showing candidates first), bulk
approve/correct for a group or selection, undo last action, comments. Every action writes a
reviews row and updates classification status.
```

### 6.2 Composite split
```
For composite elements (material layer sets), suggest one line per layer with its own
quantity and suggested code. The user confirms or edits the split. Store split lines linked
to the parent element.
```

### 6.3 Example memory write-back
```
On approve/correct, store the element profile, its embedding and the final code in
example_memory. Retrieval (3.3) must use it immediately. Test: a correction on project A
changes the suggestion for an identical element type on project B.
```

### 6.4 Re-classify remaining
```
Add "Re-run AI on unreviewed items" (POST /files/{id}/reclassify) that reprocesses only
needs_review items using the latest examples and rules. Show a diff of changed suggestions.
```

### 6.5 Rule suggestions
```
Detect when the same correction pattern (same profile features → same code) happens 3+ times
and create a suggested rule. Admin can approve, edit or dismiss it in the Rules page.
```

### 6.6 Audit trail
```
Record who/when/before/after for every classification change and admin change. Show history
per element and a review-progress bar per project.
```

## Phase 7 — Export and reporting

### 7.1 Excel export
```
Using openpyxl and the client's template (data/templates/ibis_export.xlsx), generate:
Summary sheet (quantities per IBIS code and internal element, unit, totals), Detail sheet
(each element: GlobalId, storey, quantity, code, reviewer), Warnings sheet. Store the file,
record an exports row, return a download link. Test that totals equal the database totals.
```

### 7.2 Export rules
```
Before export, check review completeness. Setting: "warn" or "block". Show unresolved items
in the UI with a link to filter them.
```

### 7.3 Dashboard
```
Reporting page: per project auto-accept rate, number of corrections, accuracy vs approved
result, AI cost; trend chart across projects. Admin and estimators can view.
```

## Phase 8 — QA and hardening

### 8.1 Test coverage
```
Check test coverage for apps/api/app/ifc and apps/api/app/ai and the main API routes.
Add missing unit and integration tests, and Playwright tests for: upload, review, 3D sync,
export, admin code import. Make CI green.
```

### 8.2 Blind accuracy run
```
Run scripts/evaluate.py on the blind reference project. Produce an error analysis grouped by
cause (data quality, ambiguous code, AI error, quantity method) with examples, and propose
final thresholds. Do not change thresholds without my approval.
```

### 8.3 Security pass
```
Review the code for security: authorization on every endpoint, file upload validation and size
limits, rate limiting, secrets handling, CORS, dependency vulnerabilities (pip-audit, pnpm audit),
and that no client data or prompts are logged. Fix issues and list what you changed.
```

### 8.4 Reliability
```
Add job retries with backoff, dead-letter handling, Sentry for api/worker/web, alerts on failed
jobs, a simple load test (5 parallel uploads), and a documented backup + restore procedure that
you test against staging.
```

## Phase 9 — Deployment and handover

### 9.1 Production deploy
```
Prepare production: environment config, domain + SSL, migrations on deploy, backups, monitoring,
and a seed script for final code lists, rules and admin user. Write docs/runbook.md.
```

### 9.2 UAT support
```
Create docs/uat_checklist.md covering every user journey with expected results. After UAT,
I'll paste findings — fix them one by one, each with a test.
```

### 9.3 Documentation
```
Write docs/user_guide.md (estimator), docs/admin_guide.md (code lists, rules, thresholds,
users) and docs/architecture.md (components, data flow, AI pipeline, deployment).
Simple language, screenshots placeholders where useful.
```
