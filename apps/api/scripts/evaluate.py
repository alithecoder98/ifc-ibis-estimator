"""Phase 3.8 CLI: the full evaluation harness - overall accuracy, auto-accept rate,
auto-accept precision, unflagged errors, accuracy per family, token/cost totals.
Saves a timestamped Markdown + JSON report to data/reports/eval/. This is what the
plan's week-6 gate reads.

Usage:
    uv run python scripts/evaluate.py <project_id> <ground_truth.csv>

Ground-truth CSV format (see example_ground_truth.csv):
    global_id,expected_ibis_code

One project per invocation, same as scripts/compare_accuracy.py and
scripts/calibrate.py - for multiple reference projects, run it once per project;
each gets its own timestamped report. Not yet run against real data -
njderidder's manually-verified reference calculations haven't arrived. Point this
at them the moment they do.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.accuracy import load_ground_truth  # noqa: E402
from app.ai.evaluate import (  # noqa: E402
    evaluate,
    gather_evaluation_rows,
    render_markdown,
    total_tokens_for_project,
)
from app.db.session import SessionLocal  # noqa: E402

REPORTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "reports" / "eval"
)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <project_id> <ground_truth.csv>")
        raise SystemExit(1)

    project_id = int(sys.argv[1])
    ground_truth = load_ground_truth(Path(sys.argv[2]))

    db = SessionLocal()
    try:
        rows = gather_evaluation_rows(db, project_id, ground_truth)
        prompt_tokens, completion_tokens = total_tokens_for_project(db, project_id)
    finally:
        db.close()

    report = evaluate(rows, prompt_tokens, completion_tokens)

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    base_name = f"eval_{project_id}_{generated_at}"

    markdown = render_markdown(report, project_id, generated_at)
    (REPORTS_DIR / f"{base_name}.md").write_text(markdown, encoding="utf-8")
    (REPORTS_DIR / f"{base_name}.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "generated_at": generated_at,
                "n_compared": report.n_compared,
                "overall_accuracy": report.overall_accuracy,
                "auto_accept_rate": report.auto_accept_rate,
                "auto_accept_precision": report.auto_accept_precision,
                "unflagged_error_rate": report.unflagged_error_rate,
                "accuracy_by_family": report.accuracy_by_family,
                "total_prompt_tokens": report.total_prompt_tokens,
                "total_completion_tokens": report.total_completion_tokens,
                "cost_usd": report.cost_usd,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(markdown)
    print(f"\nSaved to {REPORTS_DIR / base_name}.md / .json")


if __name__ == "__main__":
    main()
