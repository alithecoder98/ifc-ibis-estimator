"""Structured (JSON) logging setup.

Every log line is a single JSON object — easy to ship to any log aggregator later and
easy to grep locally. Call `configure_logging()` once at startup (see app/main.py).

No client data (IFC contents, LLM prompts/responses) should ever be logged — keep log
statements to identifiers, counts and timings. Revisit this note at Phase 8.3 (security
pass).
"""

import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Allow callers to attach structured fields: logger.info("x", extra={"project_id": 1})
        reserved = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys() | {
            "message",
            "asctime",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet the noisy libraries down to warnings; our own app logs stay at `level`.
    for noisy in ("uvicorn.access", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
