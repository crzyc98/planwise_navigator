# Epic E075: Enterprise-Grade Testing Infrastructure Overhaul

**Status**: 📋 READY FOR EXECUTION
**Priority**: MEDIUM (Long-term Quality Investment)
**Estimated Effort**: 3-4 hours (aggressive, executable TODAY)
**Target Completion**: Single-day sprint

---

## Executive Summary

Transform PlanWise Navigator's test suite from **slow, disorganized technical debt** into a **fast, maintainable, enterprise-grade testing infrastructure**. Current 8,450 lines of test code across 185 tests suffer from:

- **Slow execution** (no fast test mode, database-heavy tests)
- **Poor organization** (tests mixed with fixtures, 992-line monoliths)
- **Unclear coverage** (no coverage reporting on core modules)
- **Scattered fixtures** (29 fixtures spread across files)
- **No test isolation** (database state leakage between tests)

**Goal**: Achieve **90%+ core module coverage** with **<10 second fast test suite** and **clear unit/integration/e2e separation**.

---

## Problem Statement

### Current Test Infrastructure Pain Points

#### 1. **Slow Test Execution**
```bash
# Current: All tests run against real database
pytest tests/  # ~45-60 seconds for unit tests
pytest tests/unit/test_simulation_event.py  # 0.75s for 19 tests (acceptable)
pytest tests/integration/  # ~30 seconds (database setup overhead)
```

**Impact**: Developers skip running tests locally, leading to broken CI builds.

#### 2. **Disorganized Test Structure**
```
tests/
├─ test_e067_threading_comprehensive.py    # 992 lines - MONOLITH
├─ test_e067_resource_validation.py        # 833 lines - MONOLITH
├─ test_hybrid_pipeline_integration.py     # 486 lines - MIXED CONCERNS
├─ conftest.py                             # 743 lines - FIXTURE DUMP
├─ unit/                                   # Only 3 test files (event schema)
├─ integration/                            # 2 large files with collection errors
├─ core/                                   # 4 small test files
├─ performance/                            # Separate concern, good structure
└─ stress/                                 # Separate concern, good structure
```

**Problems**:
- No clear separation of unit/integration/e2e tests
- Large test files violate single-responsibility principle
- Fixtures scattered in conftest.py (743 lines) and test files
- Test discovery errors in integration tests (2 collection errors)

#### 3. **Database State Management**
```python
# Current: Real database connections everywhere
import duckdb
conn = duckdb.connect("dbt/simulation.duckdb")  # Real database
result = conn.execute("SELECT * FROM fct_yearly_events").fetchall()
```

**Problems**:
- Tests depend on database state from previous runs
- No in-memory test databases for fast unit tests
- Database locks cause intermittent test failures
- No cleanup between test runs

#### 4. **No Coverage Reporting**
```bash
# Unknown: What is our actual test coverage?
pytest tests/ --cov=navigator_orchestrator  # Not configured
pytest tests/ --cov=config  # Not configured
```

**Impact**: No visibility into untested code paths.

#### 5. **Scattered Mock Fixtures**
```python
# conftest.py: 29 fixtures mixed with test markers
@pytest.fixture
def mock_dbt_runner():
    return Mock(spec=DbtRunner)

@pytest.fixture
def temp_database():
    # Database setup code

@pytest.fixture
def sample_workforce_data():
    # Test data generation
```

**Problem**: No shared fixture library, fixtures redefined in multiple files.

---

## Technical Approach

### Test Organization Strategy

#### **New Directory Structure**
```
tests/
├─ unit/                          # Pure unit tests (<10s total)
│  ├─ config/                    # Configuration validation
│  │  ├─ test_simulation_config.py
│  │  ├─ test_threading_settings.py
│  │  └─ test_parameter_validation.py
│  ├─ events/                    # Event schema validation (EXISTING - KEEP)
│  │  ├─ test_simulation_event.py
│  │  ├─ test_dc_plan_events.py
│  │  └─ test_plan_administration_events.py
│  ├─ orchestrator/              # Orchestrator unit tests
│  │  ├─ test_pipeline_unit.py
│  │  ├─ test_dbt_runner_unit.py
│  │  ├─ test_registries_unit.py
│  │  └─ test_reports_unit.py
│  ├─ parallel/                  # Threading unit tests
│  │  ├─ test_execution_engine.py
│  │  ├─ test_resource_manager.py
│  │  └─ test_dependency_analyzer.py
│  └─ cli/                       # CLI unit tests
│     ├─ test_commands.py
│     └─ test_validation.py
│
├─ integration/                   # Integration tests (10-30s total)
│  ├─ test_single_year_pipeline.py      # Single year E2E
│  ├─ test_multi_year_coordination.py   # Multi-year state management
│  ├─ test_dbt_integration.py           # dbt command execution
│  ├─ test_checkpoint_recovery.py       # Checkpoint system
│  └─ test_batch_processing.py          # Scenario batch processing
│
├─ e2e/                           # End-to-end tests (30-60s total)
│  ├─ test_full_simulation.py           # Complete 5-year simulation
│  ├─ test_compensation_tuning.py       # Comp parameter workflow
│  └─ test_determinism.py               # Reproducibility validation
│
├─ performance/                   # Performance benchmarks (KEEP EXISTING)
│  └─ test_e067_threading_benchmarks.py
│
├─ stress/                        # Stress tests (KEEP EXISTING)
│  └─ test_e067_threading_stress.py
│
├─ fixtures/                      # Shared fixture library (NEW)
│  ├─ __init__.py                # Export all fixtures
│  ├─ database.py                # In-memory database fixtures
│  ├─ config.py                  # Configuration fixtures
│  ├─ mock_dbt.py                # dbt mocking utilities
│  ├─ workforce_data.py          # Test data generators
│  └─ temporal.py                # Time/date fixtures
│
├─ snapshots/                     # Snapshot test data (NEW)
│  ├─ workforce_snapshot_2025.json
│  ├─ yearly_events_2025.json
│  └─ compensation_metrics.json
│
├─ conftest.py                    # Test configuration ONLY (markers, plugins)
├─ pytest.ini                     # Pytest configuration
└─ README.md                      # Test infrastructure documentation
```

