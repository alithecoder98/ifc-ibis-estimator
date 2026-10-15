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

- [x] **P.1 jev client** — `app/ai/jev.py`: a `JevClient` wrapping jev's real API
      (same stubbed-until-credentials-exist pattern as other provider clients in this
      codebase). Given one element's `profile_text`, returns a suggested IBIS
      code + confidence/flag. Buildable now as a stub even without real jev access.
      Done when: unit-testable against a stub/fake response; ready to swap in real
      credentials with no code change once they arrive.
      ✅ 2026-10-13 — `get_jev_client()` picks `StubJevClient` (confidence=0.0,
      `is_stub=True`) or the real `JevClient` based on whether `JEV_API_URL`/
      `JEV_API_KEY` are set. The real client deliberately raises `NotImplementedError`
      rather than guessing at an API contract we don't have docs for.
- [x] **P.2 Classification step** — worker step after profiling (2.5): calls jev
      **once per unique `group_hash`**, not per element — reuses 2.5's grouping
      specifically to cut jev API calls/cost, which matters since njderidder is
      paying for API usage out of pocket. Stores the result (reuse the existing
      `classifications` table, `source="jev"`).
      Done when: runs end-to-end against a stubbed jev response on both test
      fixtures; real jev swap-in requires no code change, only credentials.
      ✅ 2026-10-13 — verified via pytest (jev called once for 2 of 3 elements sharing
      a group) and live: real_sample.ifc's 13 elements → 13 Classification rows via
      exactly as many jev calls as unique `group_hash`es, not 13 individual calls.
- [x] **P.3 Minimal results output** — the simplest thing that shows classifications
      and flags uncertain matches. Default toward a script exporting to Excel/CSV
      (no frontend work, directly shareable) over a web page, unless a quick glance
      in the browser is specifically wanted — decide concretely when building this,
      not before.
      Done when: njderidder can open the output and see element → suggested code →
      confidence/flag, without needing to run any code himself.
      ✅ 2026-10-13 — `GET /projects/{id}/export` downloads a CSV (chosen over Excel/a
      frontend page — zero new dependencies, zero new pages, both of which would eat
      disproportionately into the 1-2 day budget). Verified live: a real upload
      produced a real downloadable CSV with real quantities and an honest "jev not yet
      configured" reasoning column per row, not fabricated data.
