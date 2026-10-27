import pandas as pd
import pytest

from bankq.config import get_settings
from bankq.data.loans import LOAN_INTENTS, generate_loan_queries
from bankq.data.preprocessing import clean_text
from bankq.data.validation import DataValidationError, validate
from bankq.taxonomy import CATEGORIES, INTENT_TO_CATEGORY


def test_every_banking77_intent_is_mapped():
    intents = set(pd.read_csv(get_settings().raw_data_dir / "train.csv")["category"])
    assert len(intents) == 77
    assert intents <= set(INTENT_TO_CATEGORY)
    assert set(INTENT_TO_CATEGORY.values()) == set(CATEGORIES)


def test_loan_split_has_no_shared_text_and_covers_every_intent():
    train, test = generate_loan_queries()
    assert not {t for t, _ in train} & {t for t, _ in test}
    assert {i for _, i in train} == {i for _, i in test} == set(LOAN_INTENTS)


def test_clean_text_normalises_amounts_numbers_and_pii_markers():
    assert clean_text("I sent £50 on 3 May") == "i sent amounttoken on numtoken may"
    assert clean_text("card [CARD] stolen") == "card piicard stolen"


def _df(rows):
    return pd.DataFrame(rows, columns=["text", "intent", "category"])


def test_validation_drops_duplicates_blanks_and_leakage():
    train = _df([("a b", "i", c) for c in CATEGORIES] + [("dup", "i", "cards"), ("dup", "i", "cards"),
                 ("  ", "i", "cards"), ("In Test!", "i", "fraud")])
    train.loc[:4, "text"] = [f"text {i}" for i in range(5)]
    test = _df([("in test", "i", "fraud")])
    out, _ = validate(train, test)
    assert out["text"].tolist().count("dup") == 1
    assert "In Test!" not in out["text"].tolist()
    assert (out["text"].str.strip() != "").all()


def test_validation_rejects_unknown_category():
    with pytest.raises(DataValidationError):
        validate(_df([("x", "i", "mortgages")]), _df([("y", "i", "cards")]))
