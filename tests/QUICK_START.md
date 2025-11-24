# Testing Quick Start Guide

## TL;DR - Fast Test Workflow

```bash
# Run fast tests (4.7s for 87 tests) - USE THIS FOR TDD
pytest -m fast

# Run all tests (2 minutes for 256 tests)
pytest tests/

# Run with coverage
pytest tests/unit/events/ --cov=config.events --cov-report=term
```

---

## Most Common Commands

### Developer Workflow (TDD)

```bash
# Fast feedback loop - run after every code change
pytest -m fast --tb=short

# Watch mode (requires pytest-watch)
pytest -m fast --watch

# Specific component
pytest -m "fast and orchestrator"
pytest -m "fast and events"
pytest -m "fast and config"
```

### CI/CD Workflow

```bash
# Stage 1: Fast tests (15s)
pytest -m fast

# Stage 2: Integration tests (45s)
pytest -m "slow and not very_slow"

# Stage 3: E2E tests (60s)
pytest -m very_slow

# Full suite with coverage
pytest --cov=planalign_orchestrator --cov-report=html
```

---

## Using Fixtures

```python
# Import from centralized library
from tests.fixtures import (
    in_memory_db,              # Clean database
    populated_test_db,         # 100 employees + 50 events
    minimal_config,            # Valid configuration
    mock_dbt_runner,           # Mock dbt execution
    sample_employees,          # 100 employee dicts
)

# Use in tests
@pytest.mark.fast
@pytest.mark.unit
def test_my_feature(in_memory_db, sample_employees):
    # Your test here
    pass
```

---

## Test Markers

```python
# Speed markers
@pytest.mark.fast           # <1s execution
@pytest.mark.slow           # 1-10s execution
@pytest.mark.very_slow      # 10s+ execution

# Type markers (auto-applied by directory)
@pytest.mark.unit           # Pure unit test
@pytest.mark.integration    # Integration test
@pytest.mark.e2e            # End-to-end test

# Feature markers
@pytest.mark.orchestrator   # Orchestrator component
@pytest.mark.events         # Event schema
@pytest.mark.dbt            # dbt integration
@pytest.mark.cli            # CLI commands
```

---

## Coverage Reporting

```bash
# HTML report (open in browser)
pytest --cov=planalign_orchestrator --cov-report=html
open htmlcov/index.html

# Terminal report with missing lines
pytest tests/unit/events/ --cov=config.events --cov-report=term-missing

# Current coverage: config.events = 92.91%
```

---

## Troubleshooting

### Database Locked Error

```bash
# Close IDE database connections
lsof | grep simulation.duckdb
# Then re-run tests
```

### Import Errors

```python
# CORRECT import
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator

# WRONG import (old path)
from planalign_orchestrator.pipeline import PipelineOrchestrator
```

### Slow Tests

```python
# SLOW - File database
def test_query():
    conn = duckdb.connect("dbt/simulation.duckdb")

# FAST - In-memory database
@pytest.mark.fast
def test_query(in_memory_db):
    result = in_memory_db.execute("SELECT ...").fetchall()
```

---

## Full Documentation

See `tests/TEST_INFRASTRUCTURE.md` for complete guide (501 lines)
