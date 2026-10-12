# Implementation Plan — IFC-to-IBIS Estimator MVP

Tick each box when done. Each sub-phase = one Claude Code session = one branch.
Prompts for each sub-phase are in `docs/PROMPTS.md` (same numbers).

Legend: **Done when** = acceptance check Claude must show passing before the box is ticked.

---

## Phase 0 — Discovery tooling (week 1)
Human work (client calls, wireframes) happens in parallel; Claude builds the tools.

- [ ] **0.1 IFC audit script** — `scripts/ifc_audit.py` reports schema, element counts per class,
      % proxies, Pset/Qto coverage, material-layer coverage, units, storeys, authoring tool.
      Done when: runs on all files in `data/ifc/` and writes `data/reports/audit_<file>.md`.
- [ ] **0.2 Code list importer (offline)** — `scripts/prepare_codes.py` cleans IBIS + internal lists
      into `data/codes_clean.csv` (code, internal_element, description, unit, family).
      Done when: duplicates/missing fields reported; output validated by a Pydantic model.
- [ ] **0.3 Ground-truth format** — `data/ground_truth.csv` template + loader + validator
      (global_id, file, expected_code, expected_internal_element, expected_quantity, unit).
      Done when: validator passes on a hand-filled sample of 20 rows.

## Phase 1 — Foundation (week 2)
- [x] **1.1 Monorepo scaffold** — folders per CLAUDE.md, docker-compose (postgres+pgvector, redis),
      .env.example, pre-commit (ruff, black, eslint, prettier), README.
      Done when: `docker compose up` starts db + redis; linters run clean.
      ✅ 2026-10-13 — also added Garage (S3-compatible storage) to docker-compose since
      MinIO's Docker Hub images now require a paid account; see CLAUDE.md decision log.
      `docker compose up` → postgres+redis+garage all healthy, pgvector extension installs,
      ruff/black/pytest clean on api, eslint/prettier/build clean on web.
- [ ] **1.2 Backend skeleton** — FastAPI app, settings, logging, error format, `/health`,
      SQLAlchemy session, Alembic configured.
      Done when: `/health` returns db + redis status; pytest runs.
- [ ] **1.3 Database schema** — all tables: users, projects, ifc_files, elements, quantities,
      code_list (vector), classifications, reviews, example_memory (vector), rules, exports, jobs.
      Done when: migration up/down works; model tests pass.
- [ ] **1.4 Worker + jobs** — RQ worker, `jobs` table with status/progress, `GET /jobs/{id}`.
      Done when: a demo job reports progress 0→100 and is visible via API.
- [ ] **1.5 Auth + roles** — login/logout, JWT (httpOnly cookie), roles admin/estimator/viewer,
      permission dependency, seed admin user.
      Done when: role tests pass (viewer cannot upload, estimator cannot edit code list).
- [ ] **1.6 Frontend skeleton** — Next.js app shell, login page, protected layout, navigation,
      typed API client generated from OpenAPI, React Query provider.
      Done when: login → empty projects page works against local API.
- [ ] **1.7 CI + staging** — GitHub Actions: lint, test, build images; deploy to staging.
      Done when: a merge to main updates staging.

## Phase 2 — IFC processing engine (weeks 3–4)
- [ ] **2.1 Projects + upload API** — CRUD projects; chunked IFC upload to S3-compatible storage;
      schema validation with IfcOpenShell; create processing job.
      Done when: upload of fixture file creates ifc_files row + job; corrupt file returns clear error.
- [ ] **2.2 Element extraction** — walls, slabs, roofs, footings, columns, beams, stairs, railings,
      doors, windows, coverings, proxies: GlobalId, class, predefined type, name, object type,
      storey, materials + layer sets (thickness), all Psets, IsExternal/LoadBearing.
      Done when: fixture tests assert counts and fields; large file processes without memory blow-up.
- [ ] **2.3 Quantities from Qto** — read standard Qto sets; normalise to SI; source = qto.
      Done when: wall/slab/footing quantities match expected fixture values.
- [ ] **2.4 Geometry fallback** — ifcopenshell.geom for area/volume/length when Qto missing;
      opening deductions for walls; per-layer quantities for composites; source = geometry.
      Done when: fallback results within ±3% of Qto on elements that have both.
- [ ] **2.5 Element profiles + grouping** — `profile_text` per element; group hash for identical types.
      Done when: profiles deterministic (snapshot tests); grouping reduces element count in report.
- [ ] **2.6 Fragments for viewer** — convert IFC to That Open fragments in worker (Node script or
      service), store file, map fragment IDs ↔ GlobalIds.
      Done when: fragments file downloadable via `GET /files/{id}/model`.
- [ ] **2.7 Extraction report** — `scripts/compare_extraction.py` vs ground truth: element coverage,
      quantity deviation per code.
      Done when: report generated for all reference projects.

## Phase 3 — AI classification engine (weeks 4–6)
- [ ] **3.1 Code list import API + embeddings** — admin upload of codes (CSV/XLSX), versioning,
      `Embedder` interface, embeddings stored in pgvector, family tags.
      Done when: similarity search returns sensible codes for 10 sample queries (test).
- [ ] **3.2 Rule engine** — JSON rule conditions (class, type, material, thickness range, flags) →
      code; rules evaluated first; confidence 1.0, source = rule; admin CRUD API.
      Done when: unit tests cover match/no-match/priority.
- [ ] **3.3 Retrieval** — shortlist top-15 codes within family; example memory top-5 similar approved
      elements; caching per group hash.
      Done when: tests with seeded examples return expected neighbours.
