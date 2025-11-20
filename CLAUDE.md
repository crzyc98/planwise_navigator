# PlanWise Navigator – Claude Code-Generation Playbook

A comprehensive, opinionated reference for generating enterprise-grade, production-ready code for workforce simulation and event sourcing.

-----

## **1. Purpose**

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for PlanWise Navigator, Fidelity's on-premises workforce-simulation platform. Follow it verbatim to guarantee:

  * Event-sourced architecture with immutable audit trails
  * Modular, maintainable components with single-responsibility design
  * Enterprise-grade transparency and reproducibility
  * Production-ready deployment to analytics servers

-----

## **2. Technology Stack**

| Layer | Technology | Version | Responsibility |
| :--- | :--- | :--- | :--- |
| **Storage** | DuckDB | 1.0.0 | Immutable event store; column-store OLAP engine |
| **Transformation** | dbt-core | 1.8.8 | Declarative SQL models, tests, documentation |
| **Adapter** | dbt-duckdb | 1.8.1 | Stable DuckDB integration |
| **Orchestration** | navigator_orchestrator | Modular | PipelineOrchestrator with staged workflow execution |
| **CLI Interface** | planwise_cli (Rich + Typer) | 1.0.0 | Beautiful terminal interface with progress tracking |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics and compensation tuning |
| **Configuration** | Pydantic | 2.7.4 | Type-safe config management with validation |
| **Python** | CPython | 3.11.x | Long-term support version |
| **Package Manager** | uv | Latest | 10-100× faster than pip |

-----

## **3. Quick Start**

```bash
# Environment setup with uv (10-100× faster than pip)
uv venv .venv --python python3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Primary workflow - PlanWise CLI (Rich interface)
planwise health                                 # System readiness check
planwise simulate 2025-2027                     # Multi-year simulation
planwise batch --scenarios baseline high_growth # Batch processing
planwise status --detailed                      # Full system diagnostic

# Development workflow
planwise simulate 2025 --dry-run               # Preview execution plan
planwise simulate 2025 --verbose               # Detailed logging
planwise checkpoints list                      # View recovery points

# dbt development (always from /dbt directory)
cd dbt
dbt build --threads 1 --fail-fast              # Build all models
dbt run --select int_baseline_workforce+ --threads 1  # Incremental build
dbt test --select tag:data_quality             # Run quality tests

# Database access (Claude can execute these)
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
duckdb dbt/simulation.duckdb "SHOW TABLES"
```

-----

## **4. Event Sourcing Architecture**

PlanWise Navigator implements enterprise-grade event sourcing with immutable audit trails.

**Core Principles**:

  * **Immutability**: Every event is permanently recorded with a UUID.
  * **Auditability**: Complete workforce history reconstruction from events.
  * **Reproducibility**: Identical scenarios with the same random seed.
  * **Transparency**: Full visibility into every simulation decision.
  * **Type Safety**: Pydantic v2 validation on all event payloads.

**Event Types**:

  * **HIRE**: New employee onboarding with UUID and timestamp.
  * **TERMINATION**: Employee departure with reason codes.
  * **PROMOTION**: Level/band changes with compensation adjustments.
  * **RAISE**: Salary modifications (COLA, merit, market adjustment).
  * **BENEFIT_ENROLLMENT**: Plan participation changes.
  * **DC_PLAN_ELIGIBILITY**: Retirement plan eligibility determination.
  * **DC_PLAN_ENROLLMENT**: Retirement plan participation events.
  * **DC_PLAN_CONTRIBUTION**: Employee/employer contribution events.
  * **DC_PLAN_VESTING**: Vesting schedule progression.
  * **FORFEITURE**: Plan administration forfeiture events.
  * **HCE_STATUS**: Highly Compensated Employee determination.

**Event Creation Pattern (Pydantic v2)**:

