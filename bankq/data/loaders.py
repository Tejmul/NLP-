"""Build the training and test sets: Banking77, generated loan queries, and agent feedback."""

import logging

import pandas as pd

from ..config import get_settings
from ..taxonomy import INTENT_TO_CATEGORY
from .loans import generate_loan_queries
from .validation import validate

log = logging.getLogger(__name__)
COLUMNS = ["text", "intent", "category", "source"]


def _load_banking77(split):
    path = get_settings().raw_data_dir / f"{split}.csv"
    df = pd.read_csv(path).rename(columns={"category": "intent"})
    unmapped = set(df["intent"]) - set(INTENT_TO_CATEGORY)
    if unmapped:
        raise ValueError(f"Intents with no category mapping: {sorted(unmapped)}")
    df["category"] = df["intent"].map(INTENT_TO_CATEGORY)
    df["source"] = "banking77"
    return df[COLUMNS]


def _loans(rows):
    df = pd.DataFrame(rows, columns=["text", "intent"])
    df["category"] = "loans"
    df["source"] = "generated"
    return df[COLUMNS]


def load_feedback():
    """Agent corrections from the ticket database, used as extra training data."""
    from ..db.repository import TicketRepository
    from ..db.session import session_scope

    with session_scope() as s:
        rows = TicketRepository(s).feedback_examples()
    df = pd.DataFrame(rows, columns=["text", "category"])
    df["intent"] = "agent_feedback"
    df["source"] = "feedback"
    return df[COLUMNS]


def load_dataset(include_feedback=False):
    """Return validated (train_df, test_df) with columns text, intent, category, source."""
    loan_train, loan_test = generate_loan_queries()
    train = pd.concat([_load_banking77("train"), _loans(loan_train)], ignore_index=True)
    test = pd.concat([_load_banking77("test"), _loans(loan_test)], ignore_index=True)

    if include_feedback:
        feedback = load_feedback()
        # Feedback only ever goes into training, never into the fixed test set.
        feedback = feedback[~feedback["text"].isin(test["text"])]
        log.info("adding agent feedback to training data", extra={"rows": len(feedback)})
        train = pd.concat([train, feedback], ignore_index=True)

    train, test = validate(train, test)

    out = get_settings().processed_data_dir
    out.mkdir(parents=True, exist_ok=True)
    train.to_csv(out / "train.csv", index=False)
    test.to_csv(out / "test.csv", index=False)
    return train, test
