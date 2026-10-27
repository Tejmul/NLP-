from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from ... import __version__
from ...db.repository import TicketRepository
from ...db.session import get_engine
from ...ml.registry import ModelRegistry
from ..deps import get_db, get_router, require_api_key

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness: the process is up")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/ready", summary="Readiness: model loaded and database reachable")
def ready(request: Request):
    checks = {"model": getattr(request.app.state, "router", None) is not None}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    ok = all(checks.values())
    body = {"status": "ready" if ok else "not_ready", "checks": checks,
            "model_version": request.app.state.router.model_version if checks["model"] else None}
    if not ok:
        raise HTTPException(503, body)
    return body


@router.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/model", tags=["model"], summary="Production model card")
def model_card(router_=Depends(get_router)):
    return router_.predictor.card


@router.get("/api/v1/model/versions", tags=["model"])
def model_versions():
    return {"versions": ModelRegistry().versions()}


@router.get("/api/v1/model/figures/{name}", tags=["model"], include_in_schema=False)
def model_figure(name: str, router_=Depends(get_router)):
    if "/" in name or not name.endswith(".png"):
        raise HTTPException(404)
    path = ModelRegistry().path(router_.model_version) / "figures" / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@router.post("/api/v1/admin/reload-model", tags=["admin"], dependencies=[Depends(require_api_key)],
             summary="Hot-swap to the current production model and reload routing rules")
def reload_model(request: Request):
    from ..app import build_router
    old = getattr(request.app.state, "router", None)
    request.app.state.router = build_router()
    return {"previous": old.model_version if old else None, "current": request.app.state.router.model_version}


@router.get("/api/v1/analytics/summary", tags=["analytics"], dependencies=[Depends(require_api_key)])
def analytics(days: int = 14, db=Depends(get_db)):
    days = max(1, min(days, 90))
    return TicketRepository(db).analytics(days)
