"""Phase 3.2 CLI: loads initial rules from a JSON file (see example_rules_initial.json
for the format) into the `rules` table.

Usage:
    uv run python scripts/load_initial_rules.py <rules.json>

Not yet run against real client rules - njderidder's internal element/IBIS mapping
knowledge hasn't arrived. Point this at the real file the moment it does.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.rules import load_rules_from_json  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <rules.json>")
        raise SystemExit(1)

    db = SessionLocal()
    try:
        rules = load_rules_from_json(db, Path(sys.argv[1]))
        db.commit()
        print(f"loaded {len(rules)} rule(s)")
        for rule in rules:
            print(f"  #{rule.id}: {rule.result_ibis_code} (priority {rule.priority})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
