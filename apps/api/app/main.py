"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router

configure_logging()

app = FastAPI(title="IFC-to-IBIS Estimator API")

register_error_handlers(app)
app.include_router(health_router)
app.include_router(jobs_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ifc-ibis-api", "status": "ok"}