#### **Test Marker Strategy**
```python
# conftest.py - Clean marker configuration
def pytest_configure(config):
    """Configure pytest with comprehensive test markers."""
    # Execution speed markers
    config.addinivalue_line("markers", "fast: Fast unit tests (<1s each)")
    config.addinivalue_line("markers", "slow: Slow integration tests (1-10s each)")
    config.addinivalue_line("markers", "very_slow: E2E tests (10s+ each)")

    # Test type markers
    config.addinivalue_line("markers", "unit: Pure unit tests (no I/O)")
    config.addinivalue_line("markers", "integration: Integration tests (database, dbt)")
    config.addinivalue_line("markers", "e2e: End-to-end workflow tests")

    # Feature area markers
    config.addinivalue_line("markers", "orchestrator: Orchestrator component tests")
    config.addinivalue_line("markers", "events: Event schema tests")
    config.addinivalue_line("markers", "dbt: dbt integration tests")
    config.addinivalue_line("markers", "cli: CLI command tests")
    config.addinivalue_line("markers", "threading: Multi-threading tests")

    # Quality markers
    config.addinivalue_line("markers", "smoke: Critical path smoke tests")
    config.addinivalue_line("markers", "regression: Regression test suite")
```

#### **Fast Test Execution Strategy**
```bash
# Developer workflow: Run fast tests in <10 seconds
pytest -m fast                                    # All fast unit tests (<10s)
pytest -m "fast and orchestrator"                 # Fast orchestrator tests
pytest -m "fast and not threading"                # Skip threading tests

# CI workflow: Tiered test execution
pytest -m fast                                    # Stage 1: Fast tests (10s)
pytest -m "slow and not e2e"                      # Stage 2: Integration (30s)
pytest -m e2e                                     # Stage 3: E2E tests (60s)

# Coverage workflow: Full suite with coverage
pytest --cov=navigator_orchestrator --cov=config --cov-report=html --cov-report=term
```

---

## Story Breakdown (26 Story Points Total)

### **Story S075-01: Reorganize Test Directory Structure** (4 points)
**Goal**: Create clean unit/integration/e2e/fixtures separation.

**Implementation Plan**:
1. Create new directory structure with README files
2. Move existing unit tests to `tests/unit/` subdirectories
3. Split large test files into focused modules:
   - `test_e067_threading_comprehensive.py` (992 lines) → 6 focused test files
   - `test_e067_resource_validation.py` (833 lines) → 4 focused test files
   - `test_hybrid_pipeline_integration.py` (486 lines) → 2 integration tests
4. Add `__init__.py` files with module docstrings
5. Update import paths in moved test files

**Success Criteria**:
- No test file exceeds 300 lines
- Clear separation: unit/ (no I/O), integration/ (database), e2e/ (full workflows)
- All existing tests still pass after reorganization
- Test collection errors resolved (2 current errors)

**Time Estimate**: 60 minutes

---

### **Story S075-02: Create Shared Fixture Library** (5 points)
**Goal**: Centralize all test fixtures in `tests/fixtures/` with clean APIs.

**Implementation Plan**:

#### **1. Database Fixtures (`fixtures/database.py`)**
```python
"""In-memory database fixtures for fast unit tests."""

import duckdb
import pytest
from pathlib import Path
from typing import Generator

@pytest.fixture
def in_memory_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Create in-memory DuckDB database with schema."""
    conn = duckdb.connect(":memory:")

    # Load minimal schema
    schema_sql = Path("dbt/models").rglob("*.sql")
    for sql_file in schema_sql:
        if sql_file.stem.startswith("fct_") or sql_file.stem.startswith("int_"):
            conn.execute(sql_file.read_text())

    yield conn
    conn.close()

@pytest.fixture
def populated_test_db(in_memory_db) -> duckdb.DuckDBPyConnection:
    """In-memory database with sample test data."""
    # Insert baseline workforce (100 employees)
    in_memory_db.execute("""
        INSERT INTO fct_workforce_snapshot
        SELECT * FROM read_csv_auto('tests/fixtures/data/baseline_workforce.csv')
    """)

    # Insert sample events (50 hire/term/promotion events)
    in_memory_db.execute("""
        INSERT INTO fct_yearly_events
        SELECT * FROM read_csv_auto('tests/fixtures/data/sample_events.csv')
    """)

    return in_memory_db

@pytest.fixture
def isolated_test_db(tmp_path) -> Generator[Path, None, None]:
    """Isolated file-based test database with automatic cleanup."""
    db_path = tmp_path / "test_simulation.duckdb"

    # Initialize database
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SCHEMA IF NOT EXISTS main")
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()
```

