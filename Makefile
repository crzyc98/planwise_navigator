# filename: Makefile
.PHONY: help dev-setup install test lint format clean run-simulation run-dashboard docker-build

PYTHON := python3.11
VENV := venv
DBT_DIR := dbt
DAGSTER_HOME := $(shell pwd)/.dagster

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev-setup: install ## Complete development environment setup
	@echo "Setting up PlanWise Navigator development environment..."
	mkdir -p $(DAGSTER_HOME) data logs tmp
	cd $(DBT_DIR) && dbt deps
	cd $(DBT_DIR) && dbt seed
	@echo "Development environment ready!"

install: ## Install Python dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install -r requirements-dev.txt
	$(VENV)/bin/pre-commit install

test: ## Run all tests
	$(VENV)/bin/pytest tests/ -v --cov=planwise_navigator --cov-report=html
	cd $(DBT_DIR) && $(VENV)/bin/dbt test

lint: ## Run linting checks
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .
	$(VENV)/bin/mypy planwise_navigator/

format: ## Format code
	$(VENV)/bin/black .
	$(VENV)/bin/ruff check --fix .

clean: ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov .pytest_cache
	rm -rf $(DBT_DIR)/target $(DBT_DIR)/logs
	rm -rf $(DAGSTER_HOME)/storage

run-simulation: ## Run workforce simulation
	mkdir -p $(DAGSTER_HOME)
	@echo "DAGSTER_HOME set to: $(DAGSTER_HOME)"
	PYTHONPATH=$(shell pwd)/$(VENV)/lib/$(PYTHON)/site-packages:$(PYTHONPATH) \
	DAGSTER_HOME="$(DAGSTER_HOME)" \
	$(VENV)/bin/dagster dev -f definitions.py

run-dashboard: ## Launch Streamlit dashboard
	$(VENV)/bin/streamlit run streamlit_dashboard/app.py --server.port 8501

docker-build: ## Build Docker image
	docker build -t planwise-navigator:latest .

db-reset: ## Reset DuckDB database
	rm -f data/planwise.duckdb
	cd $(DBT_DIR) && $(VENV)/bin/dbt seed

benchmark: ## Run performance benchmarks
	$(VENV)/bin/python tests/perf/benchmark_runtime.py

generate-data: ## Generate synthetic test data
	$(VENV)/bin/python tests/utils/generate_fake_census.py --employees 10000
