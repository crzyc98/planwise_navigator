PlanWise Navigator – Claude Code-Generation Playbook

A comprehensive, opinionated reference for generating enterprise-grade, production-ready code for workforce simulation and event sourcing.

⸻

1  Purpose

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for PlanWise Navigator, Fidelity’s on-premises workforce-simulation platform.
Follow it verbatim to guarantee:
	•	Event-sourced architecture with immutable audit trails
	•	Modular, maintainable components with single-responsibility design
	•	Enterprise-grade transparency and reproducibility
	•	Production-ready deployment to analytics servers

⸻

2  System Overview

Layer	Technology	Version	Responsibility
Storage	DuckDB	1.0.0	Immutable event store; column-store OLAP engine
Transformation	dbt-core	1.8.8	Declarative SQL models, tests, documentation
Adapter	dbt-duckdb	1.8.1	Stable DuckDB integration
Orchestration	Dagster	1.8.12	Asset-based pipeline for simulation workflow
Dashboard	Streamlit	1.39.0	Interactive analytics and compensation tuning
Configuration	Pydantic	2.7.4	Type-safe config management with validation
Parameters	comp_levers.csv	Dynamic	Analyst-adjustable compensation parameters
Python	CPython	3.11.x	Long-term support version

<details>
<summary>Unified Simulation Pipeline</summary>

```
graph TD
    config[config/simulation_config.yaml] --> dagster[Dagster Pipeline]
    params[comp_levers.csv] --> parameters[int_effective_parameters]
    census[census_raw] --> baseline[int_baseline_workforce]
    baseline --> snapshot[prepare_year_snapshot]
    snapshot --> prev_year[int_previous_year_workforce]
    parameters --> events[Event Models]
    prev_year --> events[Event Models]
    events --> yearly_events[fct_yearly_events]
    yearly_events --> workforce[fct_workforce_snapshot]
    workforce --> state[simulation_year_state]
    state --> checks[Asset Checks]
    checks --> tuning[Compensation Tuning UI]
    tuning --> params
```

</details>



⸻

2.5  Event Sourcing Architecture

PlanWise Navigator implements enterprise-grade event sourcing with immutable audit trails:

**Event Types**:
- **HIRE**: New employee onboarding with UUID and timestamp
- **TERMINATION**: Employee departure with reason codes
- **PROMOTION**: Level/band changes with compensation adjustments
- **RAISE**: Salary modifications (COLA, merit, market adjustment)
- **BENEFIT_ENROLLMENT**: Plan participation changes

**Core Principles**:
- **Immutability**: Every event is permanently recorded with UUID
- **Auditability**: Complete workforce history reconstruction from events
- **Reproducibility**: Identical scenarios with same random seed
- **Transparency**: Full visibility into every simulation decision

**Modular Engines**:
- **Compensation Engine**: COLA, merit, and promotion-based adjustments with dynamic parameter resolution
- **Termination Engine**: Hazard-based turnover modeling
- **Hiring Engine**: Growth-driven recruitment with realistic sampling
- **Promotion Engine**: Band-aware advancement probabilities
- **Parameter Engine**: Analyst-driven compensation tuning via `comp_levers.csv`

**Snapshot Reconstruction**: Any workforce state can be instantly reconstructed from the event log for historical analysis and scenario validation.

⸻

3  Directory Layout

planwise_navigator/
├─ definitions.py                    # Dagster workspace entry point
├─ orchestrator/                     # Dagster pipeline code
│  ├─ simulation_pipeline.py        # Main simulation logic
│  ├─ assets/                        # Asset definitions
│  ├─ jobs/                          # Job workflows
│  └─ resources/                     # Shared resources (DuckDBResource)
├─ dbt/                              # dbt project
│  ├─ models/                        # SQL transformation models
│  │  ├─ staging/                    # Raw data cleaning (stg_*)
│  │  ├─ intermediate/               # Business logic (int_*)
│  │  └─ marts/                      # Final outputs (fct_*, dim_*)
│  ├─ seeds/                         # Configuration data (CSV)
│  └─ macros/                        # Reusable SQL functions
├─ streamlit_dashboard/              # Interactive dashboard
├─ config/                           # Configuration management
│  └─ simulation_config.yaml        # Simulation parameters
├─ scripts/                          # Utility scripts
├─ tests/                            # Comprehensive testing
├─ data/                             # Raw input files (git-ignored)
├─ .dagster/                         # Dagster home directory (git-ignored)
└─ simulation.duckdb                 # DuckDB database file (git-ignored)


⸻

