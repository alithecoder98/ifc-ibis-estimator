"""FastAPI application entrypoint.

Kept intentionally minimal for sub-phase 1.1 (monorepo scaffold). Settings,
structured logging, the global error handler and the real /health check
(DB + Redis) are added in sub-phase 1.2 — see docs/IMPLEMENTATION_PLAN.md.
"""

from fastapi import FastAPI

app = FastAPI(title="IFC-to-IBIS Estimator API")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ifc-ibis-api", "status": "ok"}
