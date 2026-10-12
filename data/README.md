# /data — client-provided reference files

**Currently empty.** This folder is where client-provided files land for development and QA.
Check before committing anything here — if files contain real client/project data, they
likely shouldn't go into git at all; use `.gitignore` and keep them local, or point to an
external storage location instead and document that here.

## Expected files (none received yet)

| File | Used by | Purpose |
|---|---|---|
| 2-3 sample IFC models (varying size/complexity) | Phase 1.1–1.4 | Extraction pipeline dev + QA |
| Client's internal standard element list | Phase 2.1 | Classification target reference data |
| Client's IBIS cost code list | Phase 2.1 | Classification target reference data |
| Manually-produced Excel/IBIS export for each sample IFC | Phase 1.4, 2.7, 5.2 | Ground truth for extraction accuracy, classification accuracy, and export format |
| 10-20 worked examples (element → correct element/IBIS code) across element types, incl. composites with missing quantities | Phase 2 QA, docs/PROMPTS.md | Prompt development and confidence calibration |
| jev API docs/credentials + a few sample outputs | Phase 2.5 | jev integration |
| Target IBIS import file format spec (column layout) | Phase 5.1 | Export format |

See [docs/IMPLEMENTATION_PLAN.md](../docs/IMPLEMENTATION_PLAN.md) "Open questions" for the
full list of what's still needed before Phase 0/1 can start in earnest.