```python
from config.events import WorkforceEventFactory, DCPlanEventFactory
from decimal import Decimal
from datetime import date

# Workforce events
hire_event = WorkforceEventFactory.create_hire_event(
    employee_id="EMP_2025_001",
    scenario_id="baseline_2025",
    plan_design_id="standard_401k",
    hire_date=date(2025, 1, 15),
    department="Engineering",
    job_level=3,
    annual_compensation=Decimal("125000.00")
)

# DC plan events
enrollment_event = DCPlanEventFactory.create_enrollment_event(
    employee_id="EMP_2025_001",
    scenario_id="baseline_2025",
    plan_design_id="standard_401k",
    enrollment_date=date(2025, 2, 1),
    deferral_rate=Decimal("0.06"),
    investment_election={"target_date_2055": Decimal("1.0")}
)
```

**Modular Engines**:

  * **Compensation Engine**: COLA, merit, and promotion-based adjustments.
  * **Termination Engine**: Hazard-based turnover modeling.
  * **Hiring Engine**: Growth-driven recruitment with realistic sampling.
  * **Promotion Engine**: Band-aware advancement probabilities.
  * **DC Plan Engine**: Retirement plan contribution, vesting, and distribution modeling.
  * **Plan Administration Engine**: Forfeiture processing, HCE determination, IRS compliance.

-----

## **5. Directory Structure**

```
planwise_navigator/
├─ navigator_orchestrator/           # Production orchestration engine
│  ├─ pipeline/                      # Modular pipeline components (E072)
│  │  ├─ workflow.py                # Stage definitions and workflow building
│  │  ├─ state_manager.py           # Checkpoint and state management
│  │  ├─ year_executor.py           # Stage-by-stage execution orchestration
│  │  ├─ event_generation_executor.py # Hybrid SQL/Polars event generation
│  │  ├─ hooks.py                   # Extensible callback system
│  │  └─ data_cleanup.py            # Database cleanup operations
│  ├─ pipeline_orchestrator.py      # Main orchestrator (1,220 lines)
│  ├─ config.py                     # SimulationConfig management
│  ├─ dbt_runner.py                 # DbtRunner with streaming output
│  ├─ exceptions.py                 # Enhanced error handling (E074)
│  ├─ error_catalog.py              # Pattern-based error recognition
│  └─ validation.py                 # Data quality validation
├─ planwise_cli/                     # Rich-based CLI (primary interface)
│  ├─ commands/                      # Command implementations
│  │  ├─ simulate.py                # Multi-year simulation
│  │  ├─ batch.py                   # Batch scenario processing
│  │  ├─ status.py                  # System health and status
│  │  └─ checkpoint.py              # Checkpoint management
│  └─ main.py                       # CLI entry point
├─ dbt/                              # dbt project
│  ├─ models/                        # SQL transformation models
│  │  ├─ staging/                   # Raw data cleaning (stg_*) - 17 models
│  │  ├─ intermediate/              # Business logic (int_*) - 62 models
│  │  │  ├─ events/                # Event generation models
│  │  │  ├─ int_enrollment_state_accumulator.sql
│  │  │  └─ int_deferral_rate_state_accumulator.sql
│  │  └─ marts/                     # Final outputs (fct_*, dim_*) - 27 models
│  ├─ seeds/                        # Configuration data (CSV)
│  └─ macros/                       # Reusable SQL functions
├─ streamlit_dashboard/              # Interactive dashboard
├─ config/                           # Configuration management
│  ├─ simulation_config.yaml        # Simulation parameters
│  └─ events.py                     # Unified event model (Pydantic v2, 971 lines)
├─ tests/                            # Comprehensive testing (256 tests)
│  ├─ fixtures/                     # Centralized fixture library (E075)
│  │  ├─ database.py               # In-memory, populated, isolated databases
│  │  ├─ config.py                 # Test configurations
│  │  ├─ mock_dbt.py               # Mock dbt runners
│  │  └─ workforce_data.py         # Sample employees and events
│  └─ test_*.py                     # Test modules
├─ data/                             # Raw input files (git-ignored)
└─ dbt/simulation.duckdb             # DuckDB database file (standardized location)
```

-----

## **6. Pipeline Orchestration (E072 - Modular Architecture)**

