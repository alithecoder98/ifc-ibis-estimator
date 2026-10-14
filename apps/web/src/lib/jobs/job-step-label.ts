// Mirrors the real progress ranges app/workers/extraction.py and
// app/ai/classify.py actually produce (see CLAUDE.md's Phase 3.7 notes) - not
// the plan's literal "validate/extract/quantities/classify" wording, since the
// backend doesn't track that many discrete steps and this doesn't invent ones
// it can't honestly report.
export function jobStepLabel(progress: number): string {
  if (progress < 80) return "Extracting elements & quantities";
  if (progress < 90) return "Classifying";
  return "Finalizing";
}
