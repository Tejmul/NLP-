"""Generated loan queries.

Banking77 has no loan intents, so the "loans" category is built from templates.
Train and test are split by *template*, so the test set only contains phrasings
the model never saw during training. This keeps the loan scores from being
inflated by near-duplicate sentences.
"""

import itertools
import random

SLOTS = {
    "loan": [
        "loan", "personal loan", "car loan", "home loan", "mortgage", "student loan",
        "business loan", "auto loan", "education loan", "housing loan",
    ],
    "amount": ["5000", "10,000", "£20k", "$15,000", "50000", "2 lakh", "€8,000", "300k"],
    "time": [
        "last week", "yesterday", "a month ago", "two weeks ago", "on monday", "3 days ago",
    ],
    "term": ["12 months", "3 years", "5 years", "24 months", "10 years", "36 months"],
}

TEMPLATES = {
    "loan_application": [
        "how do i apply for a {loan}",
        "i want to take out a {loan} of {amount}",
        "can i get a {loan} for {amount}",
        "am i eligible for a {loan}",
        "what documents do i need for a {loan} application",
        "is it possible to borrow {amount} over {term}",
        "what is the minimum salary required for a {loan}",
        "can i apply for a {loan} online through the app",
        "i would like to borrow {amount}, what are my options",
        "do you offer a {loan} to self employed people",
        "what credit score do i need to qualify for a {loan}",
        "can i get pre-approved for a {loan}",
    ],
    "loan_application_status": [
        "what is the status of my {loan} application",
        "i applied for a {loan} {time} and haven't heard back",
        "why was my {loan} application rejected",
        "my {loan} got declined, can you tell me why",
        "how long does {loan} approval take",
        "when will the {loan} amount be disbursed to my account",
        "my {loan} was approved {time} but the money hasn't arrived",
    ],
    "loan_interest_and_fees": [
        "what is the interest rate on a {loan}",
        "is the {loan} rate fixed or variable",
        "how much interest will i pay on {amount} over {term}",
        "why did the interest on my {loan} go up",
        "are there any processing fees for a {loan}",
        "what is the APR for a {loan} of {amount}",
        "can you lower the interest rate on my {loan}",
    ],
    "loan_repayment": [
        "how much will my monthly EMI be for {amount}",
        "when is my next {loan} instalment due",
        "i missed my {loan} repayment {time}, what happens now",
        "can i change the date my {loan} EMI is collected",
        "what happens if i can't make my {loan} repayments",
        "my {loan} EMI was deducted twice this month",
        "can i pause my {loan} repayments for a few months",
        "is there a penalty for a late {loan} payment",
        "how many instalments are left on my {loan}",
        "can i reduce my monthly {loan} repayments",
    ],
    "loan_closure": [
        "can i pay off my {loan} early",
        "is there a fee for closing my {loan} before {term}",
        "i want to make a part prepayment of {amount} on my {loan}",
        "how do i get a no objection certificate after closing my {loan}",
        "what is the outstanding balance on my {loan}",
        "how much do i need to pay to settle my {loan} in full",
    ],
    "loan_servicing": [
        "can i increase the amount of my existing {loan}",
        "i want to extend the tenure of my {loan} to {term}",
        "can i transfer my {loan} from another bank to you",
        "can i refinance my {loan} at a lower rate",
        "please send me the statement for my {loan}",
        "where can i see the repayment schedule for my {loan}",
        "i need an interest certificate for my {loan} for tax purposes",
        "can i add a co-applicant to my {loan}",
        "is a guarantor required for a {loan} of {amount}",
        "do i need collateral to get a {loan}",
        "can i get a top up on my {loan}",
        "my {loan} account shows the wrong outstanding amount",
        "how do i set up auto debit for my {loan} repayments",
        "will taking a {loan} affect my credit score",
        "i lost my job, can my {loan} be restructured",
        "what is the maximum tenure for a {loan}",
        "how much can i borrow with a salary of {amount}",
        "i need an overdraft or a small loan to cover rent",
    ],
}


def _expand(template, rng, max_variants):
    keys = [k for k in SLOTS if "{" + k + "}" in template]
    combos = list(itertools.product(*(SLOTS[k] for k in keys)))
    rng.shuffle(combos)
    return [template.format(**dict(zip(keys, c))) for c in combos[:max_variants]]


LOAN_INTENTS = list(TEMPLATES)


def generate_loan_queries(seed=42, variants_per_template=16, test_fraction=0.2):
    """Return (train, test) lists of (text, intent), with no template shared between them.

    The split is made within each intent, so every loan intent appears in both sets.
    """
    rng = random.Random(seed)
    train_groups, test_groups = [], []
    for intent, templates in TEMPLATES.items():
        templates = templates[:]
        rng.shuffle(templates)
        n_test = max(1, round(len(templates) * test_fraction))
        test_groups += [(t, intent) for t in templates[:n_test]]
        train_groups += [(t, intent) for t in templates[n_test:]]

    def build(group):
        rows = {}
        for t, intent in group:
            for text in _expand(t, rng, variants_per_template):
                # Mimic real chat input: some capitalised, some with a question mark.
                if rng.random() < 0.5:
                    text = text[0].upper() + text[1:]
                if rng.random() < 0.4:
                    text += "?"
                rows[text] = intent
        return sorted(rows.items())

    return build(train_groups), build(test_groups)
