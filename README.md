# Routing Desk: banking query classification and routing platform

Routing Desk reads a customer's message from any channel and does the following:
- masks personal data
- classifies the message into **Payments, Cards, Loans, Account issues or Fraud**, plus one of 83 specific topics
- applies the bank's business rules
- opens a ticket with a priority and a response deadline in the right team's queue

Agents work the queue in an inbox. Their corrections become training data, and every new model has to pass a quality gate before it can serve traffic.

```
message → mask PII → category + topic models → business rules → ticket (team, priority, deadline) → agent inbox
                                                                                                        ↓ corrections
                          model registry ← quality gate ← training job ←──────────────────────── feedback data
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and the reasons behind it.

## Quick start

```bash
make install     # virtualenv + dependencies
make train       # train, evaluate, register and promote a model (about 1 minute)
make seed        # optional: 14 days of demo tickets for the Inbox and Analytics views
make serve       # http://127.0.0.1:8077   (API docs at /docs)
make test        # unit, rules, model and API tests
```

Or with Docker: `docker compose up --build`. The image trains the model during the build, runs as a non-root user and has a health check.

## Features

| Area | What it does |
|---|---|
| **NLP models** | TF-IDF word and character n-grams; 4 model families tuned with 5-fold cross-validation; a 5-class category model plus an 83-topic sub-intent model; word-level explanations |
| **Privacy** | Card numbers (Luhn-checked), IBANs, sort codes, account numbers, emails and phone numbers are masked before classification, storage and logging |
| **Business rules** | `configs/routing_rules.yaml`: review threshold, two-tier fraud escalation (strong phrases like “skimmed” always escalate; ambiguous words like “fraud” need model support), priority overrides (bereavement, complaints, account takeover). Editable without retraining and hot-reloadable |
| **Routing** | Team, priority (urgent / high / normal), response deadline (1 h for fraud up to 48 h for loans), second category for mixed messages, manual review below 60% confidence, an audit of which rules fired |
| **Tickets** | Stored with a full event history (created, re-routed, status, assigned, note); filter, search and sort by urgency |
| **Feedback loop** | Agent re-routes are saved as labels; `make retrain` learns from them |
| **Model governance** | Versioned registry, model cards (data fingerprint, parameters, metrics, intended use, limits), a quality gate, promotion and hot reload |
| **API** | Versioned `/api/v1`, OpenAPI docs, optional API keys, rate limiting, batch and CSV endpoints, request IDs |
| **Observability** | JSON logs, Prometheus `/metrics` (traffic, latency, categories, rule hits, PII redactions), `/health` and `/ready` |
| **Delivery** | Makefile, pyproject, multi-stage Dockerfile, docker-compose, GitHub Actions CI (lint → train with gate → test → Docker build) |
| **UI** | Live routing as you type, visualised as a neural network driven by the real model output; Inbox, Batch, Analytics and Model views; light and dark mode; works on mobile |

## Results

On the held-out test set of 3,192 queries, which is never used for model selection:

| | Score |
|---|---|
| Category accuracy | **97.3%** |
| Macro F1 | **0.974** |
| Fraud recall | **95.8%** |
| Topic accuracy, 83 topics | **90.0%** (96.7% within the top 3) |
| Majority-class baseline | 46.4% accuracy |

| Model family (tuned) | CV macro F1 | Test macro F1 |
|---|---|---|
| **Logistic Regression** (C=20), selected | 0.966 ± 0.004 | 0.974 |
| Linear SVM (C=1) | 0.966 ± 0.005 | 0.957 |
| Complement Naive Bayes (α=0.1) | 0.940 ± 0.007 | 0.949 |

Every training run writes its full model card, figures and misclassified examples to `models/registry/<version>/`.

## Using the API

```bash
curl -X POST http://127.0.0.1:8077/api/v1/classify -H 'Content-Type: application/json' \
  -d '{"text": "My card 4539 1488 0343 6467 was skimmed at the ATM", "channel": "app"}'
