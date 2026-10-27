# Your tasks: the remaining 30%

The platform works end to end without these. Each task extends it the way a team would after a first release. Each has a stub or a clear place to plug in, acceptance criteria, and hints. Do them in any order. Tasks 1 and 2 carry the most weight for an NLP project.

| # | Task | Area | Effort |
|---|---|---|---|
| 1 | Transformer challenger model | NLP / ML | 1–2 days |
| 2 | Drift monitoring | MLOps | 1 day |
| 3 | Urgent-ticket notifications | Backend | half a day |
| 4 | Postgres and database migrations | Backend / infra | half a day |
| 5 | Load test and performance report | Performance | half a day |
| 6 | Project report notebook | Analysis | 1 day |

---

## 1. Transformer challenger model

**Why:** TF-IDF can't tell that "my card was used in a shop I've never been to" means fraud; the rules engine catches it instead. A fine-tuned transformer understands meaning, not just words. Run it as a *challenger* and let the quality gate decide.

**Where:** `bankq/ml/transformer.py` (stub with the interface), `bankq/ml/train.py`.

**Do:**
1. `pip install -e ".[transformer]"`.
2. Implement `TransformerClassifier.fit / predict_proba` with `distilbert-base-uncased` (2–3 epochs, lr 5e-5, max length 64). Google Colab's free GPU trains it in about 10 minutes.
3. Add a `--model transformer` option to `bankq.ml.train` that trains it, evaluates it with the same `evaluate_category`, `evaluate_intent` and `quality_gate`, and registers it with `ModelRegistry`. Save it with `save_pretrained` in the version folder instead of joblib, and teach `ModelRegistry.load` to load either kind.
4. Compare both models on the Model tab.

**Done when:** a transformer version appears in `make models` with a model card; you can promote it and the API serves it; you've written up whether it beat TF-IDF on fraud recall and macro F1, and at what latency cost.

## 2. Drift monitoring

**Why:** Customer language changes (a new scam, a new product), and accuracy drops silently. Banks are expected to monitor deployed models.

**Where:** `bankq/monitoring/drift.py` (stub with the PSI function and report outline).

**Do:**
1. Implement `population_stability_index`.
2. Implement `drift_report(days)`: compare the recent category mix and confidence histogram with the training baseline, plus the share of words in recent tickets that the model's vocabulary has never seen.
3. Add `GET /api/v1/monitoring/drift` and a "Model health" card on the Analytics tab showing stable / watch / drifted.
4. Unit tests: identical distributions give PSI ≈ 0; a shifted distribution gives PSI > 0.25.

**Done when:** seeding only fraud tickets (write a small script) flips the status to "drifted".

## 3. Urgent-ticket notifications

**Why:** A fraud ticket has a 1-hour deadline; someone must be alerted, not just find it in a queue.

**Where:** `bankq/routing/notify.py`. `LogNotifier` is called today for every urgent ticket.

**Do:** Add a `SlackNotifier` (Slack incoming webhook) or an `EmailNotifier` (SMTP). Add settings to `bankq/config.py` (e.g. `BANKQ_SLACK_WEBHOOK_URL`), choose the notifier in `get_notifier()`, use a 3-second timeout, and never let a notification failure fail the API request. Message: ticket ref, team, deadline, masked text.

**Done when:** a test with a mocked HTTP client proves the webhook is called for urgent tickets only, and that a webhook error is logged but the classify request still returns 200.

## 4. Postgres and database migrations

**Why:** `Base.metadata.create_all` can't change existing tables. Real teams version their schema.

**Do:** Add Alembic (`alembic init migrations`), generate the initial migration from `bankq/db/models.py`, and replace `create_all` in `init_db` with "run migrations". Add a `postgres` service to `docker-compose.yml` and point `BANKQ_DATABASE_URL` at it (driver: `psycopg`).

**Done when:** `docker compose up` starts Postgres and the API, the migration runs automatically, and the test suite still passes on SQLite.

## 5. Load test and performance report

**Do:** Write `scripts/locustfile.py` hitting `/api/v1/classify` with real test-set sentences. Find the requests per second at which p95 latency passes 200 ms with 1, 2 and 4 uvicorn workers. Use `/metrics` to check where the time goes (`bankq_http_request_seconds`).

**Done when:** a short `docs/PERFORMANCE.md` with a table and one recommendation (e.g. skip explanations under load).

## 6. Project report notebook

**Do:** `notebooks/report.ipynb` covering: dataset and category mapping, class imbalance, preprocessing choices, model comparison (from the model card), error analysis of `models/registry/<version>/misclassified.csv` (which intents get confused and why), the fraud rule's effect, and limitations. This is your write-up for evaluation.

**Done when:** it runs top to bottom from a fresh clone after `make train`.
