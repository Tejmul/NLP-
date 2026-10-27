"""The routing taxonomy: categories, their departments and service levels, and the sub-intents under each."""

from .data.loans import LOAN_INTENTS

CATEGORIES = {
    "payments": {
        "label": "Payments",
        "department": "Payments & Transfers Desk",
        "priority": "high",
        "sla_hours": 8,
        "description": "Transfers, top-ups, refunds, exchange rates, fees and pending or declined payments.",
    },
    "cards": {
        "label": "Cards",
        "department": "Card Services",
        "priority": "normal",
        "sla_hours": 24,
        "description": "Ordering, activating and using physical or virtual cards, PINs and card issues.",
    },
    "loans": {
        "label": "Loans",
        "department": "Lending Team",
        "priority": "normal",
        "sla_hours": 48,
        "description": "Personal, car, home and student loans, EMIs, interest rates and repayments.",
    },
    "account": {
        "label": "Account issues",
        "department": "Account Services",
        "priority": "normal",
        "sla_hours": 24,
        "description": "Identity verification, personal details, passcodes, eligibility and closing accounts.",
    },
    "fraud": {
        "label": "Fraud",
        "department": "Fraud & Security Team",
        "priority": "urgent",
        "sla_hours": 1,
        "description": "Unrecognised transactions, compromised, lost or stolen cards and phones.",
    },
}

REVIEW_DEPARTMENT = "General Support (manual review)"
REVIEW_SLA_HOURS = 24
PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2}

_CATEGORY_INTENTS = {
    "fraud": [
        "card_payment_not_recognised",
        "cash_withdrawal_not_recognised",
        "compromised_card",
        "direct_debit_payment_not_recognised",
        "lost_or_stolen_card",
        "lost_or_stolen_phone",
    ],
    "cards": [
        "activate_my_card",
        "apple_pay_or_google_pay",
        "atm_support",
        "card_about_to_expire",
        "card_acceptance",
        "card_arrival",
        "card_delivery_estimate",
        "card_linking",
        "card_not_working",
        "card_swallowed",
        "change_pin",
        "contactless_not_working",
        "declined_card_payment",
        "declined_cash_withdrawal",
        "disposable_card_limits",
        "get_disposable_virtual_card",
        "get_physical_card",
        "getting_spare_card",
        "getting_virtual_card",
        "order_physical_card",
        "pin_blocked",
        "supported_cards_and_currencies",
        "virtual_card_not_working",
        "visa_or_mastercard",
    ],
    "account": [
        "age_limit",
        "country_support",
        "edit_personal_details",
        "fiat_currency_support",
        "passcode_forgotten",
        "terminate_account",
        "unable_to_verify_identity",
        "verify_my_identity",
        "verify_source_of_funds",
        "why_verify_identity",
    ],
    "payments": [
        "Refund_not_showing_up",
        "automatic_top_up",
        "balance_not_updated_after_bank_transfer",
        "balance_not_updated_after_cheque_or_cash_deposit",
        "beneficiary_not_allowed",
        "cancel_transfer",
        "card_payment_fee_charged",
        "card_payment_wrong_exchange_rate",
        "cash_withdrawal_charge",
        "declined_transfer",
        "exchange_charge",
        "exchange_rate",
        "exchange_via_app",
        "extra_charge_on_statement",
        "failed_transfer",
        "pending_card_payment",
        "pending_cash_withdrawal",
        "pending_top_up",
        "pending_transfer",
        "receiving_money",
        "request_refund",
        "reverted_card_payment?",
        "top_up_by_bank_transfer_charge",
        "top_up_by_card_charge",
        "top_up_by_cash_or_cheque",
        "top_up_failed",
        "top_up_limits",
        "top_up_reverted",
        "topping_up_by_card",
        "transaction_charged_twice",
        "transfer_fee_charged",
        "transfer_into_account",
        "transfer_not_received_by_recipient",
        "transfer_timing",
        "verify_top_up",
        "wrong_amount_of_cash_received",
        "wrong_exchange_rate_for_cash_withdrawal",
    ],
}

INTENT_TO_CATEGORY = {
    intent: category for category, intents in _CATEGORY_INTENTS.items() for intent in intents
}

INTENT_TO_CATEGORY.update({intent: "loans" for intent in LOAN_INTENTS})

CATEGORY_ORDER = list(CATEGORIES)


def intent_label(intent: str) -> str:
    """'lost_or_stolen_card' -> 'Lost or stolen card'."""
    text = intent.strip("?").replace("_", " ").strip()
    return text[:1].upper() + text[1:].lower()
