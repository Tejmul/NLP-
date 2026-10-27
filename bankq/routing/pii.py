"""PII redaction. Customer text is masked before it is classified, stored or logged.

Masks: card numbers (Luhn-validated), IBANs, UK sort codes, account numbers,
email addresses and phone numbers. The placeholders ([CARD], [EMAIL], ...) are
kept in the text so agents can see that something was there.
"""

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b")
_DIGIT_RUN = re.compile(r"(?<![\w£$€₹])\+?\d(?:[\s-]?\d){7,18}(?![\w])")
_SORT_CODE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
_ACCOUNT_CONTEXT = re.compile(r"\b(account|acct|a/c)\s*(no\.?|number|#)?\s*:?\s*(\d{6,18})\b", re.I)


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _classify_digits(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return "CARD"
    if raw.startswith("+") or (digits.startswith("0") and 10 <= len(digits) <= 11):
        return "PHONE"
    return "ACCOUNT"


def redact(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, sorted list of PII types found)."""
    found = set()

    def sub(kind):
        def _r(_m):
            found.add(kind)
            return f"[{kind}]"
        return _r

    text = _EMAIL.sub(sub("EMAIL"), text)
    text = _IBAN.sub(sub("IBAN"), text)
    text = _SORT_CODE.sub(sub("SORT_CODE"), text)
    text = _ACCOUNT_CONTEXT.sub(lambda m: (found.add("ACCOUNT"), m.group(0).replace(m.group(3), "[ACCOUNT]"))[1], text)

    def digits(m):
        kind = _classify_digits(m.group(0))
        found.add(kind)
        return f"[{kind}]"

    text = _DIGIT_RUN.sub(digits, text)
    return text, sorted(found)