#### **2. Configuration Fixtures (`fixtures/config.py`)**
```python
"""Configuration fixtures for simulation testing."""

import pytest
from pathlib import Path
from navigator_orchestrator.config import SimulationConfig, ThreadingSettings

@pytest.fixture
def minimal_config() -> SimulationConfig:
    """Minimal valid simulation configuration."""
    return SimulationConfig(
        start_year=2025,
        end_year=2026,
        random_seed=42,
        scenario_id="test_scenario",
        plan_design_id="test_plan"
    )

@pytest.fixture
def single_threaded_config(minimal_config) -> SimulationConfig:
    """Configuration optimized for single-threaded testing."""
    minimal_config.multi_year.optimization.max_workers = 1
    minimal_config.multi_year.performance.enable_parallel_dbt = False
    return minimal_config

@pytest.fixture
def multi_threaded_config(minimal_config) -> SimulationConfig:
    """Configuration with 4-thread parallel execution."""
    minimal_config.multi_year.optimization.max_workers = 4
    minimal_config.multi_year.performance.enable_parallel_dbt = True
    return minimal_config

@pytest.fixture
def config_yaml(tmp_path, minimal_config) -> Path:
    """Write configuration to temporary YAML file."""
    config_path = tmp_path / "test_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(minimal_config.model_dump(), f)
    return config_path
```

#### **3. Mock dbt Fixtures (`fixtures/mock_dbt.py`)**
```python
"""Mock dbt runner and result fixtures."""

import pytest
from unittest.mock import Mock, MagicMock
from navigator_orchestrator.dbt_runner import DbtRunner, DbtResult

@pytest.fixture
def mock_dbt_runner() -> Mock:
    """Mock DbtRunner with successful execution."""
    runner = Mock(spec=DbtRunner)
    runner.execute_command.return_value = DbtResult(
        success=True,
        return_code=0,
        stdout="Completed successfully",
        stderr="",
        execution_time=0.5
    )
    return runner

@pytest.fixture
def failing_dbt_runner() -> Mock:
    """Mock DbtRunner with failed execution."""
    runner = Mock(spec=DbtRunner)
    runner.execute_command.return_value = DbtResult(
        success=False,
        return_code=1,
        stdout="",
        stderr="Database locked: could not acquire lock",
        execution_time=0.1
    )
    return runner

@pytest.fixture
def dbt_streaming_output() -> list[str]:
    """Sample dbt streaming output for testing."""
    return [
        "Running with dbt=1.8.8",
        "Found 42 models, 18 tests, 5 seeds",
        "Concurrency: 1 threads",
        "1 of 42 START sql table model int_baseline_workforce",
        "1 of 42 OK created sql table model int_baseline_workforce",
        "Completed successfully"
    ]
```

#### **4. Workforce Data Fixtures (`fixtures/workforce_data.py`)**
```python
"""Test data generators for workforce simulations."""

import pytest
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict

@pytest.fixture
def sample_employees() -> List[Dict]:
    """Generate 100 sample employees with realistic data."""
    return [
        {
            "employee_id": f"EMP{i:05d}",
            "hire_date": date(2020, 1, 1) + timedelta(days=i*10),
            "base_salary": 50000 + (i * 500),
            "job_band": f"L{(i % 5) + 1}",
            "department": ["Engineering", "Sales", "Operations"][i % 3],
            "is_active": True
        }
        for i in range(100)
    ]

@pytest.fixture
def baseline_workforce_df(sample_employees) -> pd.DataFrame:
    """Baseline workforce as pandas DataFrame."""
    return pd.DataFrame(sample_employees)

@pytest.fixture
def sample_yearly_events() -> List[Dict]:
    """Generate sample hire/termination/promotion events."""
    return [
        {
            "event_id": f"EVT{i:05d}",
            "employee_id": f"EMP{i:05d}",
            "event_type": ["hire", "termination", "promotion"][i % 3],
            "event_date": date(2025, 1, 1) + timedelta(days=i*7),
            "simulation_year": 2025,
            "scenario_id": "baseline",
            "plan_design_id": "standard"
        }
        for i in range(50)
    ]
```

#### **5. Temporal Fixtures (`fixtures/temporal.py`)**
```python
"""Time and date-related fixtures for deterministic testing."""

import pytest
from datetime import date, datetime
from unittest.mock import patch

@pytest.fixture
def frozen_time():
    """Freeze time at 2025-01-01 00:00:00 for deterministic tests."""
    frozen_date = datetime(2025, 1, 1, 0, 0, 0)
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = frozen_date
        mock_datetime.utcnow.return_value = frozen_date
        yield frozen_date

@pytest.fixture
def simulation_years() -> List[int]:
    """Standard 5-year simulation period."""
    return [2025, 2026, 2027, 2028, 2029]

@pytest.fixture
def fiscal_year_2025() -> tuple[date, date]:
    """FY2025 start and end dates."""
    return (date(2025, 1, 1), date(2025, 12, 31))
```

**Migration Plan**:
1. Extract 29 existing fixtures from `conftest.py` → `fixtures/`
2. Consolidate duplicate fixtures across test files
3. Add comprehensive docstrings with usage examples
4. Create `fixtures/__init__.py` with clean exports
5. Update all test files to import from `tests.fixtures`

**Success Criteria**:
- `conftest.py` reduced from 743 lines to <100 lines (markers only)
- All fixtures accessible via `from tests.fixtures import in_memory_db`
- Fixtures documented with type hints and docstrings
- No duplicate fixture definitions across test files

**Time Estimate**: 90 minutes

---

### **Story S075-03: Implement Fast Test Markers and In-Memory Patterns** (5 points)
**Goal**: Enable <10 second fast test suite using in-memory databases and markers.

**Implementation Plan**:

