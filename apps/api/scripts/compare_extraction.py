"""Phase 2.7 CLI: compares a project's extracted elements/quantities against a
ground-truth CSV and writes a markdown report.

Usage:
    uv run python scripts/compare_extraction.py <project_id> <ground_truth.csv>

Ground-truth CSV format: file, global_id, expected_ibis_code,
expected_internal_element, expected_quantity, unit, notes (see
app/ifc/extraction_report.py). Writes the report to data/reports/ at the repo root
(git-ignored) unless a third argument gives an explicit output path.

Not yet run against real data - njderidder's manually-verified reference
calculations haven't arrived. Point this at them the moment they do.
"""

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.ifc.extraction_report import (  # noqa: E402
    compare_extraction,
    load_ground_truth,
    render_markdown_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(
            f"usage: {sys.argv[0]} <project_id> <ground_truth.csv> [output.md]",
        )
        raise SystemExit(1)

    project_id = int(sys.argv[1])
    ground_truth = load_ground_truth(Path(sys.argv[2]))

    if len(sys.argv) == 4:
        output_path = Path(sys.argv[3])
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_path = (
            REPO_ROOT / "data" / "reports" / f"{project_id}-extraction-{timestamp}.md"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = compare_extraction(db, project_id, ground_truth, Path(tmp_dir))
    finally:
        db.close()

    markdown = render_markdown_report(report, project_id)
    output_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"written to {output_path}")


if __name__ == "__main__":
    main()
