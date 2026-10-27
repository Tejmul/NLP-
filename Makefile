.PHONY: install train retrain promote models serve dev seed test lint docker-build docker-up clean

PY ?= .venv/bin/python
PORT ?= 8077

install:          ## create the virtualenv and install everything
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

train:            ## train, evaluate and register a model (promotes if the quality gate passes)
	$(PY) -m bankq.ml.train

retrain:          ## retrain including agent corrections from the ticket database
	$(PY) -m bankq.ml.train --include-feedback

models:           ## list model versions
	$(PY) -m bankq.ml.registry list

promote:          ## make a version the production model: make promote V=v2026...
	$(PY) -m bankq.ml.registry promote $(V)

serve:            ## run the API and web UI
	$(PY) -m uvicorn bankq.api.app:app --host 127.0.0.1 --port $(PORT)

dev:              ## run with auto-reload and readable logs
	BANKQ_LOG_JSON=false $(PY) -m uvicorn bankq.api.app:app --reload --port $(PORT)

seed:             ## fill the database with 14 days of demo tickets
	BANKQ_LOG_JSON=false $(PY) -m scripts.seed_demo --reset

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check bankq tests scripts

docker-build:
	docker build -t bankq:latest .

docker-up:
	docker compose up --build

clean:
	rm -rf data/processed .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