#### **1. Add Test Markers to Existing Tests**
```python
# tests/unit/config/test_simulation_config.py
@pytest.mark.fast
@pytest.mark.unit
def test_load_simulation_config(minimal_config):
    """Test configuration loading with valid YAML."""
    assert config.start_year == 2025
    assert config.end_year == 2026

@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize("invalid_year", [1999, 2100, "2025", None])
def test_invalid_year_validation(invalid_year):
    """Test year validation rejects invalid inputs."""
    with pytest.raises(ValidationError):
        SimulationConfig(start_year=invalid_year, end_year=2026)
```

#### **2. Convert Slow Database Tests to In-Memory**
```python
# BEFORE: Slow integration test (5s)
def test_workforce_snapshot_generation():
    conn = duckdb.connect("dbt/simulation.duckdb")  # Disk I/O
    result = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()
    assert result[0] > 0

# AFTER: Fast unit test (0.05s)
@pytest.mark.fast
@pytest.mark.unit
def test_workforce_snapshot_generation(populated_test_db):
    result = populated_test_db.execute("SELECT COUNT(*) FROM fct_workforce_snapshot").fetchone()
    assert result[0] == 100  # Known test data size
```

#### **3. Create In-Memory Test Database Template**
```python
# fixtures/database.py - Template for fast tests
@pytest.fixture(scope="session")
def test_database_schema() -> str:
    """Load database schema DDL for in-memory databases."""
    schema_parts = []

    # Core tables
    schema_parts.append("""
    CREATE TABLE fct_yearly_events (
        event_id VARCHAR PRIMARY KEY,
        employee_id VARCHAR NOT NULL,
        event_type VARCHAR NOT NULL,
        event_date DATE NOT NULL,
        simulation_year INTEGER NOT NULL,
        scenario_id VARCHAR NOT NULL,
        plan_design_id VARCHAR NOT NULL
    );
    """)

    schema_parts.append("""
    CREATE TABLE fct_workforce_snapshot (
        employee_id VARCHAR PRIMARY KEY,
        simulation_year INTEGER NOT NULL,
        base_salary DOUBLE NOT NULL,
        enrollment_date DATE,
        scenario_id VARCHAR NOT NULL,
        plan_design_id VARCHAR NOT NULL
    );
    """)

    return "\n".join(schema_parts)

@pytest.fixture
def fast_test_db(test_database_schema) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Ultra-fast in-memory database for unit tests (<0.01s setup)."""
    conn = duckdb.connect(":memory:")
    conn.execute(test_database_schema)
    yield conn
    conn.close()
```

#### **4. Update pytest.ini Configuration**
```ini
# pytest.ini
[pytest]
markers =
    fast: Fast unit tests (<1s each)
    slow: Slow integration tests (1-10s each)
    very_slow: E2E tests (10s+ each)
    unit: Pure unit tests (no I/O)
    integration: Integration tests (database, dbt)
    e2e: End-to-end workflow tests
    orchestrator: Orchestrator component tests
    events: Event schema tests
    dbt: dbt integration tests
    cli: CLI command tests
    threading: Multi-threading tests
    smoke: Critical path smoke tests
    regression: Regression test suite

# Default test discovery
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Fast test execution (exclude slow tests by default)
addopts =
    -m "not slow and not very_slow"
    --tb=short
    --strict-markers
    -ra
    --color=yes

# Parallel execution with xdist
# addopts = -n auto
```

**Success Criteria**:
- Fast test suite (`pytest -m fast`) completes in <10 seconds
- All unit tests use in-memory databases (no disk I/O)
- Clear separation: `@pytest.mark.fast` for <1s tests, `@pytest.mark.slow` for 1-10s
- Developers can run `pytest -m fast` after every code change

**Time Estimate**: 75 minutes

---

### **Story S075-04: Add Snapshot Testing for Model Outputs** (4 points)
**Goal**: Catch unintended changes in dbt model outputs using snapshot tests.

**Implementation Plan**:

#### **1. Create Snapshot Test Infrastructure**
```python
# tests/fixtures/snapshots.py
"""Snapshot testing utilities for dbt model outputs."""

import json
import pytest
from pathlib import Path
from typing import Any, Dict
from deepdiff import DeepDiff

class SnapshotManager:
    """Manage snapshot test data for regression testing."""

    def __init__(self, snapshot_dir: Path):
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, name: str, data: Any) -> None:
        """Save snapshot data as JSON."""
        snapshot_path = self.snapshot_dir / f"{name}.json"
        with open(snapshot_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load_snapshot(self, name: str) -> Any:
        """Load snapshot data from JSON."""
        snapshot_path = self.snapshot_dir / f"{name}.json"
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {name}")
        with open(snapshot_path, 'r') as f:
            return json.load(f)

    def compare_snapshot(self, name: str, current_data: Any) -> Dict:
        """Compare current data with saved snapshot."""
        expected = self.load_snapshot(name)
        diff = DeepDiff(expected, current_data, ignore_order=True)
        return diff

@pytest.fixture
def snapshot_manager(tmp_path) -> SnapshotManager:
    """Snapshot manager for tests."""
    return SnapshotManager(tmp_path / "snapshots")
```

