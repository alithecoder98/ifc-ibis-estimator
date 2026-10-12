"""Writes the live OpenAPI schema to disk, so the frontend can generate a typed API
client from it without the backend needing to be running at generation time.

Usage (from apps/api):
    uv run python -m app.export_openapi [output_path]

Defaults to ../web/src/lib/api/openapi.json.
"""

import json
import sys
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "api" / "openapi.json"
)


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(app.openapi(), indent=2))
    print(f"Wrote OpenAPI schema to {output_path}")


if __name__ == "__main__":
    main()
