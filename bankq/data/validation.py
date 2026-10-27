"""Data quality checks that run before every training job."""

import logging

from ..taxonomy import CATEGORIES

log = logging.getLogger(__name__)


class DataValidationError(ValueError):
    pass


def validate(train, test):
    """Drop empty and duplicate rows, remove train/test leakage, and fail on schema problems."""
    for name, df in (("train", train), ("test", test)):
        missing = {"text", "intent", "category"} - set(df.columns)
        if missing:
            raise DataValidationError(f"{name} is missing columns {sorted(missing)}")
        bad = set(df["category"]) - set(CATEGORIES)
        if bad:
            raise DataValidationError(f"{name} has unknown categories {sorted(bad)}")

    def tidy(df):
        df = df.assign(text=df["text"].astype(str).str.strip())
        df = df[df["text"].str.len() > 0]
        return df.drop_duplicates(subset="text", keep="first").reset_index(drop=True)

    train, test = tidy(train), tidy(test)

    norm = lambda s: s.str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    leaked = norm(train["text"]).isin(set(norm(test["text"])))
    if leaked.any():
        log.warning("removing train rows that also appear in test", extra={"rows": int(leaked.sum())})
        train = train[~leaked].reset_index(drop=True)

    missing = set(CATEGORIES) - set(train["category"])
    if missing:
        raise DataValidationError(f"train has no examples for {sorted(missing)}")

    log.info("data validated", extra={"train_rows": len(train), "test_rows": len(test)})
    return train, test
