"""Text normalisation shared by training and inference.

This module is referenced by the pickled model pipelines, so renaming it or
`clean_text` requires retraining.
"""

import re

_AMOUNT = re.compile(r"[£$€₹]\s?\d[\d,.]*k?|\d[\d,.]*\s?(?:k|lakh|pounds|dollars|euros|usd|gbp|eur)\b")
_NUMBER = re.compile(r"\d+")
_PII_TOKEN = re.compile(r"\[(CARD|ACCOUNT|IBAN|SORT_CODE|EMAIL|PHONE)\]")


def clean_text(text):
    """Lowercase, replace money amounts, numbers and redaction markers with placeholder tokens."""
    text = _PII_TOKEN.sub(lambda m: f" pii{m.group(1).lower().replace('_', '')} ", str(text))
    text = text.lower()
    text = _AMOUNT.sub(" amounttoken ", text)
    text = _NUMBER.sub(" numtoken ", text)
    return re.sub(r"\s+", " ", text).strip()
