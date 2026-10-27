"""Alerting for urgent tickets.

The default notifier only writes a log line. Replacing it with a real channel
(Slack webhook, email, PagerDuty) is task 3 in TASKS.md.
"""

import logging
from typing import Protocol

log = logging.getLogger("bankq.notify")


class Notifier(Protocol):
    def urgent_ticket(self, ticket: dict) -> None: ...


class LogNotifier:
    def urgent_ticket(self, ticket: dict) -> None:
        log.warning("urgent ticket created", extra={
            "ticket": ticket["ref"], "department": ticket["department"], "due_at": ticket["due_at"]})


# TODO(TASKS.md #3): implement SlackNotifier / EmailNotifier and choose one from settings.
def get_notifier() -> Notifier:
    return LogNotifier()
