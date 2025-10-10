# PlanWise Navigator Testing Infrastructure

Enterprise-grade testing framework with **90%+ coverage target** and **fast test suite** for optimal developer productivity.

---

## Quick Start

### Run Fast Unit Tests (Developer Workflow)

```bash
# All fast tests - optimal for TDD workflow
pytest -m fast                          # ~10-15 seconds for 87 tests

# Specific component tests
pytest -m "fast and orchestrator"       # Orchestrator unit tests
pytest -m "fast and events"             # Event schema tests
pytest -m "fast and config"             # Configuration tests

# Single test file for targeted debugging
pytest tests/unit/events/test_simulation_event.py -v
```

### Run Full Test Suite (CI Workflow)

```bash
# Tiered execution strategy
pytest -m fast                          # Stage 1: Fast tests (~15s)
pytest -m "slow and not very_slow"      # Stage 2: Integration (~30s)
pytest -m very_slow                     # Stage 3: E2E tests (~60s)

# Full suite
pytest tests/                           # All 256 tests (~2 minutes)

# With coverage reporting
pytest --cov=navigator_orchestrator --cov=planwise_cli --cov=config \
       --cov-report=html --cov-report=term
```

---

## Test Organization

### Directory Structure

```
tests/
├─ unit/                    # Pure unit tests (no I/O, <1s each) - 87 tests
│  ├─ config/              # Configuration validation
│  ├─ events/              # Event schema validation (Pydantic v2)
│  ├─ orchestrator/        # Orchestrator unit tests
│  └─ cli/                 # CLI command tests
│
├─ integration/             # Integration tests (database, dbt, 1-10s) - ~120 tests
│  ├─ test_multi_year_coordination.py
│  ├─ test_hybrid_pipeline.py
│  ├─ test_dbt_integration.py
│  └─ test_orchestrator_dbt_end_to_end.py
│
├─ performance/             # Performance benchmarks (~50 tests)
│  └─ test_threading_comprehensive.py
│
├─ stress/                  # Stress tests
│
├─ fixtures/                # Shared fixture library (NEW in E075)
│  ├─ __init__.py          # Centralized exports
│  ├─ database.py          # In-memory database fixtures
│  ├─ config.py            # Configuration fixtures
│  ├─ mock_dbt.py          # dbt mocking utilities
│  └─ workforce_data.py    # Test data generators
│
├─ utils/                   # Test utilities
│  ├─ factories.py         # Test data factories
│  ├─ assertions.py        # Custom assertions
│  └─ fixtures.py          # Legacy fixtures (being migrated)
│
├─ conftest.py             # Test configuration (markers, auto-marking)
└─ TEST_INFRASTRUCTURE.md  # This document
```

### Test Markers

**Execution Speed Markers:**
- `@pytest.mark.fast` - Fast unit tests (<1s each) - **87 tests**
- `@pytest.mark.slow` - Slow integration tests (1-10s each)
- `@pytest.mark.very_slow` - E2E tests (10s+ each)

**Test Type Markers:**
- `@pytest.mark.unit` - Pure unit tests (no I/O)
- `@pytest.mark.integration` - Integration tests (database, dbt)
- `@pytest.mark.e2e` - End-to-end workflow tests

**Feature Area Markers:**
- `@pytest.mark.orchestrator` - Orchestrator component tests
- `@pytest.mark.events` - Event schema tests
- `@pytest.mark.dbt` - dbt integration tests
- `@pytest.mark.cli` - CLI command tests
- `@pytest.mark.threading` - Multi-threading tests
- `@pytest.mark.config` - Configuration validation tests

**Quality Markers:**
- `@pytest.mark.smoke` - Critical path smoke tests
- `@pytest.mark.regression` - Regression test suite
- `@pytest.mark.performance` - Performance benchmarks
- `@pytest.mark.stress` - Stress tests

---

## Fixture Library

### Database Fixtures (`tests/fixtures/database.py`)

Fast in-memory fixtures for unit tests without disk I/O:

```python
from tests.fixtures import in_memory_db, populated_test_db

@pytest.mark.fast
@pytest.mark.unit
def test_query_performance(in_memory_db):
    """Test using in-memory database."""
    result = in_memory_db.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
    assert result[0] == 0  # Clean database

@pytest.mark.fast
@pytest.mark.unit
def test_with_sample_data(populated_test_db):
    """Test with pre-populated sample data."""
    # Database has 100 employees and 50 events
    result = populated_test_db.execute(
        "SELECT COUNT(*) FROM fct_workforce_snapshot"
    ).fetchone()
    assert result[0] == 100
```

**Available Fixtures:**
- `in_memory_db`: Clean in-memory DuckDB database with schema
- `populated_test_db`: In-memory database with 100 employees + 50 events
- `isolated_test_db`: File-based database with automatic cleanup

