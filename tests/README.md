# PlanWise Navigator Testing Guide

**Test Suite**: 19 test files | 8,450 lines | 45+ test cases
**Framework**: pytest 7.4.0 | Coverage: pytest-cov 4.1.0

This comprehensive testing framework validates all aspects of the PlanWise Navigator platform, from event sourcing to optimization and multi-year simulation.

## Quick Start

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
python -m pytest --cov=navigator_orchestrator --cov-report=html

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
│   ├── test_multi_year_coordination.py
│   ├── test_dbt_integration.py
│   ├── test_hybrid_pipeline.py
│   └── test_end_to_end_workflow.py
├── performance/              # Performance benchmarks (10-60s each)
│   ├── test_threading_benchmarks.py
│   ├── test_resource_validation.py
│   └── test_threading_comprehensive.py
├── stress/                   # Stress tests (>60s each)
│   └── test_threading_stress.py
└── utils/                    # Shared test utilities
    ├── __init__.py
    ├── fixtures.py           # Shared fixtures
    ├── factories.py          # Test data factories
    └── assertions.py         # Custom assertions
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
- Utilities: parameter validation, data factories, custom assertions

**Key Test Scenarios**:
```python
import pytest
from tests.utils import EventFactory, assert_event_valid


@pytest.mark.unit
def test_hire_event_creation():
    """Test hire event creation with valid payload."""
    event = EventFactory.create_hire(
        employee_id="EMP_001",
        job_level=3,
        starting_salary=75000.0
    )

    assert_event_valid(event)
    assert event.event_type == "hire"
    assert event.payload.job_level == 3
    assert event.payload.starting_salary == 75000.0
```

### 2. Integration Tests

**Purpose**: Validate complete workflows across components.

**Workflows Tested**:
- Multi-year simulation coordination
- dbt model integration
- Hybrid pipeline execution (E068G)
- End-to-end workforce simulation

**Key Integration Scenarios**:
```python
import pytest
from tests.utils import test_database, ConfigFactory


@pytest.mark.integration
@pytest.mark.database
def test_multi_year_simulation(test_database):
    """Test multi-year simulation completes successfully."""
    config = ConfigFactory.create_simulation_config(
        start_year=2025,
        end_year=2026,
    )

    # Run simulation
    orchestrator = create_orchestrator(config)
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
from tests.utils import EventFactory, assert_event_valid


@pytest.mark.unit
def test_hire_event_creation():
    """Test hire event creation with valid payload."""
    event = EventFactory.create_hire(
        employee_id="EMP_001",
        job_level=3,
        starting_salary=75000.0
    )

    assert_event_valid(event)
    assert event.event_type == "hire"
    assert event.payload.job_level == 3
    assert event.payload.starting_salary == 75000.0
```

### Integration Test Example

```python
import pytest
from tests.utils import test_database, ConfigFactory


@pytest.mark.integration
@pytest.mark.database
def test_multi_year_simulation(test_database):
    """Test multi-year simulation completes successfully."""
    config = ConfigFactory.create_simulation_config(
        start_year=2025,
        end_year=2026,
    )

    # Run simulation
    orchestrator = create_orchestrator(config)
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
def test_event_generation_performance(performance_tracker, benchmark_baseline):
    """Benchmark event generation performance."""
    performance_tracker.start()

    # Generate 10,000 events
    events = [EventFactory.create_hire() for _ in range(10_000)]

    metrics = performance_tracker.stop()
    performance_tracker.assert_performance(
        max_time=benchmark_baseline["event_creation"]["max_time"] * 10_000,
        max_memory=benchmark_baseline["event_creation"]["max_memory"]
    )
```

## Test Utilities

### Fixtures

Located in `tests/utils/fixtures.py`:

- `test_database`: Isolated test database with backup/restore
- `temp_directory`: Temporary directory for test files
- `sample_workforce_data`: 1000-row workforce DataFrame
- `performance_tracker`: Performance monitoring utility
- `benchmark_baseline`: Performance baseline expectations

### Factories

Located in `tests/utils/factories.py`:

- `EventFactory`: Create test simulation events
- `WorkforceFactory`: Create test employee records
- `ConfigFactory`: Create test configurations

### Custom Assertions

Located in `tests/utils/assertions.py`:

- `assert_parameter_validity()`: Validate parameters
- `assert_optimization_convergence()`: Check optimization results
- `assert_performance_acceptable()`: Verify performance metrics
- `assert_event_valid()`: Validate event structure

## CI/CD Integration

### GitHub Actions

The `.github/workflows/tests.yml` workflow runs automatically on push and pull requests:

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest -m "not slow" --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

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
python -m pytest --cov=navigator_orchestrator --cov=planwise_cli --cov=config \
  --cov-report=html --cov-report=term

# View report
open htmlcov/index.html

# Using Make target
make test-coverage
```

**Target Coverage**:
- `navigator_orchestrator/`: 95%
- `planwise_cli/`: 90%
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
