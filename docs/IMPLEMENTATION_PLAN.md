# Implementation Plan — IFC-to-IBIS Estimator MVP

Tick each box when done. Each sub-phase = one Claude Code session = one branch.
Prompts for each sub-phase are in `docs/PROMPTS.md` (same numbers).

Legend: **Done when** = acceptance check Claude must show passing before the box is ticked.

---

## ⚠ Current priority: Phase P (minimal PoC), not the full phase order below

As of 2026-10-13, **Phase P is the actual current priority** — see immediately below.
Phases 0–9 remain the target if the client commits to a full build, but nothing past
Phase P should be worked on without an explicit decision to resume the full plan. See
CLAUDE.md's "Scope realignment" note in the decision log for the context.

## Phase P — Minimal PoC (current priority — trust-based, unpaid, ~1–2 days)

**Context:** njderidder (not the end client — a friend of the construction company's
owner) is self-financing this to convince the client to commit to a full build at all.
No contract exists yet. He explicitly asked for something much smaller than Phases
0–9: extract → match via jev → show results + flag uncertain ones → compare against
manually-verified calculations. 3D viewer, full frontend, auth/RBAC enforcement,
rules+embeddings+LLM layers, review/correction loop, export, deployment are all
explicitly deferred — not needed to prove the concept, only needed if the client says
yes afterward.

**Blocked on, from njderidder's side:** jev API credentials (not yet confirmed —
he listed IFC files/IBIS codes/reference calcs as in progress but did not mention jev
access), the 2 example IFC files, the internal IBIS code list, reference calculations.

**Already reusable as-is, no rework needed:** the IFC extraction pipeline (sub-phases
2.2–2.5 — element extraction, Qto quantities, geometry fallback, profiling/grouping).
This is exactly step 1 of his 4-step ask.

- [ ] **P.1 jev client** — `app/ai/jev.py`: a `JevClient` wrapping jev's real API
      (same stubbed-until-credentials-exist pattern as other provider clients in this
      codebase). Given one element's `profile_text`, returns a suggested IBIS
      code + confidence/flag. Buildable now as a stub even without real jev access.
      Done when: unit-testable against a stub/fake response; ready to swap in real
      credentials with no code change once they arrive.
- [ ] **P.2 Classification step** — worker step after profiling (2.5): calls jev
      **once per unique `group_hash`**, not per element — reuses 2.5's grouping
      specifically to cut jev API calls/cost, which matters since njderidder is
      paying for API usage out of pocket. Stores the result (reuse the existing
      `classifications` table, `source="jev"`).
      Done when: runs end-to-end against a stubbed jev response on both test
      fixtures; real jev swap-in requires no code change, only credentials.
- [ ] **P.3 Minimal results output** — the simplest thing that shows classifications
      and flags uncertain matches. Default toward a script exporting to Excel/CSV
      (no frontend work, directly shareable) over a web page, unless a quick glance
      in the browser is specifically wanted — decide concretely when building this,
      not before.
      Done when: njderidder can open the output and see element → suggested code →
      confidence/flag, without needing to run any code himself.
- [ ] **P.4 Accuracy comparison** — script comparing jev's suggested codes against the
      manually-verified reference calculations, once provided. Scoped down from
      2.7/3.8's full evaluation harness — just a % match and a list of mismatches,
      not cost tracking or per-family breakdowns.
      Done when: produces one number (accuracy %) + a mismatch list from real data.

**Explicitly not in scope for Phase P**, even though it exists in this repo already:
auth/RBAC enforcement, Docker/CI hardening, 3D viewer, rules engine + embeddings
shortlist + LLM classifier (beyond jev alone), review/correction loop, export
formatting, admin UI, production deployment. All of that is real, tested work — it's
just scoped for *if* the client commits, not for proving the concept to them.

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
- [x] **1.2 Backend skeleton** — FastAPI app, settings, logging, error format, `/health`,
      SQLAlchemy session, Alembic configured.
      Done when: `/health` returns db + redis status; pytest runs.
      ✅ 2026-10-13 — `/health` reports `{"status","database","redis"}`, both `ok` against
      local docker-compose. Uniform `{"error":{"code","message"}}` shape verified for
      explicit HTTPExceptions, unhandled exceptions, and routing-level 404s (had to
      register on `starlette.exceptions.HTTPException`, not `fastapi.exceptions.HTTPException`
      — the latter is a subclass in the installed FastAPI version and routing raises the
      base class, so a handler on the subclass alone misses it). Alembic upgrade/downgrade
      verified against local Postgres. 5/5 pytest, ruff/black clean.