- [x] **P.4 Accuracy comparison** — script comparing jev's suggested codes against the
      manually-verified reference calculations, once provided. Scoped down from
      2.7/3.8's full evaluation harness — just a % match and a list of mismatches,
      not cost tracking or per-family breakdowns.
      Done when: produces one number (accuracy %) + a mismatch list from real data.
      ✅ 2026-10-13 — `app/ai/accuracy.py` (`compare_accuracy()` + `load_ground_truth()`,
      pure functions over the DB, same pattern as `app/ai/export.py`) and the thin CLI
      `scripts/compare_accuracy.py` (`uv run python scripts/compare_accuracy.py
      <project_id> <ground_truth.csv>`), plus `scripts/example_ground_truth.csv` as a
      format template. Ground-truth CSV is a minimal 2-column `global_id,
      expected_ibis_code`. **Self-tested only** — njderidder's real reference
      calculations still haven't arrived, so `tests/test_accuracy.py` proves the
      comparison/mismatch logic is correct against our own fixture (jev's stub always
      returns `None`, so the test crafts a ground truth by hand to get one controlled
      match + one controlled mismatch) — this is not a real accuracy number. Verified
      live too: a real upload's real classifications ran through the real CLI against
      a hand-built ground-truth CSV and reported correct counts/mismatches.

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
- [x] **2.6 Fragments for viewer** — convert IFC to That Open fragments in worker (Node script or
      service), store file, map fragment IDs ↔ GlobalIds.
      Done when: fragments file downloadable via `GET /files/{id}/model`.
      ✅ 2026-10-13 — Node subprocess invoked from the existing Python worker job
      (`apps/api/node_fragments/convert.mjs`, called by `app/ifc/fragments.py`), not a
      standalone service or browser-side conversion: the fragments file needs to exist
      as a stored artifact independent of any viewer (Phase 5 doesn't exist yet), and a
      subprocess call matches how `ifcopenshell.geom` is already only invoked when
      needed. Verified the real `@thatopen/fragments` v3.4.8 API by installing it in a
      scratch dir and reading its `.d.ts` before writing any code — `IfcImporter.process()`
      for conversion, `SingleThreadedFragmentsModel` + `getGuidsByLocalIds()` for the
      id map — then ran it for real against both fixtures before trusting it. Route is
      `GET /projects/{project_id}/files/{file_id}/model` (nested, matching the existing
      upload route), not the plan's flat `/files/{id}/model`. New migration
      `8c104e54e6a7` adds `ifc_files.fragments_storage_key` +
      `ifc_files.fragment_id_map` (GlobalId → fragment local ID, inverse of what the
      Node script produces — lookups always start from an element's GlobalId). New
      dependency: Node.js in `Dockerfile.worker` only (the API image just enqueues the
      job, never runs it) + `actions/setup-node` in CI's `api` job.
- [x] **2.7 Extraction report** — `scripts/compare_extraction.py` vs ground truth: element coverage,
      quantity deviation per code.
      Done when: report generated for all reference projects.
      ✅ 2026-10-13 — `app/ifc/extraction_report.py` (`GroundTruthRow` Pydantic model +
      `load_ground_truth()` + `compare_extraction()` + `render_markdown_report()`) and
      the thin CLI `scripts/compare_extraction.py`. Ground-truth CSV format follows
      PROMPTS.md's 0.3 spec (`file, global_id, expected_ibis_code,
      expected_internal_element, expected_quantity, unit, notes`) — 0.3's own loader
      was never built (Phase 0 blocked on client data), so this ships its own minimal
      validated loader rather than wait on a separate phase. For a missing element,
      the ground-truth format has no `ifc_class` column, so missing-by-class comes from
      opening the raw IFC by GlobalId, not a guess. **Self-tested only** — same caveat
      as P.4: njderidder's real reference calculations still haven't arrived, so
      `tests/test_extraction_report.py` proves the coverage/missing/deviation logic
      against our own fixture (one matched element, one missing-but-present-in-IFC,
      one missing-and-not-in-IFC, one real quantity deviation), not a real coverage
      number. A live run against a real uploaded project caught a real bug before
      merge: `csv.DictReader` gives `""` for empty cells, which Pydantic's `float |
      None` fields don't coerce to `None` — fixed by normalising empty strings in
      `load_ground_truth()`. 72/72 pytest, run twice, no leaks.

## Phase 3 — AI classification engine (weeks 4–6)
- [x] **3.1 Code list import API + embeddings** — admin upload of codes (CSV/XLSX), versioning,
      `Embedder` interface, embeddings stored in pgvector, family tags.
      Done when: similarity search returns sensible codes for 10 sample queries (test).
      ✅ 2026-10-13 — **AI provider decided: local/open-source models via Ollama**, not a
      paid API (see CLAUDE.md decision log) — bge-m3 for embeddings, qwen2.5:7b-instruct
      for the LLM classifier (3.4). `docker-compose.yml` gets a new `ollama` service with
      GPU passthrough (confirmed working on the dev machine's RTX 2060 Super, 100% GPU
      offload, ~62 tok/s once warm). `EMBEDDING_DIM` changed 1536→1024 (bge-m3's real
      size; the 1536 was always an OpenAI-shaped placeholder, no real embeddings existed
      yet) via migration `9d1ddcb204f4`. `app/ai/embedder.py` (`OllamaEmbedder` +
      `FakeEmbedder` — the plan's own instruction: "tests with a fake embedder"),
      `app/ai/codes.py` (import/search logic), `app/routers/codes.py`
      (`POST /codes/import`, `GET /codes`, `GET /codes/search`, all admin-gated except
      list/search which estimators/viewers can also use). Verified live against the
      real running Ollama, not just FakeEmbedder: real bge-m3 embeddings stored in
      pgvector, a real cosine-distance search correctly ranked a matching code above an
      unrelated one, and a real qwen2.5 chat completion answered correctly.
      **Found and fixed during this session, not this sub-phase's fault:** the dev
      machine's C: drive filled to 0.29GB free mid-pull (Docker's WSL2 virtual disk
      doesn't shrink on its own after internal cleanup) — fixed by compacting the vhdx
      via diskpart (see CLAUDE.md "Known Windows/environment quirks"). The forced
      Docker Desktop/WSL restart that followed left Postgres/Garage's port-forwarding
      stale (containers reported healthy, but connections failed) until each was
      individually `docker compose restart`ed - also now documented in CLAUDE.md.
      81/81 pytest, run twice, no leaks.
- [x] **3.2 Rule engine** — JSON rule conditions (class, type, material, thickness range, flags) →
      code; rules evaluated first; confidence 1.0, source = rule; admin CRUD API.
      Done when: unit tests cover match/no-match/priority.
      ✅ 2026-10-13 — `app/ai/rules.py` (condition fields: `ifc_class`,
      `predefined_type`, `material_keyword`, `thickness_mm` (range), `is_external`,
      `load_bearing`, `storey_keyword`; `match_rule()` picks the highest-`priority`
      match). Evaluated **per element, not per `group_hash`** like jev —
      `group_hash` excludes `storey`, so a storey-based rule can still split a jev
      group; wired into `app/ai/classify.py` as the first step, so a matched element
      never calls jev at all. Admin CRUD at `app/routers/rules.py`
      (`POST/GET/PATCH/DELETE /rules`). `scripts/load_initial_rules.py` +
      `scripts/example_rules_initial.json` for the plan's "load from
      `data/rules_initial.json`" — self-tested only, no real client rules yet.
      Verified live against a real upload: added a rule matching
      `real_sample.ifc`'s actual `stone_sand-lime` wall material (not the fixture's
      literal "concrete" — real data, real messiness), confirmed 3 matching walls
      got `source="rule", confidence=1.0, auto_accepted` and skipped jev entirely,
      while a 4th wall with different material and everything else correctly fell
      through to jev. 94/94 pytest, run twice, no leaks.
- [x] **3.3 Retrieval** — shortlist top-15 codes within family; example memory top-5 similar approved
      elements; caching per group hash.
      Done when: tests with seeded examples return expected neighbours.
      ✅ 2026-10-13 — `app/ai/retrieval.py`: `guess_family()` maps each supported
      `ifc_class` to a `code_list` family (`IfcSlab` disambiguated via
      `predefined_type == "ROOF"`), `shortlist_codes()` (family-filtered, falls back
      to all families when fewer than the requested limit come back),
      `similar_examples()` (top-5 from `example_memory`), and
      `shortlist_and_examples()` wrapping both behind an in-process cache keyed by
      `group_hash` — the same "one lookup per group" reasoning `classify.py` already
      applies to jev, since `group_hash` is deterministic per group but the raw
      `profile_text` isn't (quantities vary per element). **Not wired into
      `classify.py` yet** — its output (candidates + examples) has no consumer until
      3.4's LLM prompt exists. Found and fixed while writing the live-verification
      script, not the library itself: `example_memory.project_id` is `NOT NULL` with
      an FK to `projects`, which `tests/conftest.py`'s shared
      `cleanup_project_cascade()` never deleted — the exact bug class CLAUDE.md
      already warns about for any new FK onto `projects`/`elements`, now fixed in
      that one shared function. Verified live against real Ollama/pgvector, not just
      `FakeEmbedder`: real shortlist, real fallback-to-all-families, real
      similar-example ranking, real cache hit. 100/100 pytest, run twice, no leaks.
- [x] **3.4 LLM classifier** — `LLMClient` interface + provider implementation; prompt template
      (profile + candidates + examples + rules summary); strict JSON schema
      {code, internal_element, reasoning, self_score, flags}; Pydantic validation; retries; batching
      per group; token/cost logging.
      Done when: mocked-provider tests pass; live run on 50 elements succeeds and logs cost.
      ✅ 2026-10-13 — `app/ai/llm.py`: `OllamaLLMClient` (qwen2.5:7b-instruct, the
      3.1-decided provider) uses Ollama 0.40.3's real JSON-schema-constrained
      output (`format: <schema>`, not just `format: "json"` — confirmed by hitting
      the live API before writing any code), with `minimum`/`maximum` on
      `self_score` in the schema itself so the model stays in range at generation
      time rather than only at validation time. Prompt lives in the versioned
      `app/ai/prompts/classify_v1.txt` (profile + 3.3's candidates/examples +
      `docs/estimating_rules.md`, itself a placeholder — client's real estimating
      guidance hasn't arrived, same blocked status as the code list/rules/ground
      truth). `classify_with_llm()` validates via Pydantic, retries up to
      `MAX_ATTEMPTS=3` total on bad JSON / out-of-range `self_score` / an
      `ibis_code` not in the candidate set or `"NONE"`, and fails safe (flags
      `["llm_failed"]`, `self_score=0.0`) rather than raising, matching
      `StubJevClient`'s philosophy. One call per `group_hash`, batched like
      jev/rules/retrieval. **Not wired into `classify.py` yet** — combining this
      signal with rules/jev is 3.6/3.7's job. Tested with a mocked client per the
      plan's own instruction (10 tests: retry-on-bad-JSON, retry-on-invalid-code,
      retry-on-out-of-range-score, `"NONE"` handling, retries-exhausted fail-safe).
      `scripts/run_llm_classification.py` is the plan's manual script — **run for
      real** against a live project (real codes imported, real `real_sample.ifc`
      upload, real qwen2.5 inference): correctly matched sand-lime walls and the
      concrete floor slab to their real codes, correctly refused to force a match
      for the roof slab when no candidate fit, correctly flagged every proxy
      element per `estimating_rules.md`'s own placeholder guidance. 13 elements
      (the fixture's full count — fewer than the plan's "50," noted honestly rather
      than padded), 7367 prompt + 1043 completion tokens, $0.00 cost (logged, not
      estimated — local model). 110/110 pytest, run twice, no leaks.
- [x] **3.5 jev adapter** — `JevClient` (or stub if no access yet); run in parallel with LLM;
      store agreement; per-project engine setting (llm | jev | both).
      Done when: adapter tested with recorded responses or stub.
      ✅ 2026-10-13 — `projects.classification_engine` (migration `b4df4b2fc6f1`,
      **defaults to `"jev"`, not `"llm"`**: defaulting to `"llm"` would make every
      worker-integration test - and CI - call the real multi-GB local Ollama model
      instead of the fast deterministic stub, a real regression risk rather than a
      style choice) + `classifications.agreement` (nullable boolean, set only on
      llm/jev rows from a `"both"` run). `PATCH /projects/{id}` (admin-only) changes
      it after creation. `app/ai/classify.py` extended: after rule-matching, reads
      the project's engine, calls jev and/or the LLM (via 3.3's retrieval + 3.4's
      `classify_with_llm`) per group, and on `"both"` writes **two** rows per
      element (`source="llm"` and `source="jev"`) with `agreement` set to whether
      their `ibis_code`s matched (both `None` counts as agreement - "no good match"
      is itself a signal the two engines can agree on). Tested with the jev stub
      throughout (real jev still blocked on API docs/access). **Verified live**
      with engine `"both"`: every element correctly got two rows, `agreement` was
      `True` exactly when the LLM also returned no match and `False` whenever the
      LLM found a real code against the stub's unconditional `None`. 116/116
      pytest, run twice, no leaks. **The stray-worker process-hygiene bug bit
      again, mid-sub-phase** - multiple old `rq worker` processes had survived
      across earlier live tests this session; one of them raced the freshly
      restarted worker for the job and silently processed it with pre-3.5 code,
      making the first live-verification attempt look like the engine dispatch
      hadn't taken effect at all. Fixed by killing every PID matching `rq worker`
      (not just the one most recently started) and confirming zero remain before
      trusting any live result - see the strengthened note in CLAUDE.md.
- [x] **3.6 Confidence + routing** — combine self_score, rule/LLM/jev agreement, shortlist distance,
      data completeness; hard flags (proxy, missing quantity, composite, unknown material);
      thresholds configurable; status = auto_accepted | needs_review.
      Done when: calibration script picks threshold so auto-accepted precision ≥ 95% on ground truth.
      ✅ 2026-10-13 — `app/ai/confidence.py`: `compute_confidence()` weights self_score
      (0.5), agreement (0.2), shortlist rank (0.15, a cheap proxy for "distance" -
      real cosine values aren't threaded through, candidate position is), and data
      completeness (0.15) into `confidence` (`self_score` keeps the raw per-engine
      value unchanged - the schema already had both columns, clearly meant for
      exactly this split). Hard flags force `needs_review` regardless of score.
      Weights are a reasoned placeholder; **only the threshold is calibrated**
      (`settings.auto_accept_threshold`, `scripts/calibrate.py` + `app/ai/calibrate.py`,
      reusing P.4's ground-truth loader, self-tested only - same client-data blocker
      as P.4/2.7). Wired directly into `app/ai/classify.py` (unlike 3.3/3.4, which
      stayed standalone until a consumer existed) since this *is* the consumer.
      Retrieval only runs when the engine uses the LLM, same CI-safety reasoning as
      3.5 - jev-only stays fully offline. 146/146 pytest, run twice, no leaks.
      **Two real bugs caught live, neither by any test:**
      (1) `app/ai/retrieval.py`'s Phase 3.3 cache was a module-level dict keyed by
      `group_hash`, which is purely content-based - a second upload of a
      similar-enough IFC file in the same long-lived worker process reused a
      previous job's `CodeList` objects, bound to that job's already-closed DB
      session (`DetachedInstanceError`). Fixed by making the cache **caller-scoped**:
      `shortlist_and_examples()` now takes a `cache` dict the caller owns, and
      `classify_elements()` creates a fresh `{}` per call rather than ever sharing
      one across jobs. (2) The real LLM independently reports flags like
      `proxy_element` (it has the same vocabulary suggested in
      `docs/estimating_rules.md`) that `hard_flags()` also adds for the same
      element - stored rows showed the same flag twice until `_merge_flags()`
      deduped them. **A third, process-hygiene bug compounded diagnosing both:**
      the kill command used throughout this session (`CommandLine -match 'rq
      worker'`) never matched the actual child-process command-line shape
      (`"rq.exe" worker ...`, quote-then-space, not the contiguous text "rq
      worker") - so every earlier "kill and verify zero" in this session was
      silently incomplete, and stray workers from 3.1 onward had been piling up
      the whole time. Fixed by matching `'rq\.exe|rq worker|uvicorn'` and actually
      confirming zero before trusting any live result - this is now the
      standing rule in CLAUDE.md, not just a note for next time.
- [x] **3.7 Classification job** — worker step after extraction; progress reporting; re-run endpoint.
      Done when: upload → extraction → classification runs end to end on a fixture.
      ✅ 2026-10-13 — The "worker step after extraction" and "end to end on a
      fixture" halves were already true since Phase P.2 (`classify_elements` has
      always been `process_ifc_file`'s last real step); this sub-phase added the
      genuinely new parts. `app/ai/classify.py`: `classify_elements()` now commits
      after each rule-matched element and each AI-engine group (was one
      transaction for the whole call) and takes `progress_callback` (invoked after
      each commit) and `force: bool = False` (skips elements that already have a
      `Classification` row). Together these make a crash lose at most the one
      batch in flight - true resumability, not just a retry that redoes
      everything. `app/workers/extraction.py` maps that progress onto its existing
      80→90% range. `app/workers/classification.py` (new): `reclassify_ifc_file()`
      calls `classify_elements(..., force=True, ...)` - the explicit point of a
      user-triggered re-run (e.g. after adding rules/codes) is to re-evaluate
      everything, not skip what's already classified; "latest classification
      wins" is already the project's convention (`app/ai/calibrate.py`'s
      `gather_scored_rows`), so re-run adds fresher rows rather than deleting old
      ones. `POST /projects/{project_id}/files/{file_id}/classify` (admin/
      estimator; 404 wrong project, 400 not yet extracted) enqueues it. 155/155
      pytest, run twice, no leaks. **Verified live, including the force=True path
      for real**: uploaded a real file (13 elements → 13 classifications), called
      the real endpoint, watched the real job reach `done`/`progress=100`, and
      confirmed the classification count doubled to 26 (every element genuinely
      re-evaluated, not skipped). **A new process-hygiene variant caught live,
      compounding the "wrong kill regex" lesson from 3.6:** a worker left running
      from an *earlier* sub-phase's live verification was still consuming the same
      Redis queue the pytest suite itself uses — it picked up a test's real
      "extract" job and actually ran it, racing the test's own manual DB state
      changes and producing a flaky, confusing failure that had nothing to do
      with the code under test. A dev worker left alive is now understood to be
      a correctness risk for the test suite, not just a staleness risk for manual
      verification - see CLAUDE.md's strengthened process-hygiene note.
- [x] **3.8 Evaluation harness** — `scripts/evaluate.py`: accuracy, auto-accept rate, missed errors,
      cost per model, confusion by family; results saved with timestamp.
      Done when: report produced for all reference projects (input to week-6 gate).
      ✅ 2026-10-13 — **Phase 3 (3.1–3.8) is now fully complete.** New migration
      `10d703fe08b6` adds `classifications.prompt_tokens`/`completion_tokens`
      (nullable, `None` for rule/jev rows — "not applicable" is a different thing
      from "zero cost"), populated in `classify.py`'s llm branch — without this,
      "cost per model" would have been fabricated rather than measured, since
      `classify.py` already computed these values transiently but never
      persisted them. `app/ai/evaluate.py`: `gather_evaluation_rows()` (latest
      classification per element vs. ground truth, family via 3.3's
      `guess_family()`), `evaluate()` → overall accuracy, auto-accept rate,
      auto-accept precision, **unflagged error rate** (wrong *and*
      `auto_accepted` — the dangerous silent case; a wrong `needs_review` already
      got caught by the pipeline, so it isn't "unflagged"), accuracy by family,
      token totals, `cost_usd` (real `$0.00`, local model).
      `total_tokens_for_project()` sums every `source="llm"` row, not just the
      latest-per-element subset — a superseded re-run still cost real tokens.
      `scripts/evaluate.py` reuses P.4's ground-truth loader, writes a timestamped
      `.md` + `.json` to `data/reports/eval/` (git-ignored). Self-tested only (10
      tests) — real evaluation still needs njderidder's ground truth, same
      blocker as P.4/2.7/3.6. **Verified live for real**, not just self-tested:
      uploaded a real file with `engine="llm"`, let the real qwen2.5 classify it,
      ran the real CLI against a hand-built ground truth for the known-correct
      elements — 6 compared, 83.3% overall accuracy, 100% auto-accept precision,
      0% unflagged errors, real token totals (9584 prompt + 1429 completion),
      correct per-family breakdown, real `.md`/`.json` files written to disk with
      valid content. 165/165 pytest, run twice, no leaks.

## Phase 4 — Frontend application (weeks 4–7)
- [x] **4.1 Projects pages** — list (search, status), create/edit form, project detail shell.
      ✅ 2026-10-14 — First frontend sub-phase after Phase 3's backend work; also
      regenerated `schema.d.ts` from the live backend (stale since Phase 1 - only
      had auth/health/jobs-demo, missing every endpoint built across Phases 2-3).
      **Backend additions this sub-phase needed, not pre-existing:**
      `ProjectUpdate.name` + broadened `PATCH /projects/{id}` from admin-only to
      admin/estimator (renaming is a normal estimator action, not the AI-engine-
      config concern 3.5 first scoped this endpoint for - this app has no
      multi-tenant/adversarial model per CLAUDE.md's non-goals, so no per-field
      split was worth building); `GET /projects/{project_id}/files` (list) -
      didn't exist at all, so the frontend had no way to see a project's
      uploaded file(s)/status without it. `project.status` itself is still
      always `"draft"` (nothing in the pipeline ever transitions it - a known
      gap, not fixed here); the Overview tab shows real per-file status via the
      new endpoint instead of fabricating a project-level one.
      Frontend: `src/lib/projects/*` (React Query hooks matching the existing
      auth-hooks convention), `project-dialog.tsx` (shared create/rename form),
      `status-badge.ts`, `export-button.tsx` (a real, working CSV download via
      the already-complete P.4 export endpoint - not a placeholder). `/projects`
      is now a real list with client-side name search; `/projects/[id]` is a
      real detail page with Overview (real metadata + files) wired up, and
      Elements/3D explicitly labeled "coming in a later phase" (4.3-4.5, Phase 5)
      rather than faked. New shadcn components: `badge`, `dialog`, `tabs`.
      168/168 backend pytest (run twice, no leaks), `tsc --noEmit`, `eslint`, and
      a real `pnpm build` all clean. **Verified live, honestly partial**: no
      browser/computer-use tool was available in this environment to click-test
      the actual rendered UI, so every real API call the hooks make (login,
      list/create/get/patch a project, list files, export) was exercised
      directly against the live backend with real auth and confirmed to return
      exactly the shapes the TypeScript types expect; the dev server itself
      runs and serves all routes with no build/type errors. The one thing not
      verified: whether the React rendering/interactivity itself looks and
      behaves correctly in an actual browser - flagged explicitly rather than
      claimed, per CLAUDE.md's own instruction for exactly this situation.
- [x] **4.2 Upload flow** — drag-and-drop, chunked upload, job progress per step, error states.
      ✅ 2026-10-14 — **"Chunked" wasn't built** - the backend is still a single
      server-proxied multipart POST (2.1's deliberate deferral, "revisit if
      large files prove slow"), so what shipped is real upload-progress
      reporting (via `XMLHttpRequest`, not `fetch`/the typed client - neither
      fires upload-progress events), not actual multi-request chunking. Noted
      honestly rather than claimed. **Backend additions this surfaced:**
      `IfcFileOut.job_id` (the upload response and file list had no way to tell
      the frontend which job to poll - a real gap, not pre-existing), and
      `GET /jobs/{id}` finally got a `JobOut` response model **and its first
      auth check ever** (`require_role` - previously anyone, authenticated or
      not, could poll any job). Frontend: `useUploadFile` (XHR for real byte
      progress), `useJob` (polls via `refetchInterval`, stops at `done`/`failed`),
      `jobStepLabel()` (3 honest labels mapped to the *real* progress ranges
      `classify_elements`/`extraction.py` actually produce - not the plan's
      literal "validate/extract/quantities/classify", which the backend doesn't
      track that granularly and this doesn't fabricate). `UploadDropzone` on the
      Overview tab: idle/uploading/processing/done/error states, all four error
      cases covered (wrong extension caught client-side, corrupt IFC content,
      upload failure, job failure) with real messages and a reset. New shadcn:
      `progress`. 170/170 backend pytest (run twice, no leaks), `tsc`/`eslint`/
      real `pnpm build` clean. **Verified live for real** via curl exactly
      mirroring what the hooks do (login → upload → got a real `job_id` →
      polled `/jobs/{id}` → watched it reach `done`/`progress:100` → confirmed
      the file list shows `status: "extracted"`), plus both real error paths
      (wrong extension, corrupt `.ifc` content) - still the same honest
      limitation as 4.1: no browser tool available, so the actual rendered
      drag-and-drop/progress-bar UI was never click-tested. **Reinforced the
      stray-worker lesson once more:** starting a live worker for this
      verification, then forgetting to stop it before the next `pytest` run,
      produced the exact same race as 3.7's - a test's own DB state got
      overwritten mid-test by the worker actually processing its job for real.
      Standing rule, now doubly confirmed: stop the worker *before* every
      pytest run, not just after a restart.
- [x] **4.3 Results overview** — counts (total, auto-accepted, to review, corrected), totals per IBIS
      code, warnings panel.
      ✅ 2026-10-14 — `app/ai/summary.py` + `GET /projects/{project_id}/summary`.
      `corrected` is always `0` today, honestly - no review/correction endpoint
      exists yet (`Review`'s own model docstring says Phase 6.1), so this is a
      mechanism that's real now and will report real counts once 6.1 ships, not
      thin test data. Totals-by-code picks exactly **one** quantity per element
      (net > gross > length > count precedence) to avoid double-counting a
      wall's net+gross area as two separate measures of the same physical
      quantity; warnings reuse 3.6's existing flag vocabulary
      (`missing_quantity`, `proxy_element`) plus `ibis_code IS NULL` for
      "unmapped" rather than inventing new detection logic.
      **A real correctness gap found and fixed while building this:** "latest
      classification per element" (used here and already in
      `calibrate.py`/`evaluate.py`) wasn't tie-broken when two rows share a
      `created_at` - which happens for real whenever `classification_engine`
      is `"both"`, since both rows commit together. Added `id DESC` as a
      deterministic secondary sort to all three call sites.
      **A real bug caught by the new tests, not by inspection:** `Quantity.value`
      is `NUMERIC(14,4)`, so psycopg hands back a real `decimal.Decimal` despite
      the model's `Mapped[float]` hint - summing it into a plain float
      accumulator raised `TypeError` the first time a test actually exercised
      two quantities on one element. Fixed with an explicit `float()` cast.
      **A real test-cleanup gap, the same class CLAUDE.md already warns about:**
      `Review` is used by a test for the first time ever in this codebase, and
      `cleanup_project_cascade()` didn't know about it - cleanup hit a foreign
      key violation and silently left a project/user stuck, which then broke
      an unrelated later test via a duplicated email. Fixed in the one shared
      function, per that same standing rule.
      Frontend: `useProjectSummary`, four stat cards, a warnings panel, and a
      totals-by-code table using a plain shadcn `table` (not TanStack Table -
      that's 4.4's dependency to introduce for the much larger Elements
      table). 177/177 backend pytest (run twice, no leaks), `tsc`/`eslint`/a
      real `pnpm build` all clean. **Verified live for real**: seeded real
      elements/quantities/classifications/a review directly, hit the real
      endpoint with real auth, and every number in the response matched what
      was seeded exactly (including the net-only 65.75m2 total, not
      double-counted). Same honest gap as 4.1/4.2: no browser tool available,
      so the rendered cards/table were never click-tested.
- [x] **4.4 Element table** — virtualised, filters (status, confidence, family, storey), sort, search,
      group by element type, column picker; handles 5,000+ rows smoothly.
      ✅ 2026-10-14 — New endpoint `GET /projects/{project_id}/elements` (one row
      per element, reusing 4.3's `primary_quantity`/`latest_classifications_by_element`
      and 3.3's `guess_family` rather than new logic) returns the **full** list,
      no server-side pagination - at realistic JSON sizes even 5,000+ rows fits
      comfortably in memory, and client-side virtualisation (the plan's own
      first-named solution) is what actually solves the rendering-performance
      problem; server paging stays unbuilt until something real shows it's
      needed. All filtering/sorting/grouping/search happens client-side against
      that one list via `@tanstack/react-table` + `@tanstack/react-virtual`.
      **A real, important version trap found before writing a line of component
      code:** `pnpm add @tanstack/react-table` installs **v9** by default, which
      turned out to be a from-scratch API rewrite - no `useReactTable`, no
      `getCoreRowModel()`, a completely different feature-based architecture
      with no resemblance to the stable, overwhelmingly-more-common v8 API every
      tutorial/example on the internet uses. Caught by `tsc` immediately
      ("no exported member 'useReactTable'"), not by guessing - explicitly pinned
      to `8.21.3` instead, the right call for a client project over building
      against an unfamiliar, undertested rewrite. **Two more real bugs caught by
      `tsc`/`eslint`, not inspection:** sorting the quantity column against its
      display string ("45.5 m2") would have sorted lexicographically instead of
      numerically - fixed by keeping the `accessorFn` numeric and moving the
      unit-suffix formatting into `cell`. `elements ?? []` created a fresh array
      reference every render while the query was still loading, silently
      defeating every downstream `useMemo` - fixed by memoizing that fallback
      itself. 182/182 backend pytest (run twice, no leaks), `tsc`/`eslint`/a
      real `pnpm build` all clean. **Verified live for real**: seeded a
      classified wall and an unclassified roof directly, hit the real endpoint
      with real auth, both rows matched exactly (including all-null fields for
      the unclassified one). Same honest gap as 4.1-4.3: no browser tool
      available, so the actual table/virtualisation/grouping/column-picker
      interactions were never click-tested - this is the sub-phase where that
      gap matters most, given how much of 4.4 *is* interaction.
      **Also this session, at the user's request, unrelated to 4.4's own
      scope:** downloaded all 18 real-world IFC test files from
      [youshengCode/IfcSampleFiles](https://github.com/youshengCode/IfcSampleFiles)
      into `data/sample_ifc_files/` (~176MB, git-ignored per the existing
      `/data/*` rule - these are large public test files, not something to add
      to this repo's history) for manual larger-scale pipeline testing, distinct
      from the small git-tracked fixtures in `apps/api/tests/fixtures/`.
- [x] **4.5 Element detail panel** — properties, layers, quantities with source, AI reasoning,
      candidates with scores, similar examples, review history.
      ✅ 2026-10-14 — New endpoint `GET /projects/{project_id}/elements/{element_id}`
      (`app/ai/element_detail.py`'s `get_element_detail()`), returning properties,
      material layers, quantities with source, the latest classification's AI
      reasoning, candidate codes with real cosine-similarity scores
      (`app/ai/retrieval.py`'s new `shortlist_codes_with_scores()`, kept separate
      from the existing `shortlist_codes()` so `classify_with_llm()`/
      `compute_confidence()` stay untouched), similar past examples, and review
      history/comments (joined across *all* the element's classifications, not
      just the latest). Candidates/examples are recomputed fresh against the
      element's current `profile_text` every call - nothing persists what was
      shown at classification time, a known simplification consistent with the
      rest of the project. This is the one feature that always calls the real
      embedder regardless of the project's `classification_engine` setting
      (unlike `classify.py`'s jev-only "stay offline" path), since it needs to
      show candidates for *any* element on demand - documented in the module
      docstring. Frontend: a `Sheet`-based side panel (shadcn's Base UI
      component, unused since Phase 1) opening on element-table row click,
      `use-element-detail.ts` (disabled until an element is selected, not
      skipped, so the sheet can mount before the first click).
      **Two real bugs found and fixed, both pre-existing, neither introduced by
      this sub-phase's own code:** (1) `detail.element.ifc_file.project_id` is
      not real - this codebase has no ORM `relationship()`s anywhere, only
      explicit FK columns, fixed to a plain `db.get(IfcFile, ...)` query in the
      router; (2) `test_projects.py` had its own separate, long-forgotten copy of
      a `_cleanup_project()` helper (distinct from the shared
      `cleanup_project_cascade()` in `tests/conftest.py`) that never learned
      about the `Element` table - this sub-phase's new endpoint tests were the
      first in that file to create an `Element` directly, hit the exact
      FK-violation class CLAUDE.md already warns about, and surfaced a second,
      independent instance of the duplication the shared helper exists to avoid.
      Fixed by delegating to the shared helper instead of patching the copy.
      189/189 backend pytest (run twice, no leaks), `tsc --noEmit`/`eslint`/a
      real `pnpm build` all clean. **Verified live for real**: uploaded
      `real_sample.ifc` through the real pipeline (extract → classify) via a
      disposable test user/project, hit the real endpoint over the real running
      API with a real session cookie - real properties/quantities/materials from
      the real IFC file, a real jev-stub classification with its real
      `reasoning` string, and a real (empty, correctly so - zero `CodeList` rows
      currently exist) candidates/examples result, proving the real-embedder
      call path runs without error even when it finds nothing. All live-test
      rows and the disposable user cleaned up afterward; full suite re-run
      clean. Same honest gap as 4.1-4.4: no browser tool available, so the
      panel's actual open/close/scroll interaction was never click-tested.
- [x] **4.6 Admin area** — code list import + browse, rules (suggested/active), thresholds.
      Scope narrowed 2026-10-14: the originally-planned "users/roles" screen is
      dropped — see CLAUDE.md's decision log entry of that date (RBAC/login out
      of scope for now, disabled via the existing `AUTH_DISABLED` toggle rather
      than deleted, fully reversible).
      ✅ 2026-10-14 — The only genuinely new backend piece: a minimal DB-backed
      `app_settings` key/value table (new migration `9a32c198ebc5`) so the
      confidence threshold is admin-editable *and* takes effect immediately -
      `app/core/settings_store.py`'s `get_/set_auto_accept_threshold()`, falling
      back to the env-sourced `settings.auto_accept_threshold` when no row
      exists yet. `GET/PATCH /settings/threshold` (PATCH admin-only).
      `classify.py` now reads the DB-backed value once per `classify_elements()`
      call (not per element/group) and passes it into `compute_confidence()`,
      so a saved threshold change affects the very next classification run with
      no restart - proven by a dedicated integration test
      (`test_classify_elements_uses_db_threshold_override`) that scores the
      same inputs as an existing 3.5 test (self_score 0.9 → 0.85 final
      confidence, `auto_accepted` at the 0.8 default) and shows raising the
      DB-backed threshold above 0.85 flips the *same* element to
      `needs_review`. Code-list import/browse and rules CRUD needed **no**
      backend changes at all - both already existed from 3.1/3.2; this
      sub-phase only built the frontend on top of them. Frontend: `/admin`
      rebuilt with tabs (Code lists / Rules / Threshold, reusing the shadcn
      `tabs` already in use on `/projects/[id]`) - a code-list upload form +
      family-filtered browse/search table, a rules table with a create/edit
      dialog (a small condition-builder: field/operator/value rows, add/remove,
      covering all 7 condition fields and all 3 operators including `between`'s
      two-number range) plus activate/suggest toggle and delete, and a
      threshold form. New hooks under `src/lib/admin/`. Codes import uses plain
      `fetch` + `FormData`, not the typed `apiClient`, for the same reason
      `use-upload-file.ts` does (the generated body type for a multipart
      `UploadFile` field is `{file: string}`, not `FormData`) - no
      upload-progress UI needed here, unlike that one, since this is an admin
      action rather than a user-facing progress bar. 7 new backend tests,
      196/196 backend pytest total (run twice, no leaks), `tsc`/`eslint`/a real
      `pnpm build` all clean. **Verified live for real** against the actual
      running API (not mocked): real threshold GET/PATCH/range-validation, a
      real CSV import computing real Ollama embeddings and landing in a real
      family-filtered browse and a real semantic search (correctly ranked a
      concrete-foundation code first for a "concrete foundation" query), and a
      full real rules CRUD cycle (create suggested → list by status → activate
      → delete → confirm 404) - all cleaned up afterward. **A real, if unusual,
      process-hygiene variant hit during this verification**: port 8000 turned
      out to hold two ghost TCP listeners (`netstat` showed them LISTENING,
      but `Get-Process`/`Get-CimInstance`/`taskkill` all agreed neither PID
      exists) left over from earlier in this long session - serving stale
      pre-4.6 responses (missing `/settings/threshold` entirely) despite a
      freshly-started, correctly-coded `--reload` server appearing to start up
      cleanly against that same port. Caught only because the regenerated
      OpenAPI schema was missing the new path; worked around by verifying on a
      different port (8001) instead of chasing the ghost listeners further -
      not yet understood *why* Windows left them, so noted as a standing risk
      in CLAUDE.md rather than treated as solved. Same honest gap as 4.1-4.5:
      no browser tool available, so the actual tabs/dialog/condition-builder
      interactions were never click-tested.
- [ ] **4.7 UX polish** — keyboard shortcuts (A approve, C correct, J/K next/prev), empty/loading/error
      states, consistent design.
      Done when (phase): Playwright test covers login → upload → open results → approve one item.
      ⏸️ 2026-10-15 — Everything that doesn't depend on Phase 6.1 is done: `J`/`K`
      keyboard navigation in the element table (moves to the next/previous row
      in whatever order is currently on screen - respecting sort/filter/group -
      and opens that row's detail panel; ignored while typing in a filter field
      or dialog form); a new `Skeleton` component (shadcn, no new npm
      dependency) replacing every plain "Loading..." text across the app with
      a content-shaped placeholder; a new shared `ErrorState` (message + a real
      **Retry** button wired to the query's own `refetch()`) replacing every
      bare error paragraph that previously had no way to recover without a
      full page reload; the one real missing empty state found
      (`element-table.tsx` showed a blank table with no message for zero
      elements or zero filter matches - now distinguishes "No elements yet."
      from "No elements match your filters.", the same pattern the projects
      list already used). No backend changes, no new dependencies besides the
      one new shadcn component. `tsc --noEmit`/`eslint`/Prettier all clean, a
      real `pnpm build` clean, 196/196 backend pytest (sanity check only - no
      backend code changed this sub-phase). **Not done, deliberately:** the
      `A` (approve) / `C` (correct) shortcuts and the "approve one item"
      Playwright E2E test both need Phase 6.1's review API, which doesn't
      exist yet - box stays unchecked until 6.1 ships, then this sub-phase
      finishes in one more small pass. **A real, if mundane, process-hygiene
      variant hit at the very start of this sub-phase, worth remembering
      generally:** this was a fresh session on a new day, and Docker Desktop
      simply wasn't running at all - `pytest` hung silently for over two
      minutes instead of failing fast, because SQLAlchemy was retrying a
      connection to a Postgres that didn't exist yet, not because of anything
      in this sub-phase's own code. Worth checking `docker compose ps` first
      in any fresh session before assuming a hung backend command is a code
      problem. Same honest gap as every prior frontend sub-phase: no browser
      tool available, so `J`/`K` and the new skeleton/empty/retry states were
      confirmed to compile and render without a server error, but never
      visually or interactively click-tested.
      ⏸️ 2026-10-15 — That gap closed for real: a real headless Chromium
      (Playwright, installed into a scratch directory, not a project
      dependency) drove the actual running app for the first time all
      project. Confirmed 4.1-4.6 all render correctly with real data, and
      found + fixed a real, severe, pre-existing (since 4.4, not caused by
      4.7) infinite re-render loop in `ElementTable` - an inline
      `grouped ? ["group_hash"] : []` array passed to `useReactTable`'s
      `state.grouping` with no `onGroupingChange` handler, a fresh reference
      every render that TanStack Table read as "changed" every time,
      triggering an internal reset forever. Confirmed via render counters and
      a CDP CPU profile (3,600+ renders/5s idle, zero network calls),
      confirmed present in a real production build (not a dev/HMR artifact),
      fixed with one `useMemo`. See CLAUDE.md's matching entry for full
      detail, including the CORS/`localhost`-vs-`127.0.0.1` and Base UI
      click-dispatch gotchas hit along the way. `J`/`K` navigation itself now
      confirmed actually working in a real browser, not just compiling.

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
