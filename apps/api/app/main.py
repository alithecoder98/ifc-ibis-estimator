"""FastAPI application entrypoint."""

import logging

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
from app.routers.rules import router as rules_router
from app.routers.settings import router as settings_router

configure_logging()

_settings = get_settings()
# Used to hard-refuse to start outside ENVIRONMENT=development. Deliberately
# relaxed (2026-10-16, explicit decision): every request currently needs to
# work with no login for anyone who has this deployment's URL, including
# wherever it's hosted, not just local dev - see README's "no built-in access
# control" callout for what that actually means. This is a real, intentional
# trade-off for this project's current stage, not an oversight - revisit
# before anything resembling real/sensitive data goes through a deployment
# running this way.
if _settings.auth_disabled and _settings.environment != "development":
    logging.getLogger(__name__).warning(
        "AUTH_DISABLED=true outside ENVIRONMENT=development - every request to "
        "this instance is treated as a fixed admin user, no login required. "
        "Intentional for this project's current stage; not a secure "
        "configuration for anything beyond that."
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
app.include_router(rules_router)
app.include_router(settings_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ifc-ibis-api", "status": "ok"}