4  Naming Conventions
	•	dbt models: tier_entity_purpose (e.g., fct_workforce_snapshot, int_termination_events).
	•	Event tables: fct_yearly_events (immutable), fct_workforce_snapshot (point-in-time).
	•	Modular operations: action_entity (e.g., clean_duckdb_data, run_year_simulation).
	•	Dagster assets: snake_case, descriptive (simulation_year_state, dbt_simulation_assets).
	•	Python: PEP 8; type-hints mandatory; Pydantic models for config.
	•	Configuration: snake_case in YAML, hierarchical structure.

⸻

5  Generation Workflow for Claude

Every feature request becomes a single Pull-Request with the checklist below.

	1.	Clarify scope – echo back requirements; call out unknowns.
	2.	Plan – update /docs/spec-${date}.md with the solution outline.
	3.	Generate code – create/modify dbt models, Dagster assets, or Python helpers.
	4.	Write tests – dbt schema.yml tests and Pytest for Python.
	5.	Self-review – run ./scripts/lint && ./scripts/test. All green or fix it.
	6.	Document – add docstrings and dbt doc blocks.
	7.	Commit – conventional commits (feat:, fix:, refactor:).
	8.	Open PR – attach spec link, screenshots, and test output.

⸻

6  Coding Standards

SQL (dbt)
	•	2-space indent, uppercase keywords, one clause per line.
	•	Avoid SELECT *; list columns.
	•	Use {{ ref() }} and CTEs for readability.

Python

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date

class EmployeeEvent(BaseModel):
    employee_id: str = Field(..., min_length=1)
    event_type: Literal["HIRE", "TERM", "PROMOTION", "RAISE"]
    effective_date: date

	•	Keep functions < 40 lines.
	•	Raise explicit exceptions—no bare except.

⸻

7  Testing Strategy

Layer	Framework	Minimum Coverage
dbt	built-in tests + dbt-unit-testing	90 % of models
Python	Pytest + pytest-dots	95 % lines
Dashboards	Cypress end-to-end (critical paths)	smoke


⸻

8  Data-Quality Gates
	1.	Row counts between raw & staged tables (accepted_diff_pct ≤ 0.5 %).
	2.	Primary keys uniqueness tests on every model.
	3.	Distribution drift – Kolmogorov-Smirnov vs baseline (alert ≥ 0.1 p-value).

⸻

9  Local Development Tips

# Environment Setup (REQUIRED)
# DAGSTER_HOME is already set system-wide via launchctl: ~/dagster_home_planwise
# Verify with: launchctl getenv DAGSTER_HOME
# If not set, run: ./scripts/set_dagster_home.sh

# Python Environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start Dagster development server
dagster dev               # Start Dagster web server (http://localhost:3000)

# Run simulations
dagster asset materialize --select simulation_year_state  # Single year simulation
dagster asset materialize --select multi_year_simulation  # Multi-year simulation

# dbt Development
cd dbt
dbt run                   # Run all models
dbt run --select staging  # Run staging models only
dbt test                  # Run all tests
dbt docs generate         # Generate documentation
dbt docs serve            # Serve documentation

# Streamlit Dashboards
streamlit run streamlit_dashboard/main.py               # Launch main dashboard
streamlit run streamlit_dashboard/compensation_tuning.py # Launch compensation tuning interface (E012)

# Configuration Management
# Edit config/simulation_config.yaml for simulation parameters:
# - start_year, end_year
# - target_growth_rate
# - termination_rates
# - random_seed for reproducibility

# Asset-based Development Pattern
dagster asset materialize --select dbt_models             # Run all dbt models
dagster asset materialize --select workforce_simulation   # Run simulation assets
dagster asset materialize --select dashboard_data        # Prepare dashboard data

# Data Quality Checks
dagster asset check --select validate_data_quality       # Run data quality checks
dagster asset check --select validate_simulation_results # Validate simulation outputs

⸻

9.5  Epic E012: Compensation Tuning System

**Purpose**: Enables analysts to dynamically adjust compensation parameters through a UI to hit budget targets, eliminating the need for code changes and deployments.

**Architecture**:
```
Analyst → Streamlit UI → comp_levers.csv → int_effective_parameters → Event Models → Simulation Results
```

**Key Components**:
- **`comp_levers.csv`**: 126 parameter entries covering all job levels (1-5) and years (2025-2029)
- **`int_effective_parameters.sql`**: Dynamic parameter resolution model
- **`compensation_tuning.py`**: Full-featured Streamlit interface for parameter adjustment
- **Enhanced Event Models**: Merit, hiring, and promotion models now read from dynamic parameters