#### **2. Create Model Output Snapshots**
```python
# tests/integration/test_model_snapshots.py
"""Snapshot tests for dbt model outputs to catch unintended changes."""

import pytest
import duckdb
from tests.fixtures.snapshots import SnapshotManager

@pytest.mark.integration
@pytest.mark.regression
def test_workforce_snapshot_structure(populated_test_db, snapshot_manager):
    """Validate fct_workforce_snapshot structure hasn't changed."""
    # Query current structure
    result = populated_test_db.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'fct_workforce_snapshot'
        ORDER BY ordinal_position
    """).fetchall()

    current_structure = [
        {"column": row[0], "type": row[1], "nullable": row[2]}
        for row in result
    ]

    # Compare with snapshot
    try:
        diff = snapshot_manager.compare_snapshot("workforce_snapshot_structure", current_structure)
        assert not diff, f"Schema changed unexpectedly: {diff}"
    except FileNotFoundError:
        # First run: save snapshot
        snapshot_manager.save_snapshot("workforce_snapshot_structure", current_structure)
        pytest.skip("Snapshot created, re-run to validate")

@pytest.mark.integration
@pytest.mark.regression
def test_yearly_events_distribution(populated_test_db, snapshot_manager):
    """Validate event type distribution remains stable."""
    result = populated_test_db.execute("""
        SELECT
            event_type,
            COUNT(*) as count,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
        FROM fct_yearly_events
        WHERE simulation_year = 2025
        GROUP BY event_type
        ORDER BY event_type
    """).fetchall()

    distribution = {
        row[0]: {"count": row[1], "percentage": round(row[2], 2)}
        for row in result
    }

    try:
        diff = snapshot_manager.compare_snapshot("yearly_events_distribution", distribution)
        assert not diff, f"Event distribution changed: {diff}"
    except FileNotFoundError:
        snapshot_manager.save_snapshot("yearly_events_distribution", distribution)
        pytest.skip("Snapshot created, re-run to validate")
```

#### **3. Add Compensation Metrics Snapshots**
```python
@pytest.mark.integration
@pytest.mark.regression
def test_compensation_metrics_stability(populated_test_db, snapshot_manager):
    """Validate compensation calculations remain consistent."""
    result = populated_test_db.execute("""
        SELECT
            simulation_year,
            ROUND(AVG(base_salary), 2) as avg_salary,
            ROUND(STDDEV(base_salary), 2) as salary_stddev,
            ROUND(MIN(base_salary), 2) as min_salary,
            ROUND(MAX(base_salary), 2) as max_salary,
            COUNT(*) as employee_count
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025
        GROUP BY simulation_year
    """).fetchone()

    metrics = {
        "year": result[0],
        "avg_salary": result[1],
        "salary_stddev": result[2],
        "min_salary": result[3],
        "max_salary": result[4],
        "employee_count": result[5]
    }

    try:
        diff = snapshot_manager.compare_snapshot("compensation_metrics_2025", metrics)
        # Allow 1% tolerance for floating-point differences
        if diff:
            for key in ["avg_salary", "salary_stddev"]:
                if key in diff.get("values_changed", {}):
                    old_val = diff["values_changed"][key]["old_value"]
                    new_val = diff["values_changed"][key]["new_value"]
                    pct_change = abs(new_val - old_val) / old_val
                    assert pct_change < 0.01, f"{key} changed by {pct_change*100:.2f}%"
    except FileNotFoundError:
        snapshot_manager.save_snapshot("compensation_metrics_2025", metrics)
        pytest.skip("Snapshot created, re-run to validate")
```

**Success Criteria**:
- Snapshot tests for 5 core dbt models (fct_yearly_events, fct_workforce_snapshot, int_baseline_workforce, int_employee_compensation, int_enrollment_events)
- Snapshot update workflow: `pytest --update-snapshots` to regenerate
- CI integration: Fail if snapshots differ without explicit update
- Tolerance handling for floating-point comparisons (±1%)

**Time Estimate**: 60 minutes

---

### **Story S075-05: Achieve 90%+ Coverage on Core Modules** (5 points)
**Goal**: Comprehensive test coverage with visible reporting.

**Implementation Plan**:

#### **1. Install and Configure Coverage Tools**
```bash
# Add to requirements-dev.txt
pytest-cov==4.1.0
coverage[toml]==7.3.2
```

```toml
# Add to pyproject.toml
[tool.coverage.run]
source = ["navigator_orchestrator", "config"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/venv/*",
    "*/streamlit_dashboard/*",  # Separate coverage for dashboards
]

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]

[tool.coverage.html]
directory = "htmlcov"
```

#### **2. Add Coverage Targets by Module**
```python
# tests/test_coverage_requirements.py
"""Enforce minimum coverage requirements on core modules."""

import pytest
import subprocess
import json

COVERAGE_TARGETS = {
    "navigator_orchestrator.pipeline": 95,
    "navigator_orchestrator.config": 90,
    "navigator_orchestrator.dbt_runner": 90,
    "navigator_orchestrator.registries": 85,
    "navigator_orchestrator.reports": 85,
    "navigator_orchestrator.validation": 90,
    "config.events": 95,  # Event schemas must be thoroughly tested
    "config.schema": 90,
}

@pytest.mark.slow
def test_coverage_requirements():
    """Validate test coverage meets minimum thresholds."""
    # Run coverage analysis
    result = subprocess.run(
        ["pytest", "--cov=navigator_orchestrator", "--cov=config", "--cov-report=json"],
        capture_output=True,
        text=True
    )

    # Load coverage report
    with open("coverage.json") as f:
        coverage_data = json.load(f)

    # Check each module
    failures = []
    for module, target in COVERAGE_TARGETS.items():
        actual = coverage_data["totals"].get(module, {}).get("percent_covered", 0)
        if actual < target:
            failures.append(f"{module}: {actual:.1f}% (target: {target}%)")

    if failures:
        pytest.fail(f"Coverage requirements not met:\n" + "\n".join(failures))
```

