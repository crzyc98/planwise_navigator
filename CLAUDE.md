# Fidelity PlanAlign Engine – Claude Code-Generation Playbook

A comprehensive, opinionated reference for generating enterprise-grade, production-ready code for workforce simulation and event sourcing.

-----

## **1. Purpose**

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for Fidelity PlanAlign Engine, Fidelity's on-premises workforce-simulation platform. Follow it verbatim to guarantee:

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
| **Orchestration** | planalign_orchestrator | Modular | PipelineOrchestrator with staged workflow execution |
| **CLI Interface** | planalign_cli (Rich + Typer) | 1.0.0 | Beautiful terminal interface with progress tracking |
| **Web Studio** | FastAPI + React/Vite | 0.1.0 | Modern web-based scenario management |
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
planalign health                                 # System readiness check
planalign simulate 2025-2027                     # Multi-year simulation
planalign batch --scenarios baseline high_growth # Batch processing
planalign status --detailed                      # Full system diagnostic

# Development workflow
planalign simulate 2025 --dry-run               # Preview execution plan
planalign simulate 2025 --verbose               # Detailed logging
planalign checkpoints list                      # View recovery points

# Launch PlanAlign Studio (web interface)
planalign studio                                 # Start API + frontend, opens browser
planalign studio --api-only                      # Start only the API backend
planalign studio --verbose                       # Show server output

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

Fidelity PlanAlign Engine implements enterprise-grade event sourcing with immutable audit trails.

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

**Event Type Abstraction Layer (E004)**:

The event type abstraction layer enables adding new workforce event types by implementing a single interface and registering in one location.

```python
from planalign_orchestrator.generators import (
    EventGenerator,
    EventRegistry,
    EventContext,
    ValidationResult,
)

# Register a new event type with decorator
@EventRegistry.register("sabbatical")
class SabbaticalEventGenerator(EventGenerator):
    event_type = "sabbatical"
    execution_order = 35  # Determines execution sequence
    requires_hazard = False
    supports_sql = True
    supports_polars = False

    def generate_events(self, context: EventContext):
        # Implementation (SQL mode delegates to dbt models)
        return []

    def validate_event(self, event):
        # Validation logic
        return ValidationResult(is_valid=True)

# List all registered event types
EventRegistry.list_all()  # ['enrollment', 'hire', 'merit', 'promotion', 'sabbatical', 'termination']

# Get generators by execution order
EventRegistry.list_ordered("baseline")  # Returns generators sorted by execution_order

# Disable event type for specific scenario
EventRegistry.disable("sabbatical", scenario_id="baseline")
```

**Key Components**:
- `EventGenerator`: Abstract base class with `generate_events()` and `validate_event()` methods
- `EventRegistry`: Centralized registration and lookup with scenario-specific enable/disable
- `HazardBasedEventGeneratorMixin`: Mixin for hazard probability-based event selection
- `EventContext`: Runtime context with simulation year, config, and database access
- `GeneratorMetrics`: Structured logging output for observability

-----

## **5. Directory Structure**

