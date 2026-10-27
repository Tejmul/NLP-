"""FastAPI application.

    uvicorn bankq.api.app:app --port 8077
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import ROOT, get_settings
from ..db.session import init_db
from ..logging_setup import setup_logging
from ..ml.predictor import Predictor
from ..routing.router import Router
from ..routing.rules import RuleSet
from .observability import RequestContextMiddleware
from .routes import classify, system, tickets

log = logging.getLogger("bankq.api")
WEB_DIR = ROOT / "web"


def build_router() -> Router:
    return Router(Predictor(), RuleSet.from_yaml(get_settings().rules_path))


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.log_level, s.log_json)
    init_db()
    try:
        app.state.router = build_router()
        log.info("model loaded", extra={"model_version": app.state.router.model_version})
    except FileNotFoundError as e:
        app.state.router = None
        log.error("no model available; /ready will report not_ready", extra={"error": str(e)})
    if not s.api_key_set:
        log.warning("API key auth is disabled (BANKQ_API_KEYS is empty). Do not run like this in production.")
    yield


app = FastAPI(
    title="Banking Query Router",
    version=__version__,
    description="Classifies customer banking messages, masks PII, applies business rules, "
                "creates tickets and routes them to the right team.",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.include_router(system.router)
app.include_router(classify.router)
app.include_router(tickets.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Quote the X-Request-ID when reporting."})


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")