#### **3. Identify and Fill Coverage Gaps**

**Priority 1: Core Orchestrator (Target: 95%)**
```python
# tests/unit/orchestrator/test_pipeline_unit.py - EXPAND COVERAGE
@pytest.mark.fast
@pytest.mark.unit
def test_pipeline_initialization_validation(minimal_config):
    """Test pipeline initialization with invalid config."""
    with pytest.raises(ValueError, match="start_year must be <= end_year"):
        PipelineOrchestrator(SimulationConfig(start_year=2026, end_year=2025))

@pytest.mark.fast
@pytest.mark.unit
def test_pipeline_stage_execution_order(mock_dbt_runner, minimal_config):
    """Test workflow stages execute in correct order."""
    orchestrator = PipelineOrchestrator(minimal_config, dbt_runner=mock_dbt_runner)

    executed_stages = []
    def capture_stage(stage_name):
        executed_stages.append(stage_name)

    with patch.object(orchestrator, '_execute_stage', side_effect=capture_stage):
        orchestrator.run_single_year(2025)

    expected_order = ["INITIALIZATION", "FOUNDATION", "EVENT_GENERATION", "STATE_ACCUMULATION", "VALIDATION", "REPORTING"]
    assert executed_stages == expected_order

@pytest.mark.fast
@pytest.mark.unit
def test_pipeline_error_handling(failing_dbt_runner, minimal_config):
    """Test pipeline handles dbt execution failures gracefully."""
    orchestrator = PipelineOrchestrator(minimal_config, dbt_runner=failing_dbt_runner)

    with pytest.raises(RuntimeError, match="dbt command failed"):
        orchestrator.run_single_year(2025)
```

**Priority 2: Configuration (Target: 90%)**
```python
# tests/unit/config/test_simulation_config.py - EXPAND COVERAGE
@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize("field,value,error_msg", [
    ("start_year", 1999, "start_year must be >= 2000"),
    ("end_year", 2100, "end_year must be <= 2099"),
    ("random_seed", -1, "random_seed must be >= 0"),
    ("target_growth_rate", -0.5, "target_growth_rate must be >= -0.2"),
])
def test_config_field_validation(field, value, error_msg):
    """Test configuration field validation."""
    config_dict = {
        "start_year": 2025,
        "end_year": 2026,
        "random_seed": 42,
        "scenario_id": "test",
        "plan_design_id": "test"
    }
    config_dict[field] = value

    with pytest.raises(ValidationError, match=error_msg):
        SimulationConfig(**config_dict)
```

**Priority 3: Event Schemas (Target: 95%)**
```python
# tests/unit/events/test_simulation_event.py - ALREADY GOOD (19 tests, 0.33s)
# Just add a few edge cases:

@pytest.mark.fast
@pytest.mark.unit
def test_event_discriminated_union_validation():
    """Test discriminated union correctly validates event types."""
    # Valid hire event
    hire = SimulationEvent(
        event_type="hire",
        employee_id="EMP00001",
        event_date=date(2025, 1, 1),
        scenario_id="test",
        plan_design_id="test",
        payload=HirePayload(base_salary=50000, job_band="L1")
    )
    assert isinstance(hire.payload, HirePayload)

    # Invalid: event_type mismatch with payload
    with pytest.raises(ValidationError):
        SimulationEvent(
            event_type="termination",
            payload=HirePayload(base_salary=50000, job_band="L1")  # Wrong payload type
        )
```

#### **4. Add Coverage Reporting to CI**
```yaml
# .github/workflows/test.yml
- name: Run Tests with Coverage
  run: |
    pytest --cov=navigator_orchestrator --cov=config \
           --cov-report=html --cov-report=term --cov-report=xml

- name: Upload Coverage to Codecov
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
    fail_ci_if_error: true

- name: Coverage Comment
  uses: py-cov-action/python-coverage-comment-action@v3
  with:
    GITHUB_TOKEN: ${{ github.token }}
```

**Success Criteria**:
- Overall coverage: 90%+ on navigator_orchestrator, config modules
- Coverage reports generated: HTML (htmlcov/), terminal, XML (CI)
- CI fails if coverage drops below thresholds
- Coverage badge in README showing current percentage

**Time Estimate**: 75 minutes

---

### **Story S075-06: Document Testing Infrastructure** (3 points)
**Goal**: Clear documentation for test organization, fixtures, and execution strategies.

**Implementation Plan**:

#### **Create `tests/README.md`**
```markdown
# PlanWise Navigator Testing Infrastructure

Enterprise-grade testing framework with **90%+ coverage** and **<10 second fast test suite**.

---

## Quick Start

### Run Fast Unit Tests (Developer Workflow)
```bash
# All fast tests (<10 seconds)
pytest -m fast

# Specific component tests
pytest -m "fast and orchestrator"
pytest -m "fast and events"
pytest -m "fast and config"

# Watch mode for TDD
pytest -m fast --watch
```

### Run Full Test Suite (CI Workflow)
```bash
# Tiered execution strategy
pytest -m fast                    # Stage 1: Fast tests (10s)
pytest -m "slow and not e2e"      # Stage 2: Integration (30s)
pytest -m e2e                     # Stage 3: E2E tests (60s)