```
planalign_engine/
├─ planalign_orchestrator/           # Production orchestration engine
│  ├─ pipeline/                      # Modular pipeline components (E072)
│  │  ├─ workflow.py                # Stage definitions and workflow building
│  │  ├─ state_manager.py           # Checkpoint and state management
│  │  ├─ year_executor.py           # Stage-by-stage execution orchestration
│  │  ├─ event_generation_executor.py # Hybrid SQL/Polars event generation
│  │  ├─ hooks.py                   # Extensible callback system
│  │  └─ data_cleanup.py            # Database cleanup operations
│  ├─ generators/                    # Event type abstraction layer (E004)
│  │  ├─ base.py                    # EventGenerator ABC, mixins, dataclasses
│  │  ├─ registry.py                # EventRegistry singleton
│  │  ├─ termination.py             # Termination event wrapper
│  │  ├─ hire.py                    # Hire event wrapper
│  │  ├─ promotion.py               # Promotion event wrapper
│  │  ├─ merit.py                   # Merit event wrapper
│  │  ├─ enrollment.py              # Enrollment event wrapper
│  │  └─ sabbatical.py              # Example new event type
│  ├─ pipeline_orchestrator.py      # Main orchestrator (1,220 lines)
│  ├─ config.py                     # SimulationConfig management
│  ├─ dbt_runner.py                 # DbtRunner with streaming output
│  ├─ exceptions.py                 # Enhanced error handling (E074)
│  ├─ error_catalog.py              # Pattern-based error recognition
│  └─ validation.py                 # Data quality validation
├─ planalign_cli/                     # Rich-based CLI (primary interface)
│  ├─ commands/                      # Command implementations
│  │  ├─ simulate.py                # Multi-year simulation
│  │  ├─ batch.py                   # Batch scenario processing
│  │  ├─ status.py                  # System health and status
│  │  ├─ checkpoint.py              # Checkpoint management
│  │  └─ studio.py                  # Launch API + frontend servers
│  └─ main.py                       # CLI entry point
├─ planalign_api/                     # FastAPI backend for PlanAlign Studio
│  ├─ main.py                        # FastAPI application entry point
│  ├─ routers/                       # API route handlers
│  ├─ services/                      # Business logic services
│  └─ websocket/                     # Real-time telemetry handlers
├─ planalign_studio/                  # React/Vite frontend
│  ├─ components/                    # React components
│  ├─ services/                      # API client services
│  └─ package.json                   # Frontend dependencies
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
from planalign_orchestrator.pipeline import (
    WorkflowBuilder,      # Stage definitions and workflow building
    StateManager,         # Checkpoint and state management
    YearExecutor,         # Stage-by-stage execution orchestration
    EventGenerationExecutor,  # Hybrid SQL/Polars event generation
    HookManager,          # Extensible callback system
    DataCleanupManager    # Database cleanup operations
)

from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator

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
from planalign_orchestrator.exceptions import (
    NavigatorError,       # Base exception with execution context
    DatabaseError,        # Database operations
    ConfigurationError,   # Config validation
    PipelineError,        # Pipeline execution
    DbtError,             # dbt command failures
    ResourceError,        # Resource constraints
    StateError            # State management
)

from planalign_orchestrator.error_catalog import ErrorCatalog

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
pytest --cov=planalign_orchestrator \
       --cov=planalign_cli \
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
from planalign_orchestrator.config import get_database_path
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

## **9.1 Age/Tenure Band Configuration**

Age and tenure bands are centralized in dbt seeds with reusable macros for consistent band assignment across all models.

### **Band Assignment Macros**

```sql
-- Assign age band to any age column
{{ assign_age_band('current_age') }} AS age_band

