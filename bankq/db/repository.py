"""Data access for tickets: create, query, update, feedback export and analytics."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..taxonomy import CATEGORIES, CATEGORY_ORDER, PRIORITY_RANK
from .models import Ticket, TicketEvent

STATUSES = ("open", "in_progress", "resolved")


def _aware(dt):
    """SQLite drops tzinfo; everything we store is UTC."""
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def _iso(dt):
    return _aware(dt).isoformat(timespec="seconds") if dt else None


def effective_category(t: Ticket) -> str:
    return t.final_category or t.category


def ticket_to_dict(t: Ticket, with_events=False) -> dict:
    now = datetime.now(UTC)
    due = _aware(t.due_at)
    done = _aware(t.resolved_at)
    d = {
        "ref": t.ref,
        "created_at": _iso(t.created_at),
        "updated_at": _iso(t.updated_at),
        "channel": t.channel,
        "customer_ref": t.customer_ref,
        "text": t.text,
        "pii_redacted": t.pii_types or [],
        "category": effective_category(t),
        "label": CATEGORIES[effective_category(t)]["label"],
        "model_category": t.category,
        "rerouted": bool(t.final_category and t.final_category != t.category),
        "intent": t.intent,
        "intent_confidence": t.intent_confidence,
        "confidence": t.confidence,
        "secondary_category": t.secondary_category,
        "probabilities": t.probabilities,
        "needs_review": t.needs_review,
        "rules_applied": t.rules_applied or [],
        "model_version": t.model_version,
        "latency_ms": t.latency_ms,
        "department": t.department,
        "priority": t.priority,
        "status": t.status,
        "assignee": t.assignee,
        "due_at": _iso(due),
        "resolved_at": _iso(done),
        "sla_breached": (done or now) > due,
    }
    if with_events:
        d["events"] = [{"at": _iso(e.at), "actor": e.actor, "type": e.type, "data": e.data} for e in t.events]
    return d


class TicketRepository:
    def __init__(self, session: Session):
        self.s = session

    # ---------- Writes ----------

    def create(self, decision: dict, channel="web", customer_ref=None, actor="router", created_at=None) -> Ticket:
        created_at = created_at or datetime.now(UTC)
        intent = decision.get("intent") or {}
        t = Ticket(
            created_at=created_at,
            updated_at=created_at,
            channel=channel,
            customer_ref=customer_ref,
            text=decision["text"],
            pii_types=decision["pii_redacted"],
            category=decision["category"],
            intent=intent.get("intent"),
            intent_confidence=intent.get("confidence"),
            confidence=decision["confidence"],
            secondary_category=decision["secondary_category"],
            probabilities=decision["probabilities"],
            needs_review=decision["needs_review"],
            rules_applied=decision["rules_applied"],
            model_version=decision["model_version"],
            latency_ms=decision["latency_ms"],
            department=decision["department"],
            priority=decision["priority"],
            due_at=created_at + timedelta(hours=decision["sla_hours"]),
        )
        self.s.add(t)
        self.s.flush()
        t.ref = f"TKT-{t.id:06d}"
        t.events.append(TicketEvent(at=created_at, actor=actor, type="created", data={
            "department": t.department, "category": t.category, "confidence": t.confidence}))
        return t

    def get(self, ref: str) -> Ticket | None:
        return self.s.scalar(select(Ticket).options(selectinload(Ticket.events)).where(Ticket.ref == ref))

    def reroute(self, t: Ticket, new_category: str, actor: str, at=None):
        if new_category not in CATEGORIES:
            raise ValueError(f"Unknown category {new_category!r}")
        if new_category == effective_category(t) and not t.needs_review:
            return
        at = at or datetime.now(UTC)
        info = CATEGORIES[new_category]
        before = {"category": effective_category(t), "department": t.department}
        t.final_category = new_category
        t.department = info["department"]
        t.needs_review = False
        if PRIORITY_RANK[info["priority"]] < PRIORITY_RANK[t.priority] or before["category"] != new_category:
            t.priority = info["priority"]
        t.due_at = _aware(t.created_at) + timedelta(hours=info["sla_hours"])
        t.updated_at = at
        t.events.append(TicketEvent(at=at, actor=actor, type="rerouted", data={
            "from": before, "to": {"category": new_category, "department": t.department}}))

    def set_status(self, t: Ticket, status: str, actor: str, at=None):
        if status not in STATUSES:
            raise ValueError(f"Status must be one of {STATUSES}")
        if status == t.status:
            return
        at = at or datetime.now(UTC)
        t.events.append(TicketEvent(at=at, actor=actor, type="status", data={"from": t.status, "to": status}))
        t.status = status
        t.resolved_at = at if status == "resolved" else None
        t.updated_at = at

    def assign(self, t: Ticket, assignee: str | None, actor: str):
        t.assignee = assignee
        t.events.append(TicketEvent(actor=actor, type="assigned", data={"assignee": assignee}))

    def add_note(self, t: Ticket, note: str, actor: str):
        t.events.append(TicketEvent(actor=actor, type="note", data={"note": note}))
        t.updated_at = datetime.now(UTC)

    # ---------- Reads ----------

    def search(self, department=None, status=None, priority=None, category=None, needs_review=None,
             q=None, page=1, page_size=25):
        stmt = select(Ticket)
        if department:
            stmt = stmt.where(Ticket.department == department)
        if status:
            stmt = stmt.where(Ticket.status.in_(status.split(",")))
        if priority:
            stmt = stmt.where(Ticket.priority == priority)
        if category:
            stmt = stmt.where(func.coalesce(Ticket.final_category, Ticket.category) == category)
        if needs_review is not None:
            stmt = stmt.where(Ticket.needs_review == needs_review)
        if q:
            stmt = stmt.where(or_(Ticket.text.ilike(f"%{q}%"), Ticket.ref.ilike(f"%{q}%")))
        total = self.s.scalar(select(func.count()).select_from(stmt.subquery()))
        # Unresolved first, then most urgent, then the earliest deadline.
        order = [
            case((Ticket.status == "resolved", 1), else_=0),
            case(PRIORITY_RANK, value=Ticket.priority, else_=9),
            Ticket.due_at.asc(),
        ]
        rows = self.s.scalars(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
        return total, rows

    def feedback_examples(self) -> list[tuple[str, str]]:
        rows = self.s.execute(select(Ticket.text, Ticket.final_category).where(
            Ticket.final_category.is_not(None), Ticket.final_category != Ticket.category)).all()
        return [(t, c) for t, c in rows]

    def analytics(self, days=14) -> dict:
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        tickets = self.s.scalars(select(Ticket).where(Ticket.created_at >= since)).all()

        by_day = defaultdict(Counter)
        for i in range(days):
            by_day[(since + timedelta(days=i + 1)).date().isoformat()]
        mix, channels, corrections, open_dept, breached_dept = Counter(), Counter(), Counter(), Counter(), Counter()
        conf_bins = [0] * 10
        latencies = []
        reviewed = rerouted = breached = resolved = resolved_on_time = 0

        for t in tickets:
            cat = effective_category(t)
            created = _aware(t.created_at)
            due = _aware(t.due_at)
            done = _aware(t.resolved_at)
            by_day[created.date().isoformat()][cat] += 1
            mix[cat] += 1
            channels[t.channel] += 1
            conf_bins[min(int(t.confidence * 10), 9)] += 1
            latencies.append(t.latency_ms)
            reviewed += t.needs_review or any(r.get("rule") == "low_confidence" for r in (t.rules_applied or []))
            if t.final_category and t.final_category != t.category:
                rerouted += 1
                corrections[(t.category, t.final_category)] += 1
            late = (done or now) > due
            if t.status != "resolved":
                open_dept[t.department] += 1
                if late:
                    breached += 1
                    breached_dept[t.department] += 1
            else:
                resolved += 1
                resolved_on_time += not late

        n = len(tickets)
        latencies.sort()
        pct = lambda p: round(latencies[min(int(p * len(latencies)), len(latencies) - 1)], 1) if latencies else None
        return {
            "window_days": days,
            "generated_at": now.isoformat(timespec="seconds"),
            "kpis": {
                "tickets": n,
                "auto_routed_rate": round(1 - reviewed / n, 4) if n else None,
                "review_rate": round(reviewed / n, 4) if n else None,
                "reroute_rate": round(rerouted / n, 4) if n else None,
                "open": sum(open_dept.values()),
                "open_sla_breached": breached,
                "sla_met_rate": round(resolved_on_time / resolved, 4) if resolved else None,
                "avg_confidence": round(sum(t.confidence for t in tickets) / n, 4) if n else None,
                "latency_p50_ms": pct(0.5),
                "latency_p95_ms": pct(0.95),
            },
            "by_day": [{"date": d, **{c: by_day[d][c] for c in CATEGORY_ORDER}} for d in sorted(by_day)],
            "category_mix": {c: mix[c] for c in CATEGORY_ORDER},
            "channels": dict(channels),
            "open_by_department": [{"department": d, "open": c, "breached": breached_dept[d]}
                                   for d, c in open_dept.most_common()],
            "confidence_histogram": [{"bin": f"{i / 10:.1f}–{(i + 1) / 10:.1f}", "count": c}
                                     for i, c in enumerate(conf_bins)],
            "top_corrections": [{"from": a, "to": b, "count": c} for (a, b), c in corrections.most_common(6)],
        }
