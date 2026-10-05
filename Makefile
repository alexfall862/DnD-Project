# Developer commands (docs/architecture/05-implementation-plan.md §22, docs/testing/testing-strategy.md §24).
# Requires: uv, docker compose, GNU make. Run from the repo root.

SHELL := /bin/bash
BACKEND := backend
UV := uv --directory $(BACKEND)
RUN := $(UV) run

.PHONY: help setup dev api web web-install web-build web-test e2e worker db-up db-down db-logs migrate migrate-new reset-db \
        test test-unit test-integration test-invariants test-leakage test-rules test-replay \
        test-latency test-stress eval-local seed-demo play lint format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend deps into backend/.venv and copy .env.example if .env is missing
	$(UV) sync --all-groups
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

db-up: ## Start PostgreSQL+pgvector and wait for it to be healthy
	docker compose up -d db
	@until docker compose exec -T db pg_isready -U ttrpg -d ttrpg >/dev/null 2>&1; do sleep 1; done; echo "db ready"

db-down: ## Stop the database container (data volume kept)
	docker compose down

db-logs: ## Tail database logs
	docker compose logs -f db

migrate: ## Apply migrations to DATABASE_URL
	$(RUN) alembic upgrade head

migrate-new: ## Create a new migration: make migrate-new m="0001_campaign_timeline_clock"
	$(RUN) alembic revision -m "$(m)"

reset-db: ## Drop and recreate the dev database, then migrate (the v0.1 "migration path" for dev campaigns)
	docker compose exec -T db psql -U ttrpg -d postgres -v ON_ERROR_STOP=1 \
		-c "DROP DATABASE IF EXISTS ttrpg WITH (FORCE);" -c "CREATE DATABASE ttrpg OWNER ttrpg;"
	$(MAKE) migrate

api: ## Run the FastAPI backend with reload
	$(RUN) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev: db-up migrate api ## Start db, migrate, run api

web: ## Browser client dev server (proxies /api to :8000; open on a phone via the LAN/tailnet address)
	cd frontend && npm run dev

web-install: ## Install the browser client dependencies (and Playwright Chromium for e2e)
	cd frontend && npm install && npx playwright install chromium

web-build: ## Build the browser client into frontend/dist (then `make api` serves it on :8000)
	cd frontend && npm run build

web-test: ## Browser client unit tests (Vitest) and typecheck
	cd frontend && npm run typecheck && npm test

e2e: ## Browser end-to-end tests: real UI + API, scripted FakeModel, test database (needs db-up)
	cd frontend && npx playwright test

worker: ## Background worker (jobs: embeddings, memory processing, journals, simulation): make worker ARGS="--once"
	$(RUN) python -m app.worker $(ARGS)

test: ## Run the full backend suite (needs db-up)
	$(RUN) pytest

test-unit: ## Deterministic tests, no database
	$(RUN) pytest -m unit

test-integration: ## Tests against the real ttrpg_test database
	$(RUN) pytest -m integration

test-invariants: ## Architectural invariant suite
	$(RUN) pytest -m invariants

test-leakage: ## Knowledge-leakage suite
	$(RUN) pytest -m leakage

test-rules: ## Rules-engine / ruleset fixtures
	$(RUN) pytest -m rules

test-replay: ## Deterministic replay suite
	$(RUN) pytest -m replay

test-latency: ## Budget/degradation tests with FakeModel delays
	$(RUN) pytest -m latency

test-stress: ## Long-run synthetic campaign (slow)
	$(RUN) pytest -m stress

eval-local: ## Optional real-model evaluation suite (needs A9_TOKEN)
	$(RUN) pytest -m eval --eval

seed-demo: ## Seed the full Frostbridge campaign offline and print its id map: make seed-demo ARGS="--fixture tavern --quiet"
	$(RUN) python -m app.cli.seed $(ARGS)

play: ## Terminal play harness against the running API: make play ARGS="--new" or ARGS="--campaign <id>"
	$(RUN) python -m app.cli.play $(ARGS)

lint: ## Ruff check
	$(RUN) ruff check .

format: ## Ruff format
	$(RUN) ruff format .