**Parameter Categories**:
- **Merit Rates**: `merit_base` by job level (e.g., Level 1: 4%, Level 5: 2%)
- **COLA Rates**: `cola_rate` applied uniformly (e.g., 2% across all levels)
- **New Hire Adjustments**: `new_hire_salary_adjustment` multiplier (e.g., 115% of base)
- **Promotion Rates**: `promotion_probability` and `promotion_raise` by level

**Streamlit Interface Features**:
- **Parameter Controls**: Sliders for all compensation parameters with real-time validation
- **Application Modes**: Single year vs. All Years (2025-2029) parameter application
- **Random Seed Control**: Reproducible simulation results with default (42), custom, or random seeds
- **Impact Analysis**: Real-time parameter change preview with estimated growth impact
- **Employment Status Filtering**: Granular workforce analysis using `detailed_status_code`:
  - `continuous_active`: Existing employees who remain active
  - `experienced_termination`: Existing employees who terminated this year
  - `new_hire_active`: New hires who remain active
  - `new_hire_termination`: New hires terminated in same year
- **Multi-Method Simulation**: Dagster CLI → Asset-based → Manual dbt fallback execution
- **Results Visualization**: Year-by-year breakdown with status composition charts

**Critical Implementation Patterns**:
```python
# Parameter Application (All Years Mode)
target_years = [2025, 2026, 2027, 2028, 2029] if apply_mode == "All Years" else [selected_year]
update_parameters_file(proposed_params, target_years)

# Employment Status Filtering
result = conn.execute(f"""
    SELECT COUNT(*), AVG(current_compensation)
    FROM fct_workforce_snapshot
    WHERE simulation_year = ? AND detailed_status_code IN ({status_placeholders})
""", [year] + status_filter).fetchone()

# Multi-Method Simulation Execution
try:
    # Method 1: Dagster CLI execution
    cmd = [dagster_cmd, "job", "execute", "--job", "multi_year_simulation", "-f", "definitions.py", "--config", config_file]
    result = subprocess.run(cmd, ...)
except:
    # Method 2: Asset-based simulation
    # Method 3: Manual dbt execution
```

**Database Lock Handling**:
```python
if "Conflicting lock is held" in dbt_result.stdout:
    st.error("🔒 Database Lock Error:")
    st.error("Please close any database connections in Windsurf/VS Code and try again.")
```

**Story Implementation Status**:
- ✅ **S043**: Parameter foundation (`comp_levers.csv`) - Complete
- ✅ **S044**: Dynamic parameter integration into models - Complete
- ✅ **S046**: Streamlit analyst interface - Complete
- 📋 **S045**: Dagster tuning loops - Planned (auto-optimization)
- 📋 **S047**: SciPy optimization engine - Planned (goal-seeking)

**Performance Characteristics**:
- Parameter validation: Instant
- Single simulation: 2-5 minutes
- Parameter impact preview: Real-time
- Database queries: <100ms for workforce metrics

**Common Issues & Solutions**:
- **Multi-year Data Persistence**: Use `full_refresh: False` in job configuration
- **Database Locks**: Close IDE database connections before simulation
- **Parameter Validation**: Built-in warnings for budget/retention risks
- **Dagster CLI Issues**: Multiple fallback execution methods implemented

⸻

10  Common Troubleshooting Patterns

# DuckDB Serialization Issues (CRITICAL)
- **Problem**: DuckDB Relation objects are NOT serializable by Dagster
- **Solution**: Always convert to pandas DataFrames or Python primitives before returning from assets
- **Pattern**: Use `.df()` method on DuckDB query results and context managers for connections
```python
# ✅ CORRECT: DuckDB Asset Pattern
@asset
def workforce_data(context: AssetExecutionContext, duckdb: DuckDBResource) -> pd.DataFrame:
    with duckdb.get_connection() as conn:
        # ✅ Convert immediately to DataFrame - serializable
        df = conn.execute("SELECT * FROM employees").df()
        return df  # Safe to return

# ❌ WRONG: Never return DuckDB objects
@asset
def broken_asset():
    conn = duckdb.connect("db.duckdb")
    return conn.table("employees")  # DuckDBPyRelation - NOT SERIALIZABLE!
```

# Environment and Database Paths (CRITICAL)
- **Database Location**: `/Users/nicholasamaral/planwise_navigator/simulation.duckdb`
- **Schema**: `main` (always use this schema)
- **dbt Commands**: Run from `/Users/nicholasamaral/planwise_navigator/dbt`
- **Dagster Commands**: Run from `/Users/nicholasamaral/planwise_navigator/`
- **Start Simulation**: `make run-simulation` (launches Dagster UI)
- **Multi-year Simulation**: Use Dagster UI to run `multi_year_simulation` asset

