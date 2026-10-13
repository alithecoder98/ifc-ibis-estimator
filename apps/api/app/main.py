"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.routers.auth import router as auth_router
from app.routers.codes import router as codes_router
from app.routers.health import router as health_router
from app.routers.jobs import router as jobs_router
from app.routers.projects import router as projects_router

configure_logging()

_settings = get_settings()
if _settings.auth_disabled and _settings.environment != "development":
    raise RuntimeError(
        "AUTH_DISABLED=true outside ENVIRONMENT=development — refusing to start. "
        "This bypass is for local dev convenience only and must never run in "
        "staging/production."
    )

app = FastAPI(title="IFC-to-IBIS Estimator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(codes_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ifc-ibis-api", "status": "ok"}
