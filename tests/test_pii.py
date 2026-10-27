import pytest

from bankq.routing.pii import redact


@pytest.mark.parametrize("text, expected_text, types", [
    ("my card 4539 1488 0343 6467 was cloned", "my card [CARD] was cloned", ["CARD"]),
    ("card 4539-1488-0343-6467", "card [CARD]", ["CARD"]),
    ("email me at sam.jones@example.com", "email me at [EMAIL]", ["EMAIL"]),
    ("call 07700 900123 please", "call [PHONE] please", ["PHONE"]),
    ("call +91 98765 43210", "call [PHONE]", ["PHONE"]),
    ("sort code 20-00-00", "sort code [SORT_CODE]", ["SORT_CODE"]),
    ("IBAN GB29 NWBK 6016 1331 9268 19", "IBAN [IBAN]", ["IBAN"]),
    ("account number 12345678 is blocked", "account number [ACCOUNT] is blocked", ["ACCOUNT"]),
])
def test_masks_pii(text, expected_text, types):
    out, found = redact(text)
    assert out == expected_text
    assert found == types


def test_number_that_fails_luhn_is_not_called_a_card():
    out, found = redact("ref 1234 5678 9012 3456")
    assert "CARD" not in found and "[ACCOUNT]" in out


@pytest.mark.parametrize("text", [
    "I sent £500 to my landlord",
    "can I borrow 10,000 over 3 years",
    "it has been 3 days since I ordered my card",
    "I was charged twice on 12/05",
])
def test_leaves_ordinary_numbers_alone(text):
    assert redact(text) == (text, [])