### Configuration Fixtures (`tests/fixtures/config.py`)

Pre-configured simulation settings:

```python
from tests.fixtures import minimal_config, single_threaded_config

@pytest.mark.fast
@pytest.mark.unit
def test_pipeline_initialization(minimal_config):
    """Test with minimal valid configuration."""
    assert minimal_config.simulation.start_year == 2025
    assert minimal_config.simulation.end_year == 2026
    assert minimal_config.scenario_id == "test_scenario"

@pytest.mark.integration
def test_sequential_execution(single_threaded_config):
    """Test with single-threaded optimization."""
    orchestrator = PipelineOrchestrator(single_threaded_config)
    summary = orchestrator.run_single_year(2025)
    assert summary.success
```

**Available Fixtures:**
- `minimal_config`: Minimal valid configuration for unit tests
- `single_threaded_config`: Single-threaded optimization settings
- `multi_threaded_config`: 4-thread parallel execution settings

### Mock Fixtures (`tests/fixtures/mock_dbt.py`)

Mock dbt execution for fast unit tests:

```python
from tests.fixtures import mock_dbt_runner, failing_dbt_runner

@pytest.mark.fast
@pytest.mark.unit
def test_orchestrator_success(mock_dbt_runner):
    """Test orchestrator with mocked dbt execution."""
    orchestrator = PipelineOrchestrator(config, dbt_runner=mock_dbt_runner)
    orchestrator.run_single_year(2025)
    mock_dbt_runner.execute_command.assert_called()

@pytest.mark.fast
@pytest.mark.unit
def test_orchestrator_error_handling(failing_dbt_runner):
    """Test error handling with failing dbt."""
    orchestrator = PipelineOrchestrator(config, dbt_runner=failing_dbt_runner)
    with pytest.raises(RuntimeError):
        orchestrator.run_single_year(2025)
```

**Available Fixtures:**
- `mock_dbt_runner`: Successful dbt execution mock
- `failing_dbt_runner`: Failed dbt execution mock
- `mock_dbt_result`: Sample DbtResult object

### Workforce Data Fixtures (`tests/fixtures/workforce_data.py`)

Sample data generators:

```python
from tests.fixtures import sample_employees, baseline_workforce_df

@pytest.mark.fast
@pytest.mark.unit
def test_employee_processing(sample_employees):
    """Test with 100 sample employees."""
    assert len(sample_employees) == 100
    assert all('employee_id' in emp for emp in sample_employees)

@pytest.mark.fast
@pytest.mark.unit
def test_dataframe_operations(baseline_workforce_df):
    """Test pandas DataFrame operations."""
    assert len(baseline_workforce_df) == 100
    assert 'base_salary' in baseline_workforce_df.columns
```

**Available Fixtures:**
- `sample_employees`: List of 100 employee dictionaries
- `baseline_workforce_df`: pandas DataFrame with 100 employees
- `sample_yearly_events`: List of 50 simulation events

---

## Writing Tests

### Unit Test Template

```python
@pytest.mark.fast
@pytest.mark.unit
def test_function_name(in_memory_db):
    """Test description following PlanWise conventions."""
    # Arrange
    setup_data()

    # Act
    result = function_under_test()

    # Assert
    assert result == expected
```

### Integration Test Template

```python
@pytest.mark.slow
@pytest.mark.integration
def test_integration_scenario(populated_test_db, single_threaded_config):
    """Test multi-component integration."""
    # Arrange
    orchestrator = PipelineOrchestrator(single_threaded_config)

    # Act
    summary = orchestrator.run_single_year(2025)

    # Assert
    assert summary.success
    result = populated_test_db.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
    assert result[0] > 0
```

---

## Coverage Requirements

### Coverage Targets

| Module | Target | Command |
|--------|--------|---------|
| navigator_orchestrator.* | 90% | `pytest --cov=navigator_orchestrator` |
| planwise_cli.* | 85% | `pytest --cov=planwise_cli` |
| config.events | 95% | `pytest --cov=config.events` |

### Check Coverage

```bash
# Generate HTML report
pytest --cov=navigator_orchestrator --cov-report=html
open htmlcov/index.html

# Terminal report with missing lines
pytest --cov=navigator_orchestrator --cov-report=term-missing

# Coverage for specific module
pytest tests/unit/events/ --cov=config.events --cov-report=term
```

### Coverage Configuration

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["navigator_orchestrator", "planwise_cli", "config"]
omit = ["*/tests/*", "*/venv/*", "*/dbt/*", "*/streamlit_dashboard/*"]

[tool.coverage.report]
precision = 2
show_missing = true
exclude_lines = ["pragma: no cover", "def __repr__", "if TYPE_CHECKING:"]
```

---

## Performance Targets

### Current Test Performance (256 tests total)

- ✅ **Fast test suite**: 87 tests in ~15 seconds
- ✅ **Integration tests**: ~120 tests in ~45 seconds
- ✅ **Full test suite**: 256 tests in ~2 minutes
- ✅ **Test collection**: <0.2 seconds

### Test Execution Breakdown

```bash
# Fast tests only (optimal for TDD)
pytest -m fast                          # 87 tests, ~15s

