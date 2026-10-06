# ChurnPulse - common commands.  Run `make help` to list them.
SHELL := /bin/bash
UV ?= $(HOME)/.local/bin/uv
PY := .venv/bin/python
export PYTHONWARNINGS := ignore
export MLFLOW_DISABLE_AGENT_HINT := 1

.DEFAULT_GOAL := help
.PHONY: help setup data train notebooks build up down reset logs status demo test test-e2e lint screenshots frontend-dev api-dev

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Create the Python env, install frontend packages, write .env
	@command -v $(UV) >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
	$(UV) python install 3.12
	$(UV) venv --python 3.12 .venv
	$(UV) pip install -p .venv -e ".[ml,serving,dev]" -r requirements/serving.txt
	cd frontend && npm install
	@test -f .env || (sed "s#/absolute/path/to/ChurnPulse#$(CURDIR)#" .env.example > .env && echo "wrote .env")

data: ## Download IBM Telco v11 (checksum-verified) and build data/processed/customers.csv
	$(PY) -m churnpulse.dataset

train: ## Train both models: compare, tune, calibrate, export (+ MLflow registry)
	$(PY) -m churnpulse.train --trials 30

notebooks: ## Regenerate and execute the four notebooks
	$(PY) notebooks/build_notebooks.py
	for n in 01_eda 02_features 03_modeling 04_explainability; do \
	  .venv/bin/jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=900 notebooks/$$n.ipynb; done

build: ## Build the Docker images
	docker buildx bake --allow=network.host -f docker-compose.yml --load
	docker compose pull --ignore-buildable --quiet

up: ## Start the whole platform
	docker compose up -d
	@echo ""
	@echo "  Dashboard   http://localhost:3000"
	@echo "  API docs    http://localhost:8000/api/docs"
	@echo "  Kafka UI    http://localhost:8080"
	@echo "  Flink       http://localhost:8081"
	@echo "  Grafana     http://localhost:3001   (admin / churnpulse)"
	@echo "  MLflow      http://localhost:5000"
	@echo "  Prometheus  http://localhost:9090"

down: ## Stop the platform (keeps data)
	docker compose down

reset: ## Stop and delete all data (Kafka, Postgres, Flink state)
	docker compose down -v --remove-orphans

logs: ## Follow logs of the streaming services
	docker compose logs -f --tail 50 flink-taskmanager api simulator

status: ## Show services and the Flink job
	docker compose ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}"
	@curl -s localhost:8081/jobs/overview | python3 -c "import json,sys; [print('flink job:', j['name'], j['state']) for j in json.load(sys.stdin)['jobs']]" 2>/dev/null || true

demo: ## Push a loyal customer through churn signals and show the result
	@CID=$$(curl -s "localhost:8000/api/customers?band=low&limit=200&offset=4000" | python3 -c "import json,sys; print(next(c['customer_id'] for c in json.load(sys.stdin)['items'] if c['contract']=='Two Year'))"); \
	echo "customer $$CID"; \
	curl -s localhost:8000/api/customers/$$CID | python3 -c "import json,sys; d=json.load(sys.stdin); print('  before:', round(d['probability'],3), d['risk_band'])"; \
	curl -s -X POST localhost:8000/api/customers/$$CID/scenario/churn_risk >/dev/null; sleep 3; \
	curl -s localhost:8000/api/customers/$$CID | python3 -c "import json,sys; d=json.load(sys.stdin); print('  after: ', round(d['probability'],3), d['risk_band'], '| top reason:', d['reasons'][0]['feature'])"; \
	echo "  open http://localhost:3000/customers/$$CID"

test: ## Unit tests (no Docker needed)
	$(PY) -m pytest -m "not e2e"

test-e2e: ## End-to-end tests against the running stack
	$(PY) -m pytest -m e2e -v

lint: ## Lint Python code
	.venv/bin/ruff check src api streaming tests scripts notebooks/build_notebooks.py

screenshots: ## Refresh README screenshots (stack must be running)
	$(PY) scripts/screenshots.py

frontend-dev: ## Run the dashboard with hot reload on :5173
	cd frontend && npm run dev

api-dev: ## Run the API locally with reload (needs Kafka + Postgres up)
	$(PY) -m uvicorn api.app.main:app --reload --port 8000