-- Assign tenure band to any tenure column
{{ assign_tenure_band('current_tenure') }} AS tenure_band
```

### **Configuration Seeds**

| Seed File | Purpose |
|-----------|---------|
| `dbt/seeds/config_age_bands.csv` | Age band boundaries (0-25, 25-35, 35-45, 45-55, 55-65, 65+) |
| `dbt/seeds/config_tenure_bands.csv` | Tenure band boundaries (0-2, 2-5, 5-10, 10-20, 20+) |

### **[min, max) Interval Convention**

Bands use **lower bound inclusive, upper bound exclusive**:
- Age 35 → `35-44` band (not `25-34`)
- Tenure 2.0 years → `2-4` band (not `< 2`)

### **PlanAlign Studio Band Configuration UI (E003)**

The web interface provides a visual editor for managing band configurations:

**Features:**
- **View Bands**: Display age and tenure band definitions in editable tables
- **Edit Bands**: Modify band boundaries and labels with inline editing
- **Real-time Validation**: Instant feedback for gaps, overlaps, and invalid ranges
- **Match Census**: Analyze census data to suggest optimal band boundaries

**Access:**
1. Launch PlanAlign Studio: `planalign studio`
2. Open a workspace
3. Navigate to "Configuration" → "Workforce Segmentation"

**API Endpoints:**
- `GET /api/workspaces/{workspace_id}/config/bands` - Get current band configurations
- `PUT /api/workspaces/{workspace_id}/config/bands` - Save band configurations
- `POST /api/workspaces/{workspace_id}/analyze-age-bands` - Suggest age bands from census
- `POST /api/workspaces/{workspace_id}/analyze-tenure-bands` - Suggest tenure bands from census

**Match Census Algorithm:**
Uses percentile-based boundary detection to suggest bands that follow data distribution:
- Age bands (6 bands): 0%, 10%, 25%, 50%, 75%, 90%, 100% percentiles
- Tenure bands (5 bands): 0%, 20%, 40%, 60%, 80%, 100% percentiles

**Validation Rules:**
- First band must start at 0
- Each band's max_value must be greater than min_value
- No gaps allowed between consecutive bands
- No overlapping ranges
- Saved bands are automatically loaded at simulation start

### **Modifying Bands (CLI Method)**

1. Edit the CSV seed file (`config_age_bands.csv` or `config_tenure_bands.csv`)
2. Run `dbt seed --threads 1` to load changes
3. Run `dbt test --select stg_config_age_bands stg_config_tenure_bands --threads 1` to validate
4. Run `dbt build --threads 1` to rebuild all models

### **Validation Tests**

- `test_age_band_no_gaps.sql` - Ensures no gaps between age bands
- `test_age_band_no_overlaps.sql` - Ensures age bands don't overlap
- `test_tenure_band_no_gaps.sql` - Ensures no gaps between tenure bands
- `test_tenure_band_no_overlaps.sql` - Ensures tenure bands don't overlap

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
planalign batch

# Run specific scenarios with clean start
planalign batch --scenarios baseline high_growth --clean

# Export to Excel with metadata
planalign batch --export-format excel

# Batch creates timestamped directories with:
# - Individual scenario databases (scenario_name.duckdb)
# - Excel exports with workforce snapshots, metrics, events
# - Metadata sheets with git SHA, seed, configuration
# - Comparison reports across scenarios
```

### **PlanAlign Studio (Web Interface)**

Launch the modern web-based scenario management interface:

```bash
# Launch both API backend and React frontend
planalign studio

# Options
planalign studio --api-port 8001        # Custom API port (default: 8000)
planalign studio --frontend-port 3000   # Custom frontend port (default: 5173)
planalign studio --api-only             # Start only the API backend
planalign studio --frontend-only        # Start only the frontend
planalign studio --no-browser           # Don't auto-open browser
planalign studio --verbose              # Show detailed server output
```

**Components:**
- **API Backend** (FastAPI): `http://localhost:8000`
  - REST API for workspaces, scenarios, and simulations
  - WebSocket support for real-time telemetry
  - API docs at `http://localhost:8000/api/docs`
- **Frontend** (React/Vite): `http://localhost:5173`
  - Modern scenario management interface
  - Real-time simulation progress tracking
  - Scenario comparison tools

**Stopping**: Press `Ctrl+C` to gracefully stop all services.

-----

## **11. Troubleshooting**

### **Database and Path Issues**

  * **Database Location**: `dbt/simulation.duckdb` (standardized location)
  * **dbt Commands**: Always run from `/dbt` directory
  * **Database Access**: Always use `get_database_path()` from `planalign_orchestrator.config`

