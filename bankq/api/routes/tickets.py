from fastapi import APIRouter, Depends, HTTPException, Query

from ...db.repository import TicketRepository, ticket_to_dict
from ..deps import get_db, require_api_key
from ..schemas import TicketUpdate

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"], dependencies=[Depends(require_api_key)])


@router.get("")
def list_tickets(
    department: str | None = None,
    status: str | None = Query(default=None, description="Comma-separated, e.g. open,in_progress"),
    priority: str | None = None,
    category: str | None = None,
    needs_review: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db=Depends(get_db),
):
    total, rows = TicketRepository(db).search(department, status, priority, category, needs_review, q, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": [ticket_to_dict(t) for t in rows]}


@router.get("/{ref}")
def get_ticket(ref: str, db=Depends(get_db)):
    t = TicketRepository(db).get(ref)
    if not t:
        raise HTTPException(404, f"Ticket {ref} not found.")
    return ticket_to_dict(t, with_events=True)


@router.patch("/{ref}")
def update_ticket(ref: str, body: TicketUpdate, db=Depends(get_db)):
    repo = TicketRepository(db)
    t = repo.get(ref)
    if not t:
        raise HTTPException(404, f"Ticket {ref} not found.")
    if body.category:
        repo.reroute(t, body.category, body.actor)
    if body.assignee is not None:
        repo.assign(t, body.assignee or None, body.actor)
    if body.status:
        repo.set_status(t, body.status, body.actor)
    if body.note:
        repo.add_note(t, body.note, body.actor)
    db.commit()
    return ticket_to_dict(repo.get(ref), with_events=True)
