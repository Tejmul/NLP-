"""TASK 2 (yours): production drift monitoring. See TASKS.md #2.

Models degrade silently when customer language changes (a new product, a new scam).
Compare recent traffic with the training baseline and raise an alert when they diverge.
"""


def population_stability_index(expected: list[float], actual: list[float]) -> float:
    """PSI between two distributions given as bin proportions (each sums to 1).

    PSI = sum((a - e) * ln(a / e)). Rule of thumb: < 0.1 stable, 0.1-0.25 watch, > 0.25 drifted.
    """
    # TODO: implement; guard against zero bins with a small epsilon (e.g. 1e-4).
    raise NotImplementedError("TASKS.md #2")


def drift_report(days: int = 7) -> dict:
    """Build a drift report from recent tickets.

    TODO:
      1. Baseline: category mix and confidence histogram from the production model card
         (card["data"]["train_counts"]) and from the test-set predictions.
      2. Current: the same from tickets in the last `days` (TicketRepository.analytics()).
      3. Return PSI for the category mix and the confidence histogram, the share of
         out-of-vocabulary words in recent tickets, and a status: stable / watch / drifted.
      4. Expose it at GET /api/v1/monitoring/drift and show it on the Analytics tab.
    """
    raise NotImplementedError("TASKS.md #2")