- [x] **1.3 Database schema** — all tables: users, projects, ifc_files, elements, quantities,
      code_list (vector), classifications, reviews, example_memory (vector), rules, exports, jobs.
      Done when: migration up/down works; model tests pass.
      ✅ 2026-10-13 — all 12 tables created (`app/db/models/`), verified upgrade → downgrade
      → upgrade clean against local Postgres. `code_list`/`example_memory` embeddings at
      dim 1536 (placeholder — see CLAUDE.md note, revisit once an embedding provider is
      picked). Had to hand-fix the autogenerated migration: it used
      `pgvector.sqlalchemy.vector.VECTOR` without importing it; fixed there and in
      `script.py.mako` for future autogenerates. 6/6 pytest, ruff/black clean.
- [x] **1.4 Worker + jobs** — RQ worker, `jobs` table with status/progress, `GET /jobs/{id}`.
      Done when: a demo job reports progress 0→100 and is visible via API.
      ✅ 2026-10-13 — verified with a real worker (not just tests): RQ's default worker
      uses `os.fork()`, unavailable on Windows — use `rq worker --worker-class
      rq.worker.SimpleWorker` there (documented in README). Real run: queued → running →
      done, progress 0→100, visible via `GET /jobs/{id}`. Tests use fakeredis + RQ sync
      mode so CI/Windows don't need a real worker process. 10/10 pytest, ruff/black clean.
- [x] **1.5 Auth + roles** — login/logout, JWT (httpOnly cookie), roles admin/estimator/viewer,
      permission dependency, seed admin user.
      Done when: role tests pass (viewer cannot upload, estimator cannot edit code list).
      ✅ 2026-10-13 — login/logout/me working against real app+DB; `require_role` verified
      with admin/estimator/viewer users against an isolated protected route (no real
      admin-only business route exists yet — upload/code-list endpoints come in Phase 2/3
      and will use the same dependency). `app.cli seed-admin` creates/promotes an admin,
      verified manually end to end. 15/15 pytest, ruff/black clean.
- [x] **1.6 Frontend skeleton** — Next.js app shell, login page, protected layout, navigation,
      typed API client generated from OpenAPI, React Query provider.
      Done when: login → empty projects page works against local API.
      ✅ 2026-10-13 — verified with a real browser (one-off Playwright script, not
      committed): / → /login → sign in → /projects renders, Admin link shows for an
      admin role, logout → /login, protected pages bounce back to /login when logged
      out. Had to add CORS to the backend (credentialed cookie across localhost:3000 ↔
      :8000) and use `render` instead of `asChild` on DropdownMenuTrigger — this shadcn
      install is on Base UI, not Radix. eslint/prettier/build clean on web; 15/15 pytest,
      ruff/black clean on api.
- [ ] **1.7 CI + staging** — GitHub Actions: lint, test, build images; deploy to staging.
      Done when: a merge to main updates staging.
      ⏸️ 2026-10-13 — CI done and verified: `.github/workflows/ci.yml` runs ruff/black/
      pytest (api, against real Postgres+Redis service containers), eslint/build (web),
      then builds all three Docker images. All three images were also run-tested
      locally against the real docker-compose stack (api `/health` ok, worker processed
      a real job end to end, web served `/`→`/login`), not just "docker build" succeeding.
      **Not done:** the actual deploy-to-staging step — no server/provider target exists
      yet (user chose to skip rather than guess; plan itself says ask first). Box stays
      unchecked until that exists; revisit here or in Phase 9. Nothing else in Phase 1
      depends on this.

