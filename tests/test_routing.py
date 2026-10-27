"""Router and business-rule tests with a stub model, so they test the rules and not the classifier."""

import pytest

from bankq.config import get_settings
from bankq.routing.router import Router
from bankq.routing.rules import RuleSet
from bankq.taxonomy import REVIEW_DEPARTMENT


class StubPredictor:
    version = "stub"

    def __init__(self, probs):
        self.probs = probs

    def _pred(self):
        cat = max(self.probs, key=self.probs.get)
        return {"category": cat, "confidence": self.probs[cat], "probabilities": self.probs,
                "intents": [{"intent": "x", "label": "X", "confidence": 0.9}], "keywords": []}

    def predict(self, text, explain=True):
        return self._pred()

    def intents_for(self, text, category, k=3):
        return [{"intent": f"{category}_topic", "label": "Topic", "confidence": 0.5}]

    def predict_many(self, texts):
        return [self._pred() for _ in texts]


def probs(**kw):
    base = dict.fromkeys(["payments", "cards", "loans", "account", "fraud"], 0.0)
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def rules():
    return RuleSet.from_yaml(get_settings().rules_path)


def route(rules, text, **p):
    return Router(StubPredictor(probs(**p)), rules).route(text)


def test_confident_prediction_routes_to_department(rules):
    d = route(rules, "my card has not arrived", cards=0.95, payments=0.05)
    assert d["category"] == "cards"
    assert d["department"] == "Card Services"
    assert not d["needs_review"] and d["rules_applied"] == []


def test_fraud_keyword_escalates_when_model_gives_fraud_some_weight(rules):
    d = route(rules, "there is a payment I didn't make", payments=0.7, fraud=0.25, cards=0.05)
    assert d["category"] == "fraud"
    assert d["priority"] == "urgent"
    assert d["model_category"] == "payments"
    assert d["rules_applied"][0]["rule"] == "fraud_escalation"


def test_weak_fraud_word_alone_does_not_escalate(rules):
    d = route(rules, "how do I report fraud on a loan application", loans=0.97, fraud=0.03)
    assert d["category"] == "loans"


def test_strong_fraud_phrase_escalates_even_when_model_disagrees(rules):
    d = route(rules, "I think my card was skimmed at the ATM", cards=1.0)
    assert d["category"] == "fraud" and d["model_category"] == "cards"
    assert "strong fraud phrase" in d["rules_applied"][0]["detail"]
    assert d["intent"]["intent"] == "fraud_topic"


def test_low_confidence_goes_to_review_at_normal_priority(rules):
    d = route(rules, "hello", payments=0.45, account=0.35, cards=0.2)
    assert d["needs_review"]
    assert d["department"] == REVIEW_DEPARTMENT
    assert d["priority"] == "normal"


def test_priority_override_raises_but_never_lowers(rules):
    d = route(rules, "my husband passed away, close his account", account=0.9, payments=0.1)
    assert d["priority"] == "high"
    assert any(r["rule"] == "vulnerable_customer" for r in d["rules_applied"])

    d = route(rules, "my card was stolen, my husband passed away", fraud=0.95, cards=0.05)
    assert d["priority"] == "urgent"


def test_secondary_category_for_mixed_messages(rules):
    d = route(rules, "my loan repayment transfer failed", loans=0.6, payments=0.38, cards=0.02)
    assert d["secondary_category"] == "payments"


def test_pii_is_masked_before_prediction_and_in_output(rules):
    d = route(rules, "card 4539 1488 0343 6467 lost", fraud=0.9, cards=0.1)
    assert "4539" not in d["text"] and d["pii_redacted"] == ["CARD"]


def test_urgent_tickets_get_one_hour_sla(rules):
    d = route(rules, "my card was stolen", fraud=0.99, cards=0.01)
    assert d["sla_hours"] == 1
