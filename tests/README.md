# Fidelity PlanAlign Engine Testing Guide

**Test Suite**: 19 test files | 8,450 lines | 45+ test cases
**Framework**: pytest 7.4.0 | Coverage: pytest-cov 4.1.0

This comprehensive testing framework validates all aspects of the Fidelity PlanAlign Engine platform, from event sourcing to optimization and multi-year simulation.

## Quick Start

The focused edge-configuration matrix is available with:

```bash
pytest -m edge_config_matrix -v
```

```bash
# Run all tests
python -m pytest

# Fast unit tests only (<30 seconds)
python -m pytest -m unit

# Integration tests only (<2 minutes)
python -m pytest -m integration

# Specific test file
python -m pytest tests/unit/events/test_simulation_event.py

# With coverage report
python -m pytest --cov=planalign_orchestrator --cov-report=html

# Using Make targets (recommended)
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-coverage      # Tests with coverage report
```

## Test Organization

```
tests/
├── unit/                      # Fast, isolated unit tests (<1s each)
│   ├── events/               # Event model validation (S072)
│   │   ├── test_simulation_event.py
│   │   ├── test_dc_plan_events.py
│   │   └── test_plan_administration_events.py
│   ├── orchestrator/         # Pipeline orchestration
│   │   ├── test_pipeline.py
│   │   ├── test_registries.py
│   │   ├── test_config.py
│   │   └── test_reports.py
│   └── cli/                  # CLI interface
│       └── test_cli.py
├── integration/              # Integration tests (1-10s each)
│   ├── test_dbt_integration.py
│   ├── test_hybrid_pipeline.py
│   └── test_end_to_end_workflow.py
├── performance/              # Performance benchmarks (10-60s each)
│   ├── test_threading_benchmarks.py
│   ├── test_resource_validation.py
│   └── test_threading_comprehensive.py
├── stress/                   # Stress tests (>60s each)
│   └── test_threading_stress.py
├── fixtures/                  # Centralized fixture library
│   ├── config.py             # Test configurations
│   ├── database.py           # In-memory and populated databases
│   ├── mock_dbt.py           # Mock dbt runners
│   └── workforce_data.py     # Sample employees and events
└── utils/                    # Shared test utilities
    ├── __init__.py
    └── json_validators.py    # JSON schema validation
```

## Test Markers

Use markers for selective test execution:

| Marker | Description | Target Time | Usage |
|--------|-------------|-------------|-------|
| `unit` | Fast unit tests | <30s total | `pytest -m unit` |
| `integration` | Cross-component tests | <2min total | `pytest -m integration` |
| `performance` | Performance benchmarks | <5min total | `pytest -m performance` |
| `slow` | Long-running tests | >1s per test | `pytest -m "not slow"` |
| `database` | Requires database | Varies | `pytest -m database` |
| `edge_case` | Edge case tests | Varies | `pytest -m edge_case` |
| `error_handling` | Error handling tests | Varies | `pytest -m error_handling` |
| `e2e` | End-to-end workflow tests | Varies | `pytest -m e2e` |

## Test Categories Detailed

### 1. Unit Tests

**Purpose**: Validate individual components in isolation.

**Components Tested**:
- Event models (S072): `SimulationEvent`, DC plan events, plan administration events
- Orchestrator: `PipelineOrchestrator`, registries, configuration management
- CLI interface: `planwise` command-line tool

**Key Test Scenarios**:
```python
import pytest
from config.events import WorkforceEventFactory
from decimal import Decimal
from datetime import date


@pytest.mark.unit
def test_hire_event_creation():
    """Test hire event creation with valid payload."""
    event = WorkforceEventFactory.create_hire_event(
        employee_id="EMP_001",
        scenario_id="test",
        plan_design_id="default",
        hire_date=date(2025, 1, 15),
        department="Engineering",
        job_level=3,
        annual_compensation=Decimal("75000.00"),
    )

    assert event.event_type == "HIRE"
    assert event.employee_id == "EMP_001"
```

### 2. Integration Tests

**Purpose**: Validate complete workflows across components.

**Workflows Tested**:
- dbt model integration
- Hybrid pipeline execution (E068G)
- End-to-end workforce simulation

**Key Integration Scenarios**:
```python
import pytest
from tests.fixtures.config import minimal_config
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator


@pytest.mark.integration
@pytest.mark.database
def test_multi_year_simulation(minimal_config):
    """Test multi-year simulation completes successfully."""
    orchestrator = PipelineOrchestrator(minimal_config)
    summary = orchestrator.execute_multi_year_simulation(2025, 2026)

    # Verify results
    assert summary.success
    assert len(summary.completed_years) == 2
```

### 3. Performance Tests

**Purpose**: Validate system performance characteristics and scalability.

**Performance Areas**:
- Threading performance (E068C)
- Resource utilization validation
- Event generation throughput
- Memory usage patterns
- Database query performance