The pipeline was refactored from a 2,478-line monolith into 6 focused modules:

**Core Components**:

```python
from navigator_orchestrator.pipeline import (
    WorkflowBuilder,      # Stage definitions and workflow building
    StateManager,         # Checkpoint and state management
    YearExecutor,         # Stage-by-stage execution orchestration
    EventGenerationExecutor,  # Hybrid SQL/Polars event generation
    HookManager,          # Extensible callback system
    DataCleanupManager    # Database cleanup operations
)

from navigator_orchestrator.pipeline_orchestrator import PipelineOrchestrator

# Create orchestrator
config = load_simulation_config('config/simulation_config.yaml')
orchestrator = PipelineOrchestrator(config)

# Execute multi-year simulation
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027,
    fail_on_validation_error=False
)
```

**Workflow Stages** (sequential execution within each year):

1. **INITIALIZATION**: Load seeds and staging data
2. **FOUNDATION**: Build baseline workforce and compensation
3. **EVENT_GENERATION**: Generate hire/termination/promotion events
4. **STATE_ACCUMULATION**: Build accumulators and snapshots
5. **VALIDATION**: Run data quality checks
6. **REPORTING**: Generate audit reports

-----

## **7. Error Handling (E074 - Enhanced Diagnostics)**

```python
from navigator_orchestrator.exceptions import (
    NavigatorError,       # Base exception with execution context
    DatabaseError,        # Database operations
    ConfigurationError,   # Config validation
    PipelineError,        # Pipeline execution
    DbtError,             # dbt command failures
    ResourceError,        # Resource constraints
    StateError            # State management
)

from navigator_orchestrator.error_catalog import ErrorCatalog

# Structured error handling with context
try:
    orchestrator.execute_year(2025)
except DbtError as e:
    # Error includes execution context, correlation ID, resolution hints
    print(f"Error: {e.message}")
    print(f"Stage: {e.context.stage}")
    print(f"Model: {e.context.model}")
    print(f"Resolution: {e.resolution_hint}")
```

-----

## **8. Development Workflow**

### **Testing Infrastructure (E075 - Fixture Library)**

```bash
# Fast unit tests (TDD workflow) - 87 tests in ~5 seconds
pytest -m fast

# Component-specific tests
pytest -m "fast and orchestrator"       # Orchestrator tests
pytest -m "fast and events"             # Event schema tests
pytest -m "fast and config"             # Configuration tests

# Integration tests
pytest -m integration                   # Full integration suite

# Full suite with coverage
pytest --cov=navigator_orchestrator \
       --cov=planwise_cli \
       --cov-report=html
```

**Using Fixtures**:

```python
# tests/test_my_feature.py
from tests.fixtures.database import in_memory_db, populated_db
from tests.fixtures.config import minimal_config
from tests.fixtures.workforce_data import sample_employees

def test_hire_event_generation(populated_db, minimal_config):
    """Test hire event generation with pre-populated database."""
    orchestrator = PipelineOrchestrator(minimal_config)
    result = orchestrator.execute_year(2025)
    assert result.success
```

### **Database Access Pattern**

```python
# CORRECT: Use get_database_path() for all database access
from navigator_orchestrator.config import get_database_path
import duckdb

def query_events(year: int):
    conn = duckdb.connect(str(get_database_path()))
    result = conn.execute(
        "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
        [year]
    ).fetchall()
    conn.close()
    return result[0][0]

# Claude can execute DuckDB queries directly via Bash
# duckdb dbt/simulation.duckdb "SELECT * FROM fct_workforce_snapshot LIMIT 10"
```

### **dbt Development Patterns**

```bash
# Always run from /dbt directory with --threads 1 for stability
cd dbt

# Single model development
dbt run --select int_baseline_workforce --vars "simulation_year: 2025" --threads 1

# Incremental build pattern
dbt run --select int_baseline_workforce+ --threads 1

# Event generation models (filtered by year)
dbt run --select tag:EVENT_GENERATION --vars "simulation_year: 2025" --threads 1

# Full build (safe for work laptops)
dbt build --threads 1 --fail-fast
```