- [ ] **3.4 LLM classifier** — `LLMClient` interface + provider implementation; prompt template
      (profile + candidates + examples + rules summary); strict JSON schema
      {code, internal_element, reasoning, self_score, flags}; Pydantic validation; retries; batching
      per group; token/cost logging.
      Done when: mocked-provider tests pass; live run on 50 elements succeeds and logs cost.
- [ ] **3.5 jev adapter** — `JevClient` (or stub if no access yet); run in parallel with LLM;
      store agreement; per-project engine setting (llm | jev | both).
      Done when: adapter tested with recorded responses or stub.
- [ ] **3.6 Confidence + routing** — combine self_score, rule/LLM/jev agreement, shortlist distance,
      data completeness; hard flags (proxy, missing quantity, composite, unknown material);
      thresholds configurable; status = auto_accepted | needs_review.
      Done when: calibration script picks threshold so auto-accepted precision ≥ 95% on ground truth.
- [ ] **3.7 Classification job** — worker step after extraction; progress reporting; re-run endpoint.
      Done when: upload → extraction → classification runs end to end on a fixture.
- [ ] **3.8 Evaluation harness** — `scripts/evaluate.py`: accuracy, auto-accept rate, missed errors,
      cost per model, confusion by family; results saved with timestamp.
      Done when: report produced for all reference projects (input to week-6 gate).

## Phase 4 — Frontend application (weeks 4–7)
- [ ] **4.1 Projects pages** — list (search, status), create/edit form, project detail shell.
- [ ] **4.2 Upload flow** — drag-and-drop, chunked upload, job progress per step, error states.
- [ ] **4.3 Results overview** — counts (total, auto-accepted, to review, corrected), totals per IBIS
      code, warnings panel.
- [ ] **4.4 Element table** — virtualised, filters (status, confidence, family, storey), sort, search,
      group by element type, column picker; handles 5,000+ rows smoothly.
- [ ] **4.5 Element detail panel** — properties, layers, quantities with source, AI reasoning,
      candidates with scores, similar examples, review history.
- [ ] **4.6 Admin area** — users/roles, code list import + browse, rules (suggested/active), thresholds.
- [ ] **4.7 UX polish** — keyboard shortcuts (A approve, C correct, J/K next/prev), empty/loading/error
      states, consistent design.
      Done when (phase): Playwright test covers login → upload → open results → approve one item.

## Phase 5 — 3D viewer (weeks 6.5–8)
- [ ] **5.1 Viewer component** — load fragments, camera controls, fit, storey filter, clipping, isolate.
- [ ] **5.2 Table ↔ viewer sync** — row click highlights/zooms; element click opens row + detail;
      multi-select for bulk review.
- [ ] **5.3 Colour modes** — by status, by code family, flagged only.
- [ ] **5.4 Performance** — test largest model; lazy loading; graceful message if too large.
      Done when (phase): largest reference model loads < 20 s; any row found in 3D in one click.

## Phase 6 — Review and learning loop (weeks 7–8.5)
- [ ] **6.1 Review API + UI** — approve, correct (searchable code picker with suggestions),
      bulk approve/correct per group, undo, comments.
- [ ] **6.2 Composite split** — suggest one line per material layer with layer quantities; user confirms.
- [ ] **6.3 Example memory write-back** — every approve/correct stored with embedding; used by 3.3.
      Done when: correction on project A changes suggestion for same element type on project B (test).
- [ ] **6.4 Re-classify remaining** — button/job to re-run AI on unreviewed items after corrections.
- [ ] **6.5 Rule suggestions** — same correction ≥ 3 times → suggested rule; admin approves.
- [ ] **6.6 Audit trail** — who/when/before/after for every change; review progress per project.

## Phase 7 — Export and reporting (weeks 8–9)
- [ ] **7.1 Excel export** — summary sheet per IBIS code + internal element, detail sheet with
      GlobalIds, warnings sheet; matches client template; export history.
- [ ] **7.2 Export rules** — warn or block when review incomplete (configurable).
- [ ] **7.3 Accuracy/usage dashboard** — per project: auto-accept rate, corrections, accuracy, AI cost;
      trend across projects.
      Done when (phase): client imports two exports into IBIS without manual edits.

## Phase 8 — QA, validation, hardening (weeks 8.5–10.5)
- [ ] **8.1 Test coverage** — unit (ifc, ai), API integration, Playwright E2E main journeys; CI green.
- [ ] **8.2 Blind accuracy run** — evaluate on project not used in tuning; error analysis by cause;
      final thresholds.
- [ ] **8.3 Security pass** — authz review, input/file validation, rate limiting, secrets, dependency
      audit, no client data in logs.
- [ ] **8.4 Reliability** — job retries, failure alerts (Sentry), concurrent upload load test,
      backup + restore test.

## Phase 9 — Deployment and handover (weeks 10–11)
- [ ] **9.1 Production deploy** — prod environment, domain, SSL, monitoring, backups, seed codes/rules/users.
- [ ] **9.2 UAT support** — UAT checklist, fix findings, release notes.
- [ ] **9.3 Documentation** — user guide, admin guide, architecture, deployment runbook.

---

## Gates
- **Design sign-off** (end week 1.5): scope, wireframes, data model, accuracy targets, Excel format.
- **AI accuracy checkpoint** (end week 6): evaluate.py meets interim targets (overall ≥ 75%,
  auto-accept precision ≥ 95%) or approach is adjusted.
- **UAT and go-live** (end week 11): client sign-off.

## MVP targets
Extraction ≥ 95% · quantity deviation ≤ ±3% · overall accuracy ≥ 80% before review ·
auto-accept precision ≥ 95% · unflagged errors ≤ 3% · 100 MB model < 10 min · review time −50%.
