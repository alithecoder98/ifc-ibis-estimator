"""Phase 3.6 CLI: picks the lowest auto-accept threshold where precision clears a
target (95% by default) against ground truth, and prints the resulting auto-accept
rate.

Usage:
    uv run python scripts/calibrate.py <project_id> <ground_truth.csv> [target_precision]

Ground-truth CSV format is app/ai/accuracy.py's minimal 2-column shape
(global_id,expected_ibis_code - see scripts/example_ground_truth.csv). Not yet run
against real data - njderidder's manually-verified reference calculations haven't
arrived, same blocker as P.4/2.7. Point this at them the moment they do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.accuracy import load_ground_truth  # noqa: E402
from app.ai.calibrate import gather_scored_rows, pick_threshold  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(
            f"usage: {sys.argv[0]} <project_id> <ground_truth.csv> [target_precision]"
        )
        raise SystemExit(1)

    project_id = int(sys.argv[1])
    ground_truth = load_ground_truth(Path(sys.argv[2]))
    target_precision = float(sys.argv[3]) if len(sys.argv) == 4 else 0.95

    db = SessionLocal()
    try:
        scored_rows = gather_scored_rows(db, project_id, ground_truth)
    finally:
        db.close()

    result = pick_threshold(scored_rows, target_precision)

    print(f"compared: {len(scored_rows)} classification(s) with ground truth")
    if result["achieved"]:
        print(f"threshold: {result['threshold']:.2f}")
        print(f"precision at that threshold: {result['precision']:.1%}")
        print(f"auto-accept rate: {result['auto_accept_rate']:.1%}")
    else:
        print(
            f"no threshold reaches {target_precision:.0%} precision on this data - "
            "nothing would be safely auto-accepted"
        )


if __name__ == "__main__":
    main()