**Incremental Model Pattern**:

```sql
-- Optimized incremental configuration
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
  pre_hook="DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}"
) }}

-- Filter early to reduce memory usage
SELECT *
FROM {{ ref('upstream_model') }}
WHERE simulation_year = {{ var('simulation_year') }}
  {% if is_incremental() %}
    AND simulation_year = {{ var('simulation_year') }}
  {% endif %}
```

-----

## **9. Naming and Coding Standards**

### **Naming Conventions**

  * **dbt models**: `tier_entity_purpose` (e.g., `fct_workforce_snapshot`, `int_termination_events`)
  * **Event tables**: `fct_yearly_events` (immutable), `fct_workforce_snapshot` (point-in-time)
  * **Python orchestration**: `snake_case`, descriptive (e.g., `run_year_simulation`, `audit_year_results`)
  * **Python**: PEP 8; mandatory type-hints; Pydantic v2 models for config
  * **Configuration**: `snake_case` in YAML, hierarchical structure

### **Coding Standards**

  * **SQL (dbt)**: Use 2-space indents, uppercase keywords, one clause per line. Avoid `SELECT *`. Use `{{ ref() }}` and CTEs for readability.
  * **Python**: Keep functions under 40 lines. Raise explicit exceptions. Use Pydantic v2 for data modeling.

**Do/Don't (DuckDB/dbt)**:
- ✅ Filter heavy models by `{{ var('simulation_year') }}`
- ✅ Join on `(scenario_id, plan_design_id, employee_id)` and year when relevant
- ✅ Use incremental models with `incremental_strategy='delete+insert'`
- ❌ Don't use adapter-unsupported configs like physical `partition_by`/indexes
- ❌ Don't read from `fct_*` tables in `int_*` models (circular dependencies)

**Python Type-Safe Example**:

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date
from decimal import Decimal

class EmployeeEvent(BaseModel):
    employee_id: str = Field(..., min_length=1)
    event_type: Literal["HIRE", "TERMINATION", "PROMOTION", "RAISE"]
    effective_date: date
    annual_compensation: Decimal