# Database State Management
- **Persistence**: DuckDB file persists between sessions
- **Key Tables**: `fct_workforce_snapshot`, `fct_yearly_events`, `scd_workforce_state`
- **Clean Data**: Use `clean_duckdb_data()` operation to reset simulation years
- **Snapshots**: Required for multi-year dependencies via `int_workforce_previous_year`

# Connection Management Patterns
- **Problem**: DuckDB connections must be properly managed
- **Solution**: Always use context managers for database connections
- **Pattern**: Use DuckDBResource.get_connection() with context manager
```python
with duckdb_resource.get_connection() as conn:
    # All database operations here
    result = conn.execute(query).df()
# Connection automatically closed
```

# Configuration Validation
- **Problem**: Invalid configuration parameters cause runtime errors
- **Solution**: Use Pydantic models for type-safe configuration validation
- **Pattern**: Define comprehensive validation rules
```python
class SimulationConfig(BaseModel):
    start_year: int = Field(..., ge=2020, le=2050)
    target_growth_rate: float = Field(0.03, ge=-0.5, le=0.5)
    random_seed: Optional[int] = Field(None, ge=1)
```

# Cumulative Growth Calculations
- **Problem**: Incorrect year-over-year growth showing flat numbers
- **Solution**: Calculate cumulative events from all previous years, not just current year
```python
# WRONG: Calculate from baseline each year
current_active = baseline_count + current_year_hires - current_year_terminations

# CORRECT: Calculate cumulative from all events up to current year
cumulative_events = conn.execute("""
    SELECT
        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) as total_hires,
        SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) as total_terminations
    FROM fct_yearly_events
    WHERE simulation_year <= ?
""", [year]).fetchone()
current_active = baseline_count + total_hires - total_terminations
```

# Multi-Year Simulation Dependencies
- **Problem**: Incremental models not persisting between years
- **Solution**: Use robust fallback validation that works with both table and event-based metrics
- **Pattern**: Always validate previous year data exists before running subsequent years

# Environment Variable Issues
- **Problem**: Temporary .tmp_dagster_home_* directories cluttering project
- **Solution**: DAGSTER_HOME is set system-wide via launchctl
- **Verification**: `launchctl getenv DAGSTER_HOME` should return `~/dagster_home_planwise`
- **Setup**: Run `./scripts/set_dagster_home.sh` to configure system-wide environment

# Version Compatibility Issues
- **Problem**: Incompatible versions causing runtime errors
- **Solution**: Use only proven stable versions from PRD v3.0
- **Versions**: DuckDB 1.0.0, dbt-core 1.8.8, dbt-duckdb 1.8.1, Dagster 1.8.12, Streamlit 1.39.0
- **Pattern**: Lock all dependency versions in requirements.txt

# Compensation Tuning Interface Issues (E012)
- **Problem**: Streamlit subprocess execution fails to find Dagster binary
- **Solution**: Multiple fallback paths and detailed error logging
```python
dagster_paths = [
    "venv/bin/dagster",      # Relative to project root
    "dagster",               # System path
    "/usr/local/bin/dagster" # Common system location
]
```

- **Problem**: Multi-year simulations only persisting final year data
- **Solution**: Set `full_refresh: False` in job configuration
```yaml
ops:
  run_multi_year_simulation:
    config:
      full_refresh: False  # Critical for data persistence
```

- **Problem**: Parameter changes not reflected in simulation results
- **Solution**: Clear Streamlit cache after parameter updates
```python
load_simulation_results.clear()  # Force cache refresh
```

- **Problem**: DuckDB database locked by IDE preventing simulations
- **Solution**: Enhanced error detection and user guidance
```python
if "Conflicting lock is held" in result.stdout:
    st.error("🔒 Database Lock Error: Close IDE database connections")
```

⸻

11  Deployment

The CI pipeline (GitHub Actions) performs:
	1.	Lint → Pytest → dbt build –fail-fast
	2.	Dagster asset warm-up
	3.	Tag & release Docker image ghcr.io/fidelity/planwise:${sha}
	4.	ansible playbook updates on-prem server (zero-downtime blue-green).

⸻

12  Contribution Checklist
	•	Spec updated
	•	Code & tests added
	•	Docs & examples written
	•	./scripts/lint && ./scripts/test pass
	•	PR description complete

⸻

13  Further Reading
	•	/docs/architecture.md – deep-dive diagrams
	•	/docs/events.md – workforce event taxonomy
	•	Dagster docs → https://docs.dagster.io/
	•	dbt style guide → https://docs.getdbt.com/docs/collaborate/style-guide

⸻

When in doubt: ask questions before you code. Precision beats assumption.
