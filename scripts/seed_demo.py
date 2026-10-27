"""Fill the ticket database with realistic demo traffic for the Inbox and Analytics views.

Routes real held-out test queries through the production router, spreads them over
the last 14 days, and simulates agents: most tickets get resolved, and tickets the
model got wrong are re-routed to their true category (as an agent would).

    python -m scripts.seed_demo --n 600 --reset
"""

import argparse
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from bankq.api.app import build_router
from bankq.config import get_settings
from bankq.data.loaders import load_dataset
from bankq.db.models import Ticket, TicketEvent
from bankq.db.repository import TicketRepository
from bankq.db.session import init_db, session_scope

CHANNELS = ["app", "app", "app", "web", "web", "chat", "email", "phone"]
AGENTS = ["asha.k", "dan.m", "priya.s", "tom.r", "li.w"]
EXTRA = [  # messages that exercise PII masking and business rules
    ("My card 4539 1488 0343 6467 was used in a shop I've never been to", "fraud"),
    ("Please call me on 07700 900123, I think my account was hacked", "fraud"),
    ("My father passed away and I need to close his account", "account"),
    ("I will be going to the ombudsman if my refund isn't sorted", "payments"),
    ("Email me at sam.jones@example.com about my loan application", "loans"),
    ("I'm locked out and someone logged in from a new device", "fraud"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--reset", action="store_true", help="delete existing tickets first")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    init_db()
    router = build_router()
    _, test = load_dataset()
    sample = test.sample(n=min(args.n, len(test)), random_state=args.seed)
    rows = list(zip(sample["text"], sample["category"])) + EXTRA
    rng.shuffle(rows)

    decisions = router.route_many([t for t, _ in rows])
    now = datetime.now(UTC)

    with session_scope() as s:
        if args.reset:
            s.execute(delete(TicketEvent))
            s.execute(delete(Ticket))
        repo = TicketRepository(s)
        for (_text, truth), d in zip(rows, decisions):
            # More traffic on recent days and in working hours.
            day = min(int(rng.expovariate(1 / (args.days / 3))), args.days - 1)
            created = now - timedelta(days=day, hours=rng.uniform(0, 10), minutes=rng.uniform(0, 59))
            t = repo.create(d, channel=rng.choice(CHANNELS), customer_ref=f"C{rng.randint(10000, 99999)}",
                            created_at=created)
            age_h = (now - created).total_seconds() / 3600
            agent = rng.choice(AGENTS)

            if age_h > 2 and rng.random() < 0.95:
                if truth != d["category"] or d["needs_review"]:
                    repo.reroute(t, truth, agent, at=created + timedelta(minutes=rng.uniform(5, 90)))
                    s.flush()
                t.assignee = agent
                # Most tickets close within their SLA; some slip.
                sla = (t.due_at.replace(tzinfo=UTC) if t.due_at.tzinfo is None else t.due_at) - created
                took = sla * rng.uniform(0.1, 0.9 if rng.random() < 0.9 else 1.6)
                done = min(created + took, now - timedelta(minutes=5))
                repo.set_status(t, "resolved", agent, at=done)
            elif age_h > 1 and rng.random() < 0.5:
                t.assignee = agent
                repo.set_status(t, "in_progress", agent, at=created + timedelta(minutes=rng.uniform(5, 50)))

    print(f"Seeded {len(rows)} tickets into {get_settings().database_url}")


if __name__ == "__main__":
    main()