# Full suite with coverage
pytest --cov=navigator_orchestrator --cov=config --cov-report=html
```

---

## Test Organization

### Directory Structure
```
tests/
├─ unit/              # Pure unit tests (no I/O, <1s each)
│  ├─ config/        # Configuration validation
│  ├─ events/        # Event schema validation
│  ├─ orchestrator/  # Orchestrator unit tests
│  ├─ parallel/      # Threading unit tests
│  └─ cli/           # CLI command tests
│
├─ integration/       # Integration tests (database, dbt, 1-10s)
│  ├─ test_single_year_pipeline.py
│  ├─ test_multi_year_coordination.py
│  └─ test_checkpoint_recovery.py
│
├─ e2e/              # End-to-end tests (full workflows, 10s+)
│  ├─ test_full_simulation.py
│  └─ test_determinism.py
│
├─ performance/       # Performance benchmarks
├─ stress/           # Stress tests
├─ fixtures/         # Shared fixture library
└─ snapshots/        # Snapshot test data
```

### Test Markers
- `@pytest.mark.fast` - Fast unit tests (<1s each)
- `@pytest.mark.slow` - Slow integration tests (1-10s)
- `@pytest.mark.unit` - Pure unit tests (no I/O)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end workflow tests
- `@pytest.mark.smoke` - Critical path smoke tests

---

## Fixture Library

### Database Fixtures (`fixtures/database.py`)
```python
from tests.fixtures import in_memory_db, populated_test_db

@pytest.mark.fast
def test_query_performance(in_memory_db):
    """Test using in-memory database."""
    result = in_memory_db.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
    assert result[0] > 0
```

### Configuration Fixtures (`fixtures/config.py`)
```python
from tests.fixtures import minimal_config, single_threaded_config

@pytest.mark.fast
def test_pipeline_initialization(single_threaded_config):
    """Test with single-threaded configuration."""
    orchestrator = PipelineOrchestrator(single_threaded_config)
    assert orchestrator.config.multi_year.optimization.max_workers == 1
```

### Mock Fixtures (`fixtures/mock_dbt.py`)
```python
from tests.fixtures import mock_dbt_runner

@pytest.mark.fast
def test_orchestrator_dbt_integration(mock_dbt_runner):
    """Test orchestrator with mocked dbt execution."""
    orchestrator = PipelineOrchestrator(config, dbt_runner=mock_dbt_runner)
    orchestrator.run_single_year(2025)
    mock_dbt_runner.execute_command.assert_called()
```

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

| Module | Target | Current |
|--------|--------|---------|
| navigator_orchestrator.pipeline | 95% | TBD |
| navigator_orchestrator.config | 90% | TBD |
| navigator_orchestrator.dbt_runner | 90% | TBD |
| config.events | 95% | 98% ✅ |

### Check Coverage
```bash
# Generate HTML report
pytest --cov=navigator_orchestrator --cov-report=html
open htmlcov/index.html

# Terminal report
pytest --cov=navigator_orchestrator --cov-report=term-missing
```

---

## Continuous Integration

### GitHub Actions Workflow
```yaml
jobs:
  test:
    steps:
      - name: Fast Tests
        run: pytest -m fast

      - name: Integration Tests
        run: pytest -m "slow and not e2e"

      - name: E2E Tests
        run: pytest -m e2e

      - name: Coverage Report
        run: pytest --cov --cov-report=xml
```

---

## Troubleshooting

### Tests Fail with Database Lock
**Problem**: `Database locked: could not acquire lock`
**Solution**: Close all IDE connections to `dbt/simulation.duckdb`

### Slow Test Execution
**Problem**: Fast tests take >10 seconds
**Solution**: Ensure tests use `in_memory_db` fixture, not file-based database

### Snapshot Mismatches
**Problem**: Snapshot tests fail after intentional model changes
**Solution**: Update snapshots with `pytest --update-snapshots`
```

**Success Criteria**:
- README.md with quickstart, directory structure, fixture usage
- Developer workflow documentation (TDD, fast tests, markers)
- Coverage requirements and CI integration documented
- Troubleshooting guide for common test issues

**Time Estimate**: 45 minutes

---

## Success Metrics

### Performance Targets
- ✅ **Fast test suite**: <10 seconds (unit tests only)
- ✅ **Integration tests**: <30 seconds (database + dbt)
- ✅ **Full test suite**: <60 seconds (all tests)
- ✅ **CI execution time**: <5 minutes (parallel execution)

### Coverage Targets
- ✅ **Overall coverage**: 90%+ on core modules
- ✅ **navigator_orchestrator.pipeline**: 95%
- ✅ **navigator_orchestrator.config**: 90%
- ✅ **config.events**: 95% (already achieved)
- ✅ **navigator_orchestrator.dbt_runner**: 90%

### Organization Targets
- ✅ **Test file size**: No file exceeds 300 lines
- ✅ **Fixture centralization**: All fixtures in `tests/fixtures/`
- ✅ **Clear separation**: unit/ (no I/O), integration/ (database), e2e/ (workflows)
- ✅ **Zero test collection errors**: Fix 2 current collection errors

### Developer Experience
- ✅ **Fast feedback loop**: Run `pytest -m fast` after every change
- ✅ **Clear test failures**: Descriptive assertions with failure messages
- ✅ **Easy fixture discovery**: All fixtures in `tests.fixtures` with docstrings
- ✅ **Snapshot testing**: Catch unintended model changes automatically

---

## Technical Dependencies

### Required Packages (Add to requirements-dev.txt)
```bash
pytest==7.4.0                    # Test framework
pytest-cov==4.1.0                # Coverage reporting
pytest-xdist==3.3.1              # Parallel test execution
pytest-mock==3.11.1              # Mock utilities
pytest-watch==4.2.0              # Watch mode for TDD
coverage[toml]==7.3.2            # Coverage configuration
deepdiff==6.4.1                  # Snapshot comparison
Faker==19.3.0                    # Test data generation (already installed)
```