```

-----

## **10. Critical Patterns**

### **Temporal State Accumulators**

**Pattern**: Year N reads Year N-1 accumulator data + Year N events to produce state without circular dependencies.

**Example**: Enrollment state tracking
```sql
-- int_enrollment_state_accumulator.sql
WITH prior_year_state AS (
  SELECT *
  FROM {{ this }}
  WHERE simulation_year = {{ var('simulation_year') }} - 1
),
current_year_events AS (
  SELECT *
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
  COALESCE(e.employee_id, p.employee_id) AS employee_id,
  COALESCE(e.enrollment_date, p.enrollment_date) AS enrollment_date,
  {{ var('simulation_year') }} AS simulation_year
FROM current_year_events e
FULL OUTER JOIN prior_year_state p
  ON e.employee_id = p.employee_id
```

**Build Order**: Accumulator → `int_*` models → `fct_yearly_events` → `fct_workforce_snapshot`

### **Batch Scenario Processing (E069)**

```bash
# Run all scenarios in scenarios/ directory
planwise batch

# Run specific scenarios with clean start
planwise batch --scenarios baseline high_growth --clean

# Export to Excel with metadata
planwise batch --export-format excel

# Batch creates timestamped directories with:
# - Individual scenario databases (scenario_name.duckdb)
# - Excel exports with workforce snapshots, metrics, events
# - Metadata sheets with git SHA, seed, configuration
# - Comparison reports across scenarios
```

-----

## **11. Troubleshooting**

### **Database and Path Issues**

  * **Database Location**: `dbt/simulation.duckdb` (standardized location)
  * **dbt Commands**: Always run from `/dbt` directory
  * **Database Access**: Always use `get_database_path()` from `navigator_orchestrator.config`

```python
# CORRECT pattern
from navigator_orchestrator.config import get_database_path
import duckdb

conn = duckdb.connect(str(get_database_path()))
result = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?", [year]).fetchall()
conn.close()
```

### **Virtual Environment**

  * **Problem**: `ModuleNotFoundError` when running Python or dbt commands
  * **Cause**: Using system-installed packages instead of virtual environment packages
  * **Solution**: Always activate the virtual environment (`source .venv/bin/activate`)

### **Database Locks**

  * **Problem**: Simulations fail due to `Conflicting lock is held` error
  * **Cause**: Active database connection held by IDE (VS Code, Windsurf, DBeaver)
  * **Solution**: Close all database connections in other tools before running simulation
  * **Check**: `planwise health` will detect active locks

### **Enrollment Architecture**

  * **Problem**: Duplicate enrollment events across years or missing enrollment dates
  * **Cause**: Circular dependencies in enrollment tracking
  * **Solution**: Use `int_enrollment_state_accumulator` model with proper temporal state tracking
  * **Validation**: `dbt run --select validate_enrollment_architecture --vars "simulation_year: 2025"`

### **CLI Errors**

```bash
# Check system health
planwise health                      # Quick diagnostic

# Detailed system status
planwise status --detailed           # Full system information

# View checkpoints for recovery
planwise checkpoints list            # Available recovery points
planwise checkpoints status          # Recovery recommendations
```

-----

## **12. Project Status**

### **Completed Epics (Production-Ready)**

- ✅ **E068**: Performance Optimization - 2× improvement (285s → 150s), 375× with Polars mode
- ✅ **E069**: Batch Scenario Processing - Excel export with metadata, database isolation
- ✅ **E072**: Pipeline Modularization - 51% code reduction (2,478 → 1,220 lines), 6 focused modules
- ✅ **E074**: Enhanced Error Handling - Context-rich diagnostics, <5min bug diagnosis
- ✅ **E075**: Testing Infrastructure - 256 tests, fixture library, 90%+ coverage
- ✅ **E023**: Enrollment Architecture Fix - Temporal state accumulator pattern
- ✅ **E078**: Cohort Pipeline Integration - Polars event factory, multi-year termination fixes
- ✅ **E080**: Validation Model to Test Conversion - Converted 30 validation models to dbt tests, 90 passing tests, removed legacy validation code

### **Planned / Available**

- 🚀 **E076**: Polars State Accumulation Pipeline (RECOMMENDED NEXT)
  - **Impact**: 60-75% performance improvement (236s → 60-90s for 2-year simulation)
  - **Why**: State accumulation is 70% of runtime (23s per year)
  - **Effort**: 2-3 weeks
  - **Status**: Ready to start, no blockers
  - **See**: `/docs/EPIC_STATUS_SUMMARY.md` for detailed analysis

### **Blocked**

- ⚠️ **E073**: Config Module Refactoring - BLOCKED by inadequate test coverage
  - **Status**: Not started
  - **Blocker**: Only 10% test coverage, need 80%+ before refactoring
  - **Risk**: 1,208-line monolithic file with 977-line untested function
  - **Action Required**: Build comprehensive test coverage first (5-7 days)

- ⚠️ **E079**: Performance Architectural Simplification - BLOCKED by 60% regression
  - **Status**: Not started (epic document only, no implementation)
  - **Blocker**: Performance regression detected (261s → 419s for 5-year simulation)
  - **See**: `/docs/E079_PERFORMANCE_RESULTS.md` for detailed analysis
  - **Action Required**: Investigate and fix regression before proceeding

-----

## **13. Further Reading**

  * `/docs/architecture.md` – Deep-dive diagrams
  * `/docs/events.md` – Workforce event taxonomy
  * `/docs/guides/error_troubleshooting.md` – Comprehensive troubleshooting guide
  * `/tests/TEST_INFRASTRUCTURE.md` – Testing guide and fixture documentation
  * `/tests/QUICK_START.md` – Developer quick reference
  * [dbt Style Guide](https://docs.getdbt.com/docs/collaborate/style-guide)
  * [DuckDB Documentation](https://duckdb.org/docs/)
