"""Checks on the production model. These fail if a bad model is promoted."""

import pytest

from bankq.ml.predictor import Predictor
from bankq.ml.registry import ModelRegistry
from bankq.ml.train import QUALITY_GATE


@pytest.fixture(scope="module")
def predictor():
    return Predictor()


def test_production_model_passed_its_quality_gate():
    reg = ModelRegistry()
    card = reg.card(reg.production_version())
    m = card["metrics"]["category"]
    assert card["quality_gate"]["passed"]
    assert m["macro_f1"] >= QUALITY_GATE["min_macro_f1"]
    assert m["per_class"]["fraud"]["recall"] >= QUALITY_GATE["min_fraud_recall"]


@pytest.mark.parametrize("text, expected", [
    ("Someone used my card without my permission", "fraud"),
    ("My card still hasn't arrived", "cards"),
    ("What is the interest rate on a personal loan?", "loans"),
    ("My bank transfer has not arrived yet", "payments"),
    ("How do I verify my identity?", "account"),
    ("I lost my phone with the banking app on it", "fraud"),
    ("How much is the EMI on a 5 lakh home loan", "loans"),
])
def test_canonical_queries(predictor, text, expected):
    assert predictor.predict(text, explain=False)["category"] == expected


def test_probabilities_are_a_distribution(predictor):
    p = predictor.predict("exchange rate for dollars")["probabilities"]
    assert abs(sum(p.values()) - 1) < 1e-3


def test_sub_intent_belongs_to_predicted_category(predictor):
    r = predictor.predict("my card got stuck in the ATM", explain=False)
    assert r["category"] == "cards"
    assert r["intents"][0]["intent"] == "card_swallowed"
