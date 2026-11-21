# Day-to-day commands. `make` alone lists them.
#
# fix/lint/typecheck/clean run on your machine (pip install -r backend/requirements-dev.txt
# and npm ci in frontend/ first). test/migrate/seed run inside the compose stack, because
# the backend suite needs Postgres — exactly as README.md's quick start describes.

BACKEND  := backend
FRONTEND := frontend
PY_PATHS := app tests migrations
COMPOSE  := docker compose

.DEFAULT_GOAL := help
.PHONY: help clean clean-all fix lint typecheck check up down migrate seed test test-backend \
        test-domain test-frontend test-scripts e2e smoke infra-fmt infra-validate

help: ## List targets
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

clean: ## Delete caches and build output (keeps .env and node_modules)
	find $(BACKEND) scripts -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf scripts/.pytest_cache scripts/.mypy_cache scripts/.ruff_cache
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
	       $(BACKEND)/.hypothesis $(BACKEND)/.coverage $(BACKEND)/coverage.xml $(BACKEND)/htmlcov
	rm -rf $(FRONTEND)/dist $(FRONTEND)/coverage $(FRONTEND)/playwright-report \
	       $(FRONTEND)/test-results $(FRONTEND)/*.tsbuildinfo

clean-all: clean ## clean, plus node_modules
	rm -rf $(FRONTEND)/node_modules

fix: ## Auto-fix lint and formatting
	cd $(BACKEND) && ruff check --fix $(PY_PATHS) && ruff format $(PY_PATHS)
	cd $(FRONTEND) && npm run lint -- --fix

lint: ## Lint and format check, as CI runs it
	@if grep -rn "float(" $(BACKEND)/app/domain; then echo "float() in app/domain — see ADR-001"; exit 1; fi
	cd $(BACKEND) && ruff check $(PY_PATHS) && ruff format --check $(PY_PATHS)
	cd $(FRONTEND) && npm run lint

typecheck: ## mypy and tsc
	cd $(BACKEND) && mypy app --ignore-missing-imports
	cd $(FRONTEND) && npm run typecheck

check: lint typecheck ## Everything CI checks that needs no database

up: ## Start the dev stack
	$(COMPOSE) up -d

down: ## Stop the dev stack
	$(COMPOSE) down

migrate: ## Apply migrations in the dev stack
	$(COMPOSE) exec backend alembic upgrade head

seed: ## Create the demo user
	$(COMPOSE) exec backend flask --app wsgi seed demo

test: test-backend test-frontend ## All unit and integration tests

test-backend: ## Backend suite against the compose Postgres
	$(COMPOSE) exec backend pytest

test-domain: ## Financial engines only, fast
	$(COMPOSE) exec backend pytest tests/domain -q

test-frontend: ## Vitest, single run
	$(COMPOSE) run --rm frontend npm test -- --run

test-scripts: ## Deploy tooling against mocked AWS (pip install -r scripts/requirements-dev.txt)
	cd scripts && pytest -q && mypy --strict aws_deploy.py smoke_test.py

e2e: ## Playwright against the running dev stack (run `make seed` first)
	$(COMPOSE) run --rm playwright

smoke: ## Smoke-test a deployment: make smoke URL=https://staging.example.com
	python3 scripts/smoke_test.py $(URL)

infra-fmt: ## Format Terraform
	terraform -chdir=infrastructure/terraform fmt -recursive

infra-validate: ## Validate every Terraform stack (no AWS access needed)
	@for stack in bootstrap global envs/staging envs/production; do \
		echo "== $$stack"; \
		terraform -chdir=infrastructure/terraform/$$stack init -backend=false -input=false >/dev/null && \
		terraform -chdir=infrastructure/terraform/$$stack validate || exit 1; \
	done