```python
# CORRECT pattern
from planalign_orchestrator.config import get_database_path
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
  * **Check**: `planalign health` will detect active locks

### **Enrollment Architecture**

  * **Problem**: Duplicate enrollment events across years or missing enrollment dates
  * **Cause**: Circular dependencies in enrollment tracking
  * **Solution**: Use `int_enrollment_state_accumulator` model with proper temporal state tracking
  * **Validation**: `dbt run --select validate_enrollment_architecture --vars "simulation_year: 2025"`

### **SQLParse Token Limit Error**

  * **Problem**: Multi-year simulations fail on Year 2+ with `Maximum number of tokens exceeded (10000)`
  * **Cause**: sqlparse 0.5.4+ has DoS protection that limits SQL parsing to 10,000 tokens
  * **Affected Models**: `fct_workforce_snapshot.sql` compiles to ~13,668 tokens in Year 2+
  * **Solution**: **Automatic** - the fix is auto-installed on first import of `planalign_orchestrator`

```bash
# The fix auto-installs on first import. Just run any planalign command:
planalign health

# Or import the package in Python:
python -c "import planalign_orchestrator"

# Verify the fix (in a new terminal/Python process):
python -c "import sqlparse.engine.grouping; print(f'MAX_GROUPING_TOKENS={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}')"
# Expected output: MAX_GROUPING_TOKENS=50000
```

  * **How It Works**: On first import, `planalign_orchestrator.sqlparse_config` auto-installs a `.pth` file to site-packages that sets `MAX_GROUPING_TOKENS = 50000` when Python starts. This applies to all Python processes in the venv, including dbt subprocesses.
  * **Re-installation**: After recreating the virtual environment (`uv venv && pip install -e .`), just import the package once to trigger auto-install.

### **CLI Errors**

```bash
# Check system health
planalign health                      # Quick diagnostic

# Detailed system status
planalign status --detailed           # Full system information

# View checkpoints for recovery
planalign checkpoints list            # Available recovery points
planalign checkpoints status          # Recovery recommendations
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
- ✅ **E083**: Workspace Cloud Synchronization - Git-based sync with audit trails
- ✅ **E080**: Validation Model to Test Conversion - Converted 30 validation models to dbt tests, 90 passing tests, removed legacy validation code
- ✅ **E073**: Config Module Refactoring - Split 1,471-line config.py into 7 focused modules
- ✅ **E076**: Polars State Accumulation Pipeline - 60-75% performance improvement achieved
- ✅ **E077**: Bulletproof Workforce Growth Accuracy - Deterministic growth with algebraic solver
- ✅ **E082**: Configurable New Hire Demographics - Age/level distribution via seeds + UI
- ✅ **E084**: Configurable DC Plan Match Formulas - UI config, editable match tiers, graded core by service
- ✅ **E014**: Layered Defense Strategy - Achieved via E075/E080/E074 testing infrastructure

### **Planned / Available**

- No active epics - project feature-complete for MVP

### **Superseded**

- ⚠️ **E078**: Cohort Pipeline Integration - SUPERSEDED by E076
  - **Original Goal**: Mode-aware model references for Polars compatibility (2-5× improvement)
  - **Resolution**: E076 achieves 1000x+ improvement, making E078 unnecessary
  - **Status**: Partial implementation reverted; SQL mode default

- ⚠️ **E079**: Performance Architectural Simplification - SUPERSEDED by E076
  - **Original Problem**: 60% performance regression (261s → 419s)
  - **Resolution**: E076 Polars pipeline achieved 1000x+ improvement (0.22s for 2-year simulation)
  - **Status**: No longer needed - Polars bypasses dbt bottlenecks

-----

## **13. Versioning**

Fidelity PlanAlign Engine follows **Semantic Versioning 2.0.0** (MAJOR.MINOR.PATCH):

- **Current Version**: 1.0.0 ("Foundation")
- **View Version**: `planalign --version` or `planalign health`
- **Version Module**: `_version.py` (centralized version management)

**When to Increment:**
- **MAJOR**: Breaking changes (config schema, database schema, API changes)
- **MINOR**: New features/epics (E076, E077, etc.)
- **PATCH**: Bug fixes, docs, tests

**Version Update Process:**
1. Update `_version.py` (version, release_date, release_name)
2. Update `pyproject.toml` (line 3)
3. Update `CHANGELOG.md` with changes
4. Commit: `git commit -m "chore: Bump version to X.Y.Z"`
5. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
6. Reinstall: `uv pip install -e .`

