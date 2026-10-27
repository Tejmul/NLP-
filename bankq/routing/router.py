"""The routing engine: redact PII, predict, apply business rules, and decide where a query goes."""

import logging
import time
from datetime import UTC, datetime, timedelta

from ..ml.predictor import Predictor
from ..taxonomy import CATEGORIES, PRIORITY_RANK, REVIEW_DEPARTMENT, REVIEW_SLA_HOURS
from .pii import redact
from .rules import RuleSet

log = logging.getLogger("bankq.router")


class Router:
    def __init__(self, predictor: Predictor, rules: RuleSet):
        self.predictor = predictor
        self.rules = rules

    @property
    def model_version(self):
        return self.predictor.version

    def _decide(self, text, pii, pred, latency_ms):
        rules = self.rules
        applied = []
        probs = pred["probabilities"]
        category, confidence = pred["category"], pred["confidence"]

        # Fraud safety net: a fraud keyword plus some model support overrides the top category.
        hit = rules.fraud_keyword(text)
        if hit and category != "fraud":
            kw, strong = hit
            if strong or probs.get("fraud", 0) >= rules.fraud_min_probability:
                kind = "strong fraud phrase" if strong else "keyword"
                detail = f"{kind} “{kw}”; model said {CATEGORIES[category]['label']} {confidence:.0%}, fraud {probs['fraud']:.0%}"
                applied.append({"rule": "fraud_escalation", "detail": detail})
                category, confidence = "fraud", probs["fraud"]

        info = CATEGORIES[category]
        escalated = bool(applied)
        needs_review = confidence < rules.review_threshold and not escalated
        if needs_review:
            applied.append({"rule": "low_confidence", "detail": f"{confidence:.0%} is below the "
                            f"{rules.review_threshold:.0%} review threshold"})

        # A low-confidence guess should not set priority; review tickets start at normal.
        priority = "normal" if needs_review else info["priority"]
        override = rules.priority_override(text)
        if override and PRIORITY_RANK[override[0]] < PRIORITY_RANK[priority]:
            priority = override[0]
            applied.append({"rule": override[1], "detail": f"keyword “{override[2]}” raised priority to {priority}"})

        ranked = sorted(probs.items(), key=lambda kv: -kv[1])
        secondary = next((c for c, p in ranked if c != category and p >= rules.secondary_threshold), None)

        sla_hours = REVIEW_SLA_HOURS if needs_review and priority != "urgent" else info["sla_hours"]
        if priority == "urgent":
            sla_hours = min(sla_hours, 1)
        elif priority == "high":
            sla_hours = min(sla_hours, 8)

        intents = pred["intents"]
        if escalated:
            intents = self.predictor.intents_for(text, "fraud")

        return {
            "text": text,
            "pii_redacted": pii,
            "category": category,
            "label": info["label"],
            "intent": intents[0] if intents else None,
            "intent_alternatives": intents[1:],
            "confidence": round(confidence, 4),
            "model_category": pred["category"],
            "secondary_category": secondary,
            "probabilities": probs,
            "needs_review": needs_review,
            "department": REVIEW_DEPARTMENT if needs_review else info["department"],
            "priority": priority,
            "sla_hours": sla_hours,
            "due_at": (datetime.now(UTC) + timedelta(hours=sla_hours)).isoformat(timespec="seconds"),
            "rules_applied": applied,
            "keywords": pred["keywords"],
            "model_version": self.model_version,
            "latency_ms": latency_ms,
        }

    def route(self, raw_text: str, explain: bool = True) -> dict:
        start = time.perf_counter()
        text, pii = redact(raw_text.strip())
        pred = self.predictor.predict(text, explain=explain)
        decision = self._decide(text, pii, pred, round((time.perf_counter() - start) * 1000, 1))
        log.info("query routed", extra={
            "category": decision["category"], "confidence": decision["confidence"],
            "needs_review": decision["needs_review"], "priority": decision["priority"],
            "rules": [r["rule"] for r in decision["rules_applied"]], "latency_ms": decision["latency_ms"]})
        return decision

    def route_many(self, raw_texts: list[str]) -> list[dict]:
        start = time.perf_counter()
        redacted = [redact(t.strip()) for t in raw_texts]
        preds = self.predictor.predict_many([t for t, _ in redacted])
        per_item = round((time.perf_counter() - start) * 1000 / max(len(raw_texts), 1), 2)
        return [self._decide(t, pii, p, per_item) for (t, pii), p in zip(redacted, preds)]