**Benchmarks**:
```python
PERFORMANCE_BENCHMARKS = {
    "parameter_validation": {"max_time": 0.1, "max_memory": 10.0},
    "event_creation": {"max_time": 0.01, "max_memory": 5.0},
    "optimization_execution": {"max_time": 5.0, "max_memory": 100.0},
    "simulation_single_year": {"max_time": 30.0, "max_memory": 200.0},
}
```

## Writing Tests

### Unit Test Example

```python
import pytest
from tests.fixtures.config import minimal_config


@pytest.mark.unit
def test_simulation_config(minimal_config):
    """Test simulation config loads correctly."""
    assert minimal_config is not None
    assert minimal_config.scenario_id is not None
```

### Integration Test Example

```python
import pytest
from tests.fixtures.config import minimal_config
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator


@pytest.mark.integration
@pytest.mark.database
def test_multi_year_simulation(minimal_config):
    """Test multi-year simulation completes successfully."""
    orchestrator = PipelineOrchestrator(minimal_config)
    summary = orchestrator.execute_multi_year_simulation(2025, 2026)

    # Verify results
    assert summary.success
    assert len(summary.completed_years) == 2
```

### Performance Test Example

```python
import pytest


@pytest.mark.performance
@pytest.mark.slow
def test_event_generation_performance():
    """Benchmark event generation performance."""
    import time
    start = time.perf_counter()

    # Generate events using the event factory
    from config.events import WorkforceEventFactory
    from decimal import Decimal
    from datetime import date

    for i in range(1000):
        WorkforceEventFactory.create_hire_event(
            employee_id=f"EMP_{i:04d}",
            scenario_id="perf_test",
            plan_design_id="default",
            hire_date=date(2025, 1, 15),
            department="Engineering",
            job_level=3,
            annual_compensation=Decimal("75000.00"),
        )

    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Event generation took {elapsed:.2f}s, expected <5s"
```

## Test Utilities

### Fixtures

Located in `tests/fixtures/`:

- `tests/fixtures/config.py`: Test configurations (`minimal_config`, `single_threaded_config`, etc.)
- `tests/fixtures/database.py`: In-memory and populated database fixtures
- `tests/fixtures/mock_dbt.py`: Mock dbt runners
- `tests/fixtures/workforce_data.py`: Sample employees and events

### JSON Validators

Located in `tests/utils/json_validators.py`:

- JSON schema validation utilities for API response testing

## CI/CD Integration

### GitHub Actions

The `.github/workflows/ci.yml` workflow runs automatically on push to `main`/`develop`
and on pull requests to `main`, with `lint`, `test`, `multi-year-invariants`, and
`validate-models` jobs. See that file for the current steps.

### Pre-commit Hook

```bash
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-fast
        name: Run fast tests
        entry: pytest -m unit --maxfail=1
        language: system
        pass_filenames: false
```

## Coverage

```bash
# Generate HTML coverage report
python -m pytest --cov=planalign_orchestrator --cov=planalign_cli --cov=config \
  --cov-report=html --cov-report=term

# View report
open htmlcov/index.html

# Using Make target
make test-coverage
```

**Target Coverage**:
- `planalign_orchestrator/`: 95%
- `planalign_cli/`: 90%
- `config/`: 90%

## Troubleshooting

### Tests not discovered

```bash
# Verify pytest can find tests
python -m pytest --collect-only

# Check for import errors
python -m pytest --collect-only -v
```

### Database lock errors

```bash
# Close all database connections
# In VS Code: Close database explorer tabs
# In DBeaver: Disconnect all sessions

# Run tests with isolated database
python -m pytest --database-isolation
```

### Slow test performance

```bash
# Identify slow tests
python -m pytest --durations=10

# Run with parallel execution
python -m pytest -n auto
```

## Performance Expectations

| Test Category | Count | Target Time | Actual |
|--------------|-------|-------------|--------|
| Unit Tests | 87 | <30s | **28.6s** ✓ |
| Integration Tests | 23 | <2min | **1.6s** ✓ |
| Performance Tests | 13 | <5min | **9.1s** ✓ |
| Full Suite | 185 | <5min | **~40s** ✓ |

**Test Status** (as of October 7, 2025):
- **Total Tests Collected**: 185 tests
- **Unit Tests**: 79 passing, 8 failing (91% pass rate)
- **Integration Tests**: 17 passing, 6 failing (74% pass rate)
- **Performance Tests**: 2 passing, 11 failing (15% pass rate - needs refactoring)
- **Collection Errors**: 2 tests (outdated imports for legacy modules)

**Notes**:
- Unit tests meet performance target (<30s)
- Integration tests significantly exceed target (1.6s vs 2min target)
- Some tests require updates for refactored orchestrator architecture
- Test infrastructure is fully functional and ready for development

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [PlanWise Architecture](../docs/architecture/)
- [Event Sourcing Guide](../docs/guides/event-sourcing.md)