See `/docs/VERSIONING_GUIDE.md` for detailed versioning workflow.

-----

## **14. Further Reading**

  * `/docs/VERSIONING_GUIDE.md` – Complete versioning workflow and best practices
  * `/CHANGELOG.md` – Version history and release notes
  * `/docs/architecture.md` – Deep-dive diagrams
  * `/docs/events.md` – Workforce event taxonomy
  * `/docs/guides/error_troubleshooting.md` – Comprehensive troubleshooting guide
  * `/tests/TEST_INFRASTRUCTURE.md` – Testing guide and fixture documentation
  * `/tests/QUICK_START.md` – Developer quick reference
  * [Semantic Versioning](https://semver.org/)
  * [dbt Style Guide](https://docs.getdbt.com/docs/collaborate/style-guide)
  * [DuckDB Documentation](https://duckdb.org/docs/)

## Active Technologies
- SQL (DuckDB 1.0.0), dbt-core 1.8.8 + dbt-duckdb 1.8.1, DuckDB (001-centralize-band-definitions)
- DuckDB (dbt/simulation.duckdb) (001-centralize-band-definitions)
- Python 3.11, SQL (DuckDB 1.0.0) + dbt-core 1.8.8, dbt-duckdb 1.8.1, Polars (002-fix-auto-escalation-hire-filter)
- Python 3.11 (backend), TypeScript 5.x (frontend) + FastAPI (backend), React 18 + Vite (frontend), Pydantic v2 (validation) (003-studio-band-config)
- CSV files (dbt seeds: `config_age_bands.csv`, `config_tenure_bands.csv`), Parquet (census data) (003-studio-band-config)
- Python 3.11 + Pydantic v2 (validation), dbt-core 1.8.8 (SQL transforms), Polars 1.0+ (high-performance mode) (004-event-type-abstraction)
- DuckDB 1.0.0 (immutable event store at `dbt/simulation.duckdb`) (004-event-type-abstraction)
- Python 3.11 + Pydantic v2 (validation), FastAPI (dependency injection context), pathlib (path handling) (005-database-path-resolver)
- DuckDB databases at multiple levels (scenario, workspace, project) (005-database-path-resolver)
- Python 3.11 + Pydantic v2 (type-safe contracts), existing `planalign_orchestrator` modules (007-state-accumulator-contract)
- DuckDB 1.0.0 (existing `dbt/simulation.duckdb`) (007-state-accumulator-contract)
- Python 3.11, SQL (DuckDB 1.0.0) + dbt-core 1.8.8, dbt-duckdb 1.8.1, Hypothesis (property-based testing), pytest (008-irs-402g-limits-hardening)
- DuckDB (`dbt/simulation.duckdb`) (008-irs-402g-limits-hardening)
- SQL (DuckDB 1.0.0), dbt-core 1.8.8 + dbt-duckdb 1.8.1 + dbt, DuckDB, existing `int_employer_core_contributions.sql` model (009-fix-service-based-core-contribution)
- Python 3.11 (orchestrator), SQL/Jinja (dbt models), TypeScript 5.x (frontend) + dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2, React 18 (010-fix-match-service-tiers)
- Python 3.11 + sqlparse 0.5.4+, dbt-core 1.8.8, dbt-duckdb 1.8.1 (011-sqlparse-token-limit-fix)
- DuckDB 1.0.0 (dbt/simulation.duckdb) (011-sqlparse-token-limit-fix)
- Python 3.11 + pathlib (stdlib), Typer (CLI), Pydantic v2 (config), DuckDB (storage) (012-polars-path-fixes)
- DuckDB databases (scenario-specific), Parquet files (Polars output) (012-polars-path-fixes)

## Recent Changes
- 001-centralize-band-definitions: Added SQL (DuckDB 1.0.0), dbt-core 1.8.8 + dbt-duckdb 1.8.1, DuckDB
