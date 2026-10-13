"""Phase P.4 CLI: compares a project's jev classifications against a ground-truth CSV.

Usage:
    uv run python scripts/compare_accuracy.py <project_id> <ground_truth.csv>

Ground-truth CSV format (see example_ground_truth.csv):
    global_id,expected_ibis_code

Not yet run against real data - njderidder's manually-verified reference calculations
haven't arrived. Point this at them the moment they do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.accuracy import compare_accuracy, load_ground_truth  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <project_id> <ground_truth.csv>")
        raise SystemExit(1)

    project_id = int(sys.argv[1])
    ground_truth = load_ground_truth(Path(sys.argv[2]))

    db = SessionLocal()
    try:
        report = compare_accuracy(db, project_id, ground_truth)
    finally:
        db.close()

    print(f"compared:  {report['compared']}")
    print(f"correct:   {report['correct']}")
    print(f"accuracy:  {report['accuracy_percent']:.1f}%")

    if report["mismatches"]:
        print(f"\nmismatches ({len(report['mismatches'])}):")
        for m in report["mismatches"]:
            print(
                f"  {m['global_id']} ({m['ifc_class']} {m['name'] or ''}): "
                f"expected {m['expected_ibis_code']!r}, got {m['actual_ibis_code']!r}"
            )

    if report["elements_not_in_ground_truth"]:
        print(
            f"\n{len(report['elements_not_in_ground_truth'])} element(s) in the "
            "project had no matching row in the ground-truth file (skipped)."
        )


if __name__ == "__main__":
    main()