# Integration tests
pytest -m "slow and not very_slow"      # ~120 tests, ~45s

# E2E and performance tests
pytest -m very_slow                     # ~49 tests, ~60s

# Full suite
pytest tests/                           # 256 tests, ~2 minutes
```

---

## Continuous Integration

### GitHub Actions Workflow

The CI pipeline runs tests in stages:

```yaml
jobs:
  test:
    steps:
      - name: Fast Tests
        run: pytest -m fast --cov=navigator_orchestrator

      - name: Integration Tests
        run: pytest -m "slow and not very_slow" --cov-append

      - name: E2E Tests
        run: pytest -m very_slow --cov-append

      - name: Coverage Report
        run: pytest --cov-report=xml --cov-report=term
```

### Pre-commit Hooks

Run fast tests before commit:

```bash
# .git/hooks/pre-commit
#!/bin/bash
pytest -m fast --tb=short || exit 1
```

---

## Troubleshooting

### Tests Fail with Database Lock

**Problem**: `Database locked: could not acquire lock`

**Solution**: Close all IDE connections to `dbt/simulation.duckdb`

```bash
# Check for open connections
lsof | grep simulation.duckdb

# Kill IDE database connections, then re-run tests
pytest tests/integration/test_dbt_integration.py
```

### Slow Test Execution

**Problem**: Fast tests take >15 seconds

**Solution**: Ensure tests use `in_memory_db` fixture, not file-based database

```python
# SLOW - File-based database
def test_query():
    conn = duckdb.connect("dbt/simulation.duckdb")
    result = conn.execute("SELECT * FROM fct_yearly_events").fetchall()

# FAST - In-memory database
@pytest.mark.fast
def test_query(in_memory_db):
    result = in_memory_db.execute("SELECT * FROM fct_yearly_events").fetchall()
```

### Import Errors

**Problem**: `ImportError: cannot import name 'PipelineOrchestrator'`

**Solution**: Use correct import path

```python
# CORRECT
from navigator_orchestrator.pipeline_orchestrator import PipelineOrchestrator

# INCORRECT (old path)
from navigator_orchestrator.pipeline import PipelineOrchestrator
```

### Test Collection Errors

**Problem**: pytest collection fails

**Solution**: Check for syntax errors and verify markers are registered

```bash
# Validate test collection
pytest --collect-only tests/

# List registered markers
pytest --markers
```

---

## Epic E075 Implementation Summary

### Completed Improvements

1. ✅ **Fixed import errors** - Corrected PipelineOrchestrator imports across all test files
2. ✅ **Created fixture library** - Centralized fixtures in `tests/fixtures/`
3. ✅ **Configured markers** - Added comprehensive marker system in `pyproject.toml`
4. ✅ **In-memory databases** - Fast unit test fixtures without disk I/O
5. ✅ **Coverage reporting** - pytest-cov integration with HTML/terminal reports
6. ✅ **Auto-marking** - Automatic marker application based on test location

### Test Count: **256 tests collected**

- **87 fast unit tests** (`pytest -m fast`)
- **~120 integration tests** (`pytest -m integration`)
- **~49 performance/stress tests** (`pytest -m "performance or stress"`)

### Performance Achievement

- **Fast test suite**: <15 seconds (87 tests)
- **Full test suite**: ~2 minutes (256 tests)
- **Test collection**: <0.2 seconds

---

## Next Steps (Future Enhancements)

### Property-Based Testing with Hypothesis

```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=2000, max_value=2099))
def test_simulation_year_range(year):
    """Property test: All valid years produce consistent results."""
    config = SimulationConfig(start_year=year, end_year=year)
    assert config.start_year == year
```

### Snapshot Testing for Model Outputs

```python
@pytest.mark.regression
def test_workforce_snapshot_stability(populated_test_db, snapshot_manager):
    """Validate model output hasn't changed unexpectedly."""
    result = populated_test_db.execute("SELECT * FROM fct_workforce_snapshot").fetchall()
    snapshot_manager.assert_matches("workforce_snapshot_2025", result)
```

### Performance Regression Tests

```python
@pytest.mark.performance
def test_event_generation_performance(benchmark):
    """Ensure event generation doesn't regress below 1000 events/second."""
    result = benchmark(generate_events, count=10000)
    assert result.stats.mean < 10.0  # 10 seconds for 10k events
```

---

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/2.0/)
- [DuckDB Python API](https://duckdb.org/docs/api/python)
- Epic E075: Testing Infrastructure Overhaul (`docs/epics/E075_testing_improvements.md`)
