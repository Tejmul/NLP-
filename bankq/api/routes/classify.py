import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...config import get_settings
from ...db.repository import TicketRepository, ticket_to_dict
from ...routing.notify import get_notifier
from ...taxonomy import CATEGORIES, CATEGORY_ORDER, REVIEW_DEPARTMENT
from ..deps import get_db, get_router, rate_limited
from ..observability import record_decision
from ..schemas import BatchRequest, ClassifyRequest, Decision

router = APIRouter(prefix="/api/v1", tags=["classification"])


def _summary(results):
    counts = {c: 0 for c in CATEGORY_ORDER}
    for r in results:
        counts[r["category"]] += 1
    return {"total": len(results), "counts": counts,
            "needs_review": sum(r["needs_review"] for r in results),
            "urgent": sum(r["priority"] == "urgent" for r in results)}


def _route_and_store(texts, channel, create, router_, db):
    results = router_.route_many(texts)
    repo = TicketRepository(db) if create else None
    for r in results:
        record_decision(r)
        r["ticket_ref"] = repo.create(r, channel=channel).ref if repo else None
    if create:
        db.commit()
    return {"results": results, "summary": _summary(results)}


@router.get("/taxonomy")
def taxonomy(router_=Depends(get_router)):
    rules = router_.rules
    return {"categories": CATEGORIES, "review_department": REVIEW_DEPARTMENT,
            "review_threshold": rules.review_threshold, "secondary_threshold": rules.secondary_threshold}


@router.post("/classify", response_model=Decision)
def classify(req: ClassifyRequest, caller: str = Depends(rate_limited), router_=Depends(get_router), db=Depends(get_db)):
    decision = router_.route(req.text)
    record_decision(decision)
    decision["ticket_ref"] = None
    if req.create_ticket:
        ticket = TicketRepository(db).create(decision, channel=req.channel, customer_ref=req.customer_ref, actor=caller)
        decision["ticket_ref"] = ticket.ref
        db.commit()
        if decision["priority"] == "urgent":
            get_notifier().urgent_ticket(ticket_to_dict(ticket))
    return decision


@router.post("/classify/batch")
def classify_batch(req: BatchRequest, _: str = Depends(rate_limited), router_=Depends(get_router), db=Depends(get_db)):
    limit = get_settings().max_batch_size
    texts = [t for t in req.texts if t.strip()]
    if not texts:
        raise HTTPException(422, "All queries are empty.")
    if len(texts) > limit:
        raise HTTPException(413, f"Batch too large: {len(texts)} queries, the limit is {limit}.")
    return _route_and_store(texts, req.channel, req.create_tickets, router_, db)


@router.post("/classify/csv")
async def classify_csv(file: UploadFile = File(...), create_tickets: bool = Form(False),
                       _: str = Depends(rate_limited), router_=Depends(get_router), db=Depends(get_db)):
    """Accepts a CSV with a 'text', 'query' or 'message' column, or a plain one-query-per-line file."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows:
        raise HTTPException(422, "The file is empty.")
    header = [h.strip().lower() for h in rows[0]]
    col = next((header.index(h) for h in ("text", "query", "message") if h in header), None)
    texts = [r[col] for r in rows[1:] if len(r) > col] if col is not None else [r[0] for r in rows if r]
    texts = [t for t in texts if t.strip()]
    if not texts:
        raise HTTPException(422, "No queries found. Use a 'text' column or one query per line.")
    limit = get_settings().max_batch_size
    if len(texts) > limit:
        raise HTTPException(413, f"File has {len(texts)} queries; the limit is {limit}.")
    return _route_and_store(texts, "api", create_tickets, router_, db)