## Phase 2 — IFC processing engine (weeks 3–4)
- [x] **2.1 Projects + upload API** — CRUD projects; chunked IFC upload to S3-compatible storage;
      schema validation with IfcOpenShell; create processing job.
      Done when: upload of fixture file creates ifc_files row + job; corrupt file returns clear error.
      ✅ 2026-10-13 — server-proxied upload (not chunked/presigned — no upload UI exists
      yet to pair that with, see Phase 4.2). Verified both via pytest (23/23) and live
      against the real stack: real login → real upload → file confirmed present in the
      Garage bucket (`garage bucket info`) → job verified done/progress 100 via the real
      worker. Corrupt file → clean 400, not a 500. The processing job is a stub for now
      (marks done, no real parsing) — Phase 2.2 fills in the actual extraction.
- [x] **2.2 Element extraction** — walls, slabs, roofs, footings, columns, beams, stairs, railings,
      doors, windows, coverings, proxies: GlobalId, class, predefined type, name, object type,
      storey, materials + layer sets (thickness), all Psets, IsExternal/LoadBearing.
      Done when: fixture tests assert counts and fields; large file processes without memory blow-up.
      ✅ 2026-10-13 — verified via pytest (29/29) AND live against the real stack (both
      fixtures, through the actual upload → worker → DB pipeline, not just unit tests).
      No geometry is touched, so memory use should scale fine, but this is **not proven
      at scale** — biggest fixture tested is 92KB/13 elements, nowhere near the 100MB
      target. Revisit once a large real file is available. Also surfaced and fixed a
      process-hygiene issue unrelated to the extraction code itself (stray `rq worker`
      processes accumulating across the session) — see commit `b40f795`.
- [x] **2.3 Quantities from Qto** — read standard Qto sets; normalise to SI; source = qto.
      Done when: wall/slab/footing quantities match expected fixture values.
      ✅ 2026-10-13 — exact match on synthetic fixture (wall: length 5.0m, area_net
      15.0m², volume_net 3.0m³; slab: area_net 40.0m², area_gross 42.0m², volume_net
      10.0m³; footing: volume_net 2.5m³, volume_gross 2.8m³), plausible real values on
      the public real_sample.ifc. SI conversion looks up LENGTHUNIT/AREAUNIT/VOLUMEUNIT
      scales independently (not derived from length² / length³) — real_sample.ifc
      declares millimetre length but plain metre-based area/volume, which would have
      silently produced wrong values otherwise. Verified via pytest (35/35) and live
      through the real upload → worker → DB pipeline for both fixtures.
- [x] **2.4 Geometry fallback** — ifcopenshell.geom for area/volume/length when Qto missing;
      opening deductions for walls; per-layer quantities for composites; source = geometry.
      Done when: fallback results within ±3% of Qto on elements that have both.
      ✅ 2026-10-13 — 0.00% deviation on all 7 real walls/slabs tested (real_sample.ifc,
      both Qto and geometry present), exact match on 2 purpose-built synthetic cases.
      Openings deducted correctly (verified exactly against a hand-built wall+door:
      3.0m³ gross → 2.58m³ net, matching the opening's own 0.42m³ volume exactly) via
      ifcopenshell's own boolean-subtraction behavior, not manual face analysis.
      **Per-layer composite quantities not implemented** — asked first rather than
      guessed: the `quantities` table has no concept of a material layer, extending it
      wasn't scoped here, deferred to Phase 6.2 where the plan actually uses it. Only
      applies when Qto is completely absent for an element — never overrides real Qto
      data (verified live). Verified via pytest (41/41) and live through the real
      pipeline. ruff/black clean.
- [x] **2.5 Element profiles + grouping** — `profile_text` per element; group hash for identical types.
      Done when: profiles deterministic (snapshot tests); grouping reduces element count in report.
      ✅ 2026-10-13 — exact-string snapshot test on the fixture wall, plus an explicit
      twice-called-same-input determinism check. Grouping verified on real data: 4
      walls in real_sample.ifc → 2 unique group hashes (3 share material/class/type, 1
      doesn't), confirmed via pytest and live through the real pipeline. Found a real
      bug while building this: `ifcopenshell.util.element.get_psets()` always injects
      an `"id"` key into every pset dict (the pset's own STEP id) — without excluding
      it, profile_text would show `Properties: id=24` as if it were a real IFC
      property. 49/49 pytest, ruff/black clean.
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
