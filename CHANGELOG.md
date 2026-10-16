# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — Initial repository preparation

First version prepared for version control and future hosted deployment. This entry
documents the state of the application as of that preparation, not a single development
session — the features below were built incrementally and each has been exercised against
a real running local stack (Docker Compose Postgres/Redis/Garage/Ollama), not just unit
tests, unless noted otherwise under Known limitations.

### Added

- **IFC extraction pipeline** — IfcOpenShell-based extraction of walls, floors,
  foundations, roofs, and their materials/layers; quantities from Qto property sets where
  present, computed from geometry otherwise; conversion to That Open "fragments" for the
  3D viewer.
- **Classification pipeline** — rule matching → pgvector-backed code-list shortlist and
  example-memory retrieval → an Ollama-served LLM (`qwen2.5:7b-instruct`) and/or the
  client's own "jev" tool → a calibrated confidence score deciding auto-accept vs.
  needs-review.
- **Code list management** — CSV import with embeddings, browse, and semantic search.
- **Rule management** — admin CRUD for classification rules, plus automatic rule
  suggestion from repeated correction patterns.
- **Review workflow** — approve/correct a single element or a whole element group in one
  action, with undo; every review is stored append-only, never overwriting prior rows.
- **Composite element splitting** — split a multi-material-layer element (e.g. a wall)
  into separate line items with proportionally split quantities.
- **Example memory** — corrections are embedded and retrieved as examples for future
  similar elements.
- **Project review UI** — a virtualized, filterable, groupable element table with keyboard
  navigation, synced to a 3D viewer (That Open Engine): selecting an element in either one
  opens/highlights it in the other. The 3D viewer includes fit-to-model, zoom, wireframe
  toggle, storey/IFC-class visibility filters, a measurement tool, and section clipping.
- **Export** — CSV and Excel export of reviewed quantities/codes (a general layout, not
  yet the client's specific IBIS import template).
- **File processing recovery** — a "Process file" / "Retry processing" action for any
  upload whose background job never completed, with live progress once retried.
- **Auth** — email/password with argon2 hashing, JWT in an httpOnly cookie, `admin`/
  `estimator`/`viewer` roles, and a guarded local-dev-only bypass.
- **Docker images** for the API, worker, and frontend, verified against a real running
  Compose stack; CI builds all three on every push/PR.

### Changed

- API Dockerfile now reads the listening port from `$PORT` at container start (falling
  back to 8000), instead of a port hardcoded into the image — required for deployment to
  a platform like Render that assigns its own port at runtime.
- Frontend Dockerfile's `NEXT_PUBLIC_API_URL` is now a declared build argument rather than
  only a local-dev default, since Next.js inlines `NEXT_PUBLIC_*` values at build time.

### Fixed

- The 3D viewer's "Fit to model" control (and the automatic fit on first load) previously
  called into an API with an empty, never-populated mesh set and silently did nothing —
  the model always rendered as a near-invisible speck in a corner. Fixed to use the
  correct "fit to everything currently loaded" call.
- The 3D viewer's clipping control toggled an internal flag but never actually created a
  cutting plane — no double-click handler had ever been wired up to do so.
- A file whose background processing job was lost (e.g. an infrastructure restart) could
  get stuck showing "Uploaded" forever with no way to recover from the UI; a reprocess
  endpoint and a visible retry action now cover this.
- Several earlier-session fixes to frontend data staleness, accessibility semantics
  (ARIA grid roles on the element table), and a few Select components showing raw
  internal sentinel values instead of human-readable labels.

### Known limitations

- **jev integration is a stub.** No API documentation or credentials for the client's own
  classification tool have arrived yet; the real adapter deliberately raises rather than
  guessing at an undocumented contract.
- **No real client ground truth.** Accuracy and calibration tooling exists
  (`apps/api/scripts/evaluate.py`, `calibrate.py`, `compare_accuracy.py`) but has only
  ever been run against synthetic fixtures — none of its output is a validated real-world
  accuracy claim, and none should be presented as one until real reference data arrives.
- **Click-to-select/measure/clip in the 3D viewer is unverified in headless/CI-style
  environments** specifically — it depends on GPU raycasting that a software-rendered
  browser can't reliably exercise. The underlying API calls are verified correct against
  library source; real-browser, real-GPU behavior has been confirmed for the parts that
  don't depend on raycasting (fit, zoom, wireframe, filters) but not yet for the rest.
- **No hosted/staging environment has existed yet.** Every "verified live" claim in this
  project's history is against a local Docker Compose stack, not a deployed environment —
  see README's "Deploying on Render" section for what a first real deployment still needs
  (external S3-compatible storage, a reachable Ollama/LLM endpoint, pgvector enabled on
  the managed Postgres instance).
- **Auth bypass for local dev** (`AUTH_DISABLED`) exists in the codebase, guarded to
  refuse startup outside `ENVIRONMENT=development`.