```

The response (abridged) shows the masked text, and the rule that caught what the model missed (the model said Cards):

```json
{
  "text": "My card [CARD] was skimmed at the ATM",
  "pii_redacted": ["CARD"],
  "category": "fraud", "model_category": "cards",
  "intent": {"intent": "lost_or_stolen_card", "label": "Lost or stolen card"},
  "department": "Fraud & Security Team", "priority": "urgent", "sla_hours": 1,
  "rules_applied": [{"rule": "fraud_escalation", "detail": "strong fraud phrase “skimmed”; model said Cards 100%, fraud 0%"}],
  "ticket_ref": "TKT-000629"
}
```

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/classify` | Route one message; creates a ticket unless `create_ticket: false` |
| POST | `/api/v1/classify/batch` | Up to 1,000 messages; optional ticket creation |
| POST | `/api/v1/classify/csv` | CSV upload with a `text` column |
| GET | `/api/v1/tickets` | Queue: filter by team, status, priority, category, review, search |
| GET / PATCH | `/api/v1/tickets/{ref}` | Ticket with history; change status, re-route, assign, add a note |
| GET | `/api/v1/analytics/summary?days=14` | Volumes, review and re-route rates, deadlines, confidence, corrections |
| GET | `/api/v1/model`, `/api/v1/model/versions` | Production model card; registry |
| POST | `/api/v1/admin/reload-model` | Hot-swap to the production model and reload the rules |
| GET | `/health`, `/ready`, `/metrics` | Liveness, readiness, Prometheus |

## Configuration

All  settings are `BANKQ_*` environment variables (see `.env.example`). The important ones:

- `BANKQ_API_KEYS`: comma-separated keys. When set, every `/api/v1` call needs an `X-API-Key` header, and the UI asks for one. **When empty, auth is off. Only run like that locally.**
- `BANKQ_DATABASE_URL`: SQLite by default; any SQLAlchemy URL, e.g. Postgres.
- `BANKQ_RATE_LIMIT_PER_MINUTE`, `BANKQ_MAX_BATCH_SIZE`, `BANKQ_LOG_JSON`.

## Model lifecycle

```bash
make train                  # new version; promoted only if it passes the gate
make retrain                # same, plus agent corrections from the ticket database
make models                 # list versions, metrics and which is in production
make promote V=v2026...     # promote a specific version
curl -X POST localhost:8077/api/v1/admin/reload-model   # serve it without a restart
```

The quality gate requires macro F1 ≥ 0.93, fraud recall ≥ 0.90, topic accuracy ≥ 0.80, and no more than a 1-point macro-F1 drop against the current production model.

## Project layout

```
bankq/
  config.py  logging_setup.py  taxonomy.py
  data/        loaders · loans (generated) · preprocessing · validation
  ml/          pipeline · train · registry · predictor · transformer (task 1)
  routing/     pii · rules · router · notify (task 3)
  db/          models · session · repository
  api/         app · deps · schemas · observability · routes/
  monitoring/  drift (task 2)
configs/routing_rules.yaml
web/                 UI
scripts/seed_demo.py demo traffic
tests/               PII, rules, data, model and API tests
docs/ARCHITECTURE.md
TASKS.md             remaining work
```

## Limitations

- **Loan data is generated.** Banking77 has no loan intents. The loan queries come from 60 templates across 6 loan topics, split between train and test *by template*, so test phrasings are unseen. They are still cleaner than real messages, so the loan scores are optimistic.
- The seeded demo traffic uses real Banking77 test sentences, but the timing and agent behaviour are simulated.
- English only. One primary category per message (a second one is exposed for mixed messages).

## Remaining work

[TASKS.md](TASKS.md) lists the remaining 30%: a transformer challenger model, drift monitoring, notifications, Postgres migrations, load testing, and the report notebook.

## Credits

Banking77: Casanueva et al., *Efficient Intent Detection with Dual Sentence Encoders*, 2020, CC BY 4.0. https://github.com/PolyAI-LDN/task-specific-datasets
# NLP-