### DuckDB In-Memory Performance
- **Setup time**: <0.01s per test (in-memory schema creation)
- **Query performance**: 10-100× faster than file-based database
- **Memory usage**: ~10 MB per in-memory database
- **Isolation**: Each test gets clean database state

---

## Execution Timeline (3-4 hours)

### Hour 1: Structure and Fixtures (S075-01, S075-02)
- **00:00-00:30**: Create directory structure, move existing tests
- **00:30-01:00**: Extract fixtures from conftest.py to fixtures/
- **Status Check**: Run `pytest tests/` to ensure no regressions

### Hour 2: Fast Tests and Markers (S075-03)
- **01:00-01:30**: Add test markers to all existing tests
- **01:30-02:00**: Convert database tests to in-memory fixtures
- **Status Check**: Run `pytest -m fast` to validate <10s execution

### Hour 3: Coverage and Snapshots (S075-04, S075-05)
- **02:00-02:30**: Add snapshot testing infrastructure
- **02:30-03:00**: Write tests to fill coverage gaps
- **Status Check**: Run `pytest --cov` to validate 90%+ coverage

### Hour 4: Documentation and Validation (S075-06)
- **03:00-03:30**: Write tests/README.md and fixture documentation
- **03:30-04:00**: Final validation, CI integration, epic completion

---

## Risk Mitigation

### Risk: Test Reorganization Breaks Existing Tests
**Mitigation**: Run full test suite after each file move, update import paths incrementally

### Risk: In-Memory Database Doesn't Match Production Schema
**Mitigation**: Generate in-memory schema from dbt models, use snapshot tests to catch drift

### Risk: Coverage Targets Too Aggressive for Legacy Code
**Mitigation**: Apply 90% target to new code only, 70% target for legacy modules

### Risk: Snapshot Tests Create Maintenance Burden
**Mitigation**: Only snapshot 5 critical models, use 1% tolerance for floating-point, clear update workflow

---

## Future Enhancements (Post-E075)

### Property-Based Testing with Hypothesis
```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=2000, max_value=2099))
def test_simulation_year_range(year):
    """Property test: All valid years produce consistent results."""
    config = SimulationConfig(start_year=year, end_year=year)
    assert config.start_year == year
```

### Performance Regression Tests
```python
@pytest.mark.performance
def test_event_generation_performance_regression(populated_test_db):
    """Ensure event generation doesn't regress below 1000 events/second."""
    start = time.time()
    result = generate_events(populated_test_db, count=10000)
    duration = time.time() - start

    events_per_second = 10000 / duration
    assert events_per_second >= 1000, f"Performance regression: {events_per_second:.0f} events/s"
```

### Contract Testing for dbt Models
```python
@pytest.mark.integration
def test_fct_yearly_events_contract(populated_test_db):
    """Validate fct_yearly_events satisfies data contract."""
    # Required columns
    required_columns = ["event_id", "employee_id", "event_type", "event_date", "simulation_year"]
    result = populated_test_db.execute("PRAGMA table_info(fct_yearly_events)").fetchall()
    actual_columns = [row[1] for row in result]

    for col in required_columns:
        assert col in actual_columns, f"Missing required column: {col}"

    # Data quality constraints
    result = populated_test_db.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT event_id) as unique_ids,
            COUNT(CASE WHEN event_date IS NULL THEN 1 END) as null_dates
        FROM fct_yearly_events
    """).fetchone()

    assert result[0] == result[1], "event_id uniqueness violation"
    assert result[2] == 0, "NULL event_date constraint violation"
```

---

## Appendix: Test File Migration Map

### Large Files to Split
| Original File | Size | New Files |
|--------------|------|-----------|
| test_e067_threading_comprehensive.py | 992 lines | test_threading_config.py (150)<br>test_execution_engine.py (200)<br>test_resource_manager.py (180)<br>test_dependency_analyzer.py (150)<br>test_threading_integration.py (250)<br>test_threading_determinism.py (100) |
| test_e067_resource_validation.py | 833 lines | test_cpu_monitor.py (150)<br>test_memory_monitor.py (150)<br>test_resource_limits.py (200)<br>test_resource_manager_integration.py (250) |
| test_hybrid_pipeline_integration.py | 486 lines | test_polars_pipeline.py (250)<br>test_hybrid_orchestrator.py (250) |
| conftest.py | 743 lines | conftest.py (100) - markers only<br>fixtures/database.py (150)<br>fixtures/config.py (120)<br>fixtures/mock_dbt.py (100)<br>fixtures/workforce_data.py (150)<br>fixtures/temporal.py (80) |

---

## Epic Completion Checklist

- [ ] **S075-01**: Test directory reorganization complete
- [ ] **S075-02**: Shared fixture library created
- [ ] **S075-03**: Fast test markers and in-memory patterns implemented
- [ ] **S075-04**: Snapshot testing infrastructure added
- [ ] **S075-05**: 90%+ coverage achieved on core modules
- [ ] **S075-06**: Testing infrastructure documented
- [ ] Fast test suite executes in <10 seconds
- [ ] All 185 tests passing after reorganization
- [ ] Coverage reports integrated into CI
- [ ] Developer workflow documented in README
- [ ] Zero test collection errors

---

**Epic Owner**: Engineering Team
**Stakeholders**: All Developers
**Dependencies**: None (fully independent)
**Blockers**: None

**Ready to Execute**: This epic can be completed TODAY in a single 3-4 hour sprint with immediate ROI on developer productivity and code quality.
