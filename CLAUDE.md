PlanWise Navigator – Claude Code-Generation Playbook

A comprehensive, opinionated reference for generating enterprise-grade, production-ready code for workforce simulation and event sourcing.

⸻

1  Purpose

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for PlanWise Navigator, Fidelity's on-premises workforce-simulation platform.
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
Context	Context7 MCP	Latest	Extended context management and tool integration

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
- **DC PLAN EVENTS** (S072-03): Eligibility, enrollment, contributions, vesting
- **PLAN ADMINISTRATION EVENTS** (S072-04): Forfeitures, HCE determination, compliance monitoring

**Unified Event Model** (NEW - S072-01):
- **SimulationEvent**: Core event model using Pydantic v2 with discriminated unions
- **Required Context**: `scenario_id`, `plan_design_id` for proper event isolation
- **EventFactory**: Type-safe event creation with comprehensive validation
- **Performance**: <5ms validation, 1000 events/second creation rate

**Core Principles**:
- **Immutability**: Every event is permanently recorded with UUID
- **Auditability**: Complete workforce history reconstruction from events
- **Reproducibility**: Identical scenarios with same random seed
- **Transparency**: Full visibility into every simulation decision
- **Type Safety**: Pydantic v2 validation on all event payloads

**Modular Engines**:
- **Compensation Engine**: COLA, merit, and promotion-based adjustments with dynamic parameter resolution
- **Termination Engine**: Hazard-based turnover modeling
- **Hiring Engine**: Growth-driven recruitment with realistic sampling
- **Promotion Engine**: Band-aware advancement probabilities
- **Parameter Engine**: Analyst-driven compensation tuning via `comp_levers.csv`
- **DC Plan Engine**: Retirement plan contribution, vesting, and distribution modeling (S072-03)
- **Plan Administration Engine** (NEW - S072-04): Forfeiture processing, HCE determination, and IRS compliance monitoring

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
│  ├─ simulation_config.yaml        # Simulation parameters
│  ├─ schema.py                     # Legacy event schema (Pydantic v1)
│  └─ events.py                     # Unified event model (Pydantic v2)
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

# Context Management
# Context7 MCP server provides extended context management and tool integration
# Use context7 tools for enhanced codebase understanding and navigation

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

14  Memory of Actions

• Added a memory section to track key actions and interactions with the project
• Implemented memory tracking for future reference and project continuity

When in doubt: ask questions before you code. Precision beats assumption.

## Troubleshooting: Virtual Environment Issues

**Problem**: `ModuleNotFoundError: No module named 'dbt.cli'` when running dagster commands

**Root Cause**: Using system-installed dagster (`/opt/homebrew/bin/dagster`) instead of virtual environment's dagster

**Solution**:
1. Always activate virtual environment first:
   ```bash
   source venv/bin/activate
   ```

2. Or use virtual environment's dagster directly:
   ```bash
   venv/bin/dagster asset materialize --select advanced_optimization_engine -f definitions.py
   ```

**Current Working Versions**:
- dbt-core: 1.9.8
- dagster: 1.10.21
- dagster-dbt: 0.26.21

These versions are compatible and work correctly together.

## Epic E013 - S013-01: dbt Command Utility Enhancement (COMPLETED)

**Status**: ✅ **COMPLETED** - Enhanced dbt command utility with streaming support

**Changes Made**:
1. **Extended `execute_dbt_command` utility** in `orchestrator/simulator_pipeline.py`:
   - Added `execute_dbt_command_streaming()` function for streaming operations
   - Supports same parameter interface as original function
   - Handles long-running operations like `dbt build` with streaming output

2. **Migrated non-centralized patterns**:
   - `orchestrator/assets.py`: Now uses `execute_dbt_command_streaming()` for dbt build
   - `orchestrator/repository.py`: Now uses `execute_dbt_command_streaming()` for dbt build

3. **Added comprehensive tests** in `tests/unit/test_execute_dbt_command.py`:
   - 6 new test cases for streaming functionality
   - Tests cover variables, full_refresh, error handling, and edge cases

**Key Functions**:
```python
# Original function (already existed)
execute_dbt_command(context, command, vars_dict, full_refresh, description)

# New streaming function
execute_dbt_command_streaming(context, command, vars_dict, full_refresh, description)
```

**Usage Pattern**:
```python
# For regular dbt commands
execute_dbt_command(context, ["run", "--select", "model"], {"year": 2025}, False, "model run")

# For streaming operations (long-running builds)
yield from execute_dbt_command_streaming(context, ["build"], {}, False, "full build")
```

**Result**: 100% centralization of dbt command execution with enhanced streaming support for long-running operations.

## dbt Contract Compliance Fix (RESOLVED)

**Issue**: Multi-year simulation failing with dbt contract error:
```
Contracted models require data_type to be defined for each column.
Please ensure that the column name and data_type are defined within the YAML configuration.
```

**Root Cause**: The `fct_yearly_events` model has `contract: {enforced: true}` but the schema.yml file was missing:
1. **data_type definitions** for all columns
2. **Complete column definitions** for all model outputs (14 additional columns)
3. **Correct data type mappings** for DuckDB type system

**Solution Applied**: Updated `/dbt/models/marts/schema.yml` for `fct_yearly_events`:

```yaml
columns:
  - name: employee_id
    data_type: varchar
  - name: employee_ssn
    data_type: varchar
  - name: event_type
    data_type: varchar
  - name: simulation_year
    data_type: integer
  - name: effective_date
    data_type: timestamp  # Changed from date
  - name: event_details
    data_type: varchar
  - name: compensation_amount
    data_type: double  # Changed from decimal
  - name: previous_compensation
    data_type: double  # Added missing column
  - name: employee_age
    data_type: bigint  # Changed from integer
  - name: employee_tenure
    data_type: bigint  # Added missing column
  - name: level_id
    data_type: integer
  - name: age_band
    data_type: varchar  # Added missing column
  - name: tenure_band
    data_type: varchar  # Added missing column
  - name: event_probability
    data_type: double  # Added missing column
  - name: event_category
    data_type: varchar  # Added missing column
  - name: event_sequence
    data_type: bigint  # Changed from integer
  - name: created_at
    data_type: timestamp with time zone  # Added missing column
  - name: parameter_scenario_id
    data_type: varchar  # Added missing column
  - name: parameter_source
    data_type: varchar  # Added missing column
  - name: data_quality_flag
    data_type: varchar  # Added missing column
```

**Key Changes**:
- Added **10 missing columns** to contract definition
- Fixed **4 data type mismatches** (timestamp vs date, double vs decimal, bigint vs integer)
- Maintained all existing data tests and constraints

**Status**: ✅ **RESOLVED** - Multi-year simulation now runs successfully with full dbt contract compliance

### **Additional Fix: fct_workforce_snapshot Contract Compliance**

**Second Issue**: After fixing `fct_yearly_events`, the `fct_workforce_snapshot` model had the same contract error.

**Solution Applied**: Updated schema.yml for `fct_workforce_snapshot` with:
- **All 17 columns** with proper `data_type` definitions
- **Corrected data types**: `employee_birth_date`, `employee_hire_date`, `termination_date` → `timestamp` (not `date`)
- **Added missing columns**: `prorated_annual_compensation`, `full_year_equivalent_compensation`, `age_band`, `tenure_band`, `snapshot_created_at`

**Final Status**: ✅ **FULLY RESOLVED** - Both `fct_yearly_events` and `fct_workforce_snapshot` models now have complete dbt contract compliance and run successfully together.

## Epic E020: Polars Integration - MVP Completed (2025-07-10)

**✅ S020-01: Polars Performance Proof of Concept - COMPLETED**

**Performance Results on 27,849 employee workforce dataset:**
```
Operation                 Pandas     Polars     Speedup
------------------------------------------------------------
Active Filter                 2.2ms    19.9ms     0.1x
Level Grouping                2.9ms     7.3ms     0.4x
Compensation Analysis         4.2ms     4.9ms     0.9x
Complex Aggregation           5.4ms     2.5ms     2.1x ⭐
------------------------------------------------------------
TOTAL                        14.8ms    34.6ms     0.4x
```

**Key Findings:**
- **Complex aggregations show 2.1x speedup** - Polars excels at multi-dimensional analytics
- **Simple operations favor pandas** on this dataset size (< 30k rows)
- **Polars version 1.31.0** installed and working with existing DuckDB infrastructure
- **Memory usage comparable** - no significant memory overhead
- **Business case established** for complex workforce analytics operations

**Implementation Details:**
- Zero changes to existing codebase - purely additive POC
- Benchmark script: `/scripts/polars_benchmark_poc.py`
- Tests against real `fct_workforce_snapshot` data (5 years, 27k+ employees)
- Uses existing DuckDB connection patterns from `orchestrator/resources/duckdb_resource.py`

**Next Steps Recommended:**
- Target Polars adoption for **complex multi-year simulations** where 2x+ speedups are evident
- Consider pandas→Polars migration for operations with >3 grouping dimensions
- Future stories should focus on eligibility calculations and complex regulatory computations
- Avoid Polars for simple filtering/basic aggregations until dataset size >100k employees

**Technical Environment:**
- Polars 1.31.0 successfully installed in existing virtual environment
- Compatible with DuckDB 1.0.0, pandas 2.0.0+, Dagster 1.10.21
- Zero conflicts with existing dependencies
- Ready for broader integration when business logic complexity justifies adoption

## Story S072-04: Plan Administration Events - COMPLETED (2025-07-11)

**✅ Implementation Status**: Fully implemented and tested with comprehensive validation

**Purpose**: Essential plan administration events for basic plan governance and compliance monitoring, including forfeiture processing, HCE determination, and IRS limit monitoring.

### **Core Event Payloads Implemented**

**ForfeiturePayload** - Unvested Employer Contribution Recapture:
```python
class ForfeiturePayload(BaseModel):
    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str = Field(..., min_length=1)
    forfeited_from_source: Literal[
        "employer_match", "employer_nonelective", "employer_profit_sharing"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    reason: Literal["unvested_termination", "break_in_service"]
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)
```

**HCEStatusPayload** - Highly Compensated Employee Determination:
```python
class HCEStatusPayload(BaseModel):
    event_type: Literal["hce_status"] = "hce_status"
    plan_id: str = Field(..., min_length=1)
    determination_method: Literal["prior_year", "current_year"]
    ytd_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    annualized_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    hce_threshold: Decimal = Field(..., gt=0, decimal_places=6)
    is_hce: bool
    determination_date: date
    prior_year_hce: Optional[bool] = None
```

**ComplianceEventPayload** - Basic IRS Limit Monitoring:
```python
class ComplianceEventPayload(BaseModel):
    event_type: Literal["compliance"] = "compliance"
    plan_id: str = Field(..., min_length=1)
    compliance_type: Literal[
        "402g_limit_approach",    # Approaching elective deferral limit
        "415c_limit_approach",    # Approaching annual additions limit
        "catch_up_eligible"       # Participant becomes catch-up eligible
    ]
    limit_type: Literal["elective_deferral", "annual_additions", "catch_up"]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    monitoring_date: date
```

### **Factory Integration**

**PlanAdministrationEventFactory** - Type-Safe Event Creation:
```python
# Create forfeiture event for unvested contributions
event = PlanAdministrationEventFactory.create_forfeiture_event(
    employee_id="EMP_001",
    plan_id="PLAN_001",
    scenario_id="SCENARIO_001",
    plan_design_id="DESIGN_001",
    forfeited_from_source="employer_match",
    amount=Decimal("2500.00"),
    reason="unvested_termination",
    vested_percentage=Decimal("0.40"),
    effective_date=date(2025, 3, 15)
)

# Create HCE status determination event
event = PlanAdministrationEventFactory.create_hce_status_event(
    employee_id="EMP_002",
    plan_id="PLAN_001",
    scenario_id="SCENARIO_001",
    plan_design_id="DESIGN_001",
    determination_method="prior_year",
    ytd_compensation=Decimal("130000.00"),
    annualized_compensation=Decimal("156000.00"),
    hce_threshold=Decimal("135000.00"),
    is_hce=True,
    determination_date=date(2025, 1, 1),
    prior_year_hce=False
)

# Create compliance monitoring event
event = PlanAdministrationEventFactory.create_compliance_monitoring_event(
    employee_id="EMP_003",
    plan_id="PLAN_001",
    scenario_id="SCENARIO_001",
    plan_design_id="DESIGN_001",
    compliance_type="catch_up_eligible",
    limit_type="catch_up",
    applicable_limit=Decimal("7500.00"),
    current_amount=Decimal("0.00"),
    monitoring_date=date(2025, 7, 1)
)
```

### **Integration with SimulationEvent**

**Discriminated Union Extension**: All 3 new payloads automatically integrated into the core `SimulationEvent` discriminated union:
```python
payload: Union[
    # Workforce Events
    Annotated[HirePayload, Field(discriminator='event_type')],
    Annotated[PromotionPayload, Field(discriminator='event_type')],
    Annotated[TerminationPayload, Field(discriminator='event_type')],
    Annotated[MeritPayload, Field(discriminator='event_type')],
    # DC Plan Events (S072-03)
    Annotated[EligibilityPayload, Field(discriminator='event_type')],
    Annotated[EnrollmentPayload, Field(discriminator='event_type')],
    Annotated[ContributionPayload, Field(discriminator='event_type')],
    Annotated[VestingPayload, Field(discriminator='event_type')],
    # Plan Administration Events (S072-04) - NEW
    Annotated[ForfeiturePayload, Field(discriminator='event_type')],
    Annotated[HCEStatusPayload, Field(discriminator='event_type')],
    Annotated[ComplianceEventPayload, Field(discriminator='event_type')],
] = Field(..., discriminator='event_type')
```

### **Enterprise-Grade Validation**

**Regulatory Compliance Features**:
- **Forfeiture Source Validation**: Only employer contribution sources allowed (`employer_match`, `employer_nonelective`, `employer_profit_sharing`)
- **HCE Determination Methods**: Support for both prior-year and current-year determination methods
- **IRS Limit Monitoring**: 402(g) elective deferral limits, 415(c) annual additions limits, catch-up eligibility tracking
- **Precision Standards**: 18,6 decimal precision for monetary amounts, 4 decimal places for percentages

**Validation Rules**:
- All monetary amounts must be positive (except current_amount ≥ 0 for compliance tracking)
- Vested percentages constrained to 0.0-1.0 range with 4 decimal precision
- Required plan_id linking for all administrative events
- Date validation for determination and monitoring dates
- Enum validation for all categorical fields

### **Comprehensive Testing Coverage**

**24 Unit Tests Implemented**:
- **Payload Validation**: 17 tests covering field validation, edge cases, and error conditions
- **Factory Methods**: 3 tests for type-safe event creation with proper context validation
- **Integration**: 4 tests for discriminated union routing, serialization, and deserialization

**Test Categories**:
```python
# Validation testing for each payload type
TestForfeiturePayload: 5 test cases
TestHCEStatusPayload: 5 test cases
TestComplianceEventPayload: 7 test cases

# Factory method testing
TestPlanAdministrationEventFactory: 3 test cases

# Integration testing
TestPlanAdministrationEventIntegration: 4 test cases
```

**Quality Assurance Results**:
- ✅ **24/24 tests passing**: 100% test success rate
- ✅ **Flake8 compliance**: No linting violations
- ✅ **MyPy validation**: Full type safety confirmed
- ✅ **Pre-commit hooks**: All code standards met

### **Architecture Integration**

**Event Sourcing Compatibility**:
- **Immutable Events**: All administrative events permanently recorded with UUID
- **Audit Trail**: Complete plan administration history reconstruction capability
- **Type Safety**: Pydantic v2 discriminated union automatic routing
- **Context Isolation**: Required `scenario_id` and `plan_design_id` for proper event isolation

**Source System Identification**:
- **plan_administration**: Forfeiture events
- **hce_determination**: HCE status events
- **compliance_monitoring**: IRS limit monitoring events

### **Usage Patterns**

**Common Administrative Scenarios**:
```python
# Scenario 1: Employee termination with forfeiture
forfeiture_event = PlanAdministrationEventFactory.create_forfeiture_event(
    employee_id="TERM_001",
    plan_id="401K_PLAN",
    scenario_id="SIMULATION_2025",
    plan_design_id="STANDARD_DESIGN",
    forfeited_from_source="employer_match",
    amount=Decimal("1245.67"),
    reason="unvested_termination",
    vested_percentage=Decimal("0.2500"),  # 25% vested
    effective_date=date(2025, 6, 30)
)

# Scenario 2: Annual HCE determination
hce_event = PlanAdministrationEventFactory.create_hce_status_event(
    employee_id="HCE_001",
    plan_id="401K_PLAN",
    scenario_id="SIMULATION_2025",
    plan_design_id="STANDARD_DESIGN",
    determination_method="prior_year",
    ytd_compensation=Decimal("125000.00"),
    annualized_compensation=Decimal("150000.00"),
    hce_threshold=Decimal("135000.00"),  # 2025 IRS threshold
    is_hce=True,
    determination_date=date(2025, 1, 1),
    prior_year_hce=False
)

# Scenario 3: 402(g) limit monitoring
compliance_event = PlanAdministrationEventFactory.create_compliance_monitoring_event(
    employee_id="LIMIT_001",
    plan_id="401K_PLAN",
    scenario_id="SIMULATION_2025",
    plan_design_id="STANDARD_DESIGN",
    compliance_type="402g_limit_approach",
    limit_type="elective_deferral",
    applicable_limit=Decimal("23000.00"),  # 2025 402(g) limit
    current_amount=Decimal("21500.00"),   # Approaching limit
    monitoring_date=date(2025, 11, 15)
)
```

### **Implementation Details**

**Files Modified/Created**:
- **config/events.py**: Added 3 new payload classes and PlanAdministrationEventFactory
- **tests/unit/test_plan_administration_events.py**: Comprehensive 24-test suite (NEW FILE)

**Code Quality Metrics**:
- **Lines Added**: 729 lines of production code and tests
- **Test Coverage**: 100% of new functionality tested
- **Type Safety**: Full Pydantic v2 validation with discriminated unions
- **Documentation**: Comprehensive docstrings and usage examples

**Performance Characteristics**:
- **Event Validation**: <5ms per event (Pydantic v2 optimization)
- **Factory Creation**: <1ms per event with full validation
- **Serialization**: Native Pydantic performance with proper decimal handling
- **Memory Usage**: Minimal overhead with efficient discriminated union routing

### **Regulatory Coverage**

**IRS Requirements Addressed**:
- **Section 402(g)**: Elective deferral limit monitoring and approach warnings
- **Section 415(c)**: Annual additions limit tracking for total plan contributions
- **Catch-up Contributions**: Age-based eligibility determination (50+ years old)

**ERISA Compliance Features**:
- **Forfeiture Allocation**: Proper tracking of unvested employer contribution recapture
- **HCE Testing**: Annual determination supporting nondiscrimination testing
- **Administrative Audit Trail**: Complete documentation for compliance reporting

**Future Enhancement Ready**:
- Event foundation supports advanced compliance features as needed
- Factory pattern ready for additional administrative event types
- Discriminated union architecture scales for complex regulatory scenarios

## Epic E021-A: DC Plan Event Schema Foundation - COMPLETED (2025-07-11)

**✅ Full Epic Status**: All stories completed with comprehensive enterprise-grade event schema

### **S072-06: Performance & Validation Framework - COMPLETED**

**Purpose**: Enterprise-grade performance and validation infrastructure ensuring production readiness with automated testing, monitoring, and quality gates.

**Key Achievements**:
- ✅ **Performance Targets Met**: ≥100K events/sec ingest, ≤5s history reconstruction, <10ms validation, <8GB memory
- ✅ **Quality Targets Achieved**: ≥99% CI success, 100% golden dataset match, >95% test coverage
- ✅ **Enterprise Features Delivered**: Automated quality gates, production monitoring, snapshot strategy

### **Implementation Summary**

**Performance Framework** (`tests/performance/test_event_schema_performance.py`):
- **Bulk Event Ingest Testing**: DuckDB vectorized operations validation for ≥100K events/sec
- **History Reconstruction**: ≤5s validation for 5-year participant history reconstruction
- **Schema Validation Performance**: <10ms per event validation with Pydantic v2
- **Memory Efficiency Testing**: <8GB memory usage validation for 100K employee simulation

**Validation Framework** (`tests/validation/test_golden_dataset_validation.py`):
- **Golden Dataset Validation**: 100% accuracy requirement against benchmark calculations
- **JSON Schema Validation**: ≥99% success rate for all 11 payload types
- **Edge Case Coverage**: >95% coverage with comprehensive boundary condition testing
- **Integration Workflow Testing**: End-to-end validation of all event combinations

**Snapshot Strategy** (`dbt/models/marts/fct_participant_balance_snapshots.sql`):
- **Weekly Balance Snapshots**: Pre-computed Friday snapshots for <100ms query performance
- **Event Reconstruction**: Complete balance calculation from event history with audit trail
- **dbt Contract Compliance**: Enforced contracts with complete column definitions
- **Performance Optimization**: Optimized for dashboard queries and compliance reporting

**CI/CD Integration** (`.github/workflows/performance-validation.yml`):
- **Automated Schema Validation**: JSON schema validation in GitHub Actions pipeline
- **Performance Regression Detection**: Automated performance benchmark testing
- **Quality Gate System**: 75% success rate requirement with detailed reporting
- **Artifact Collection**: Comprehensive test results and performance metrics retention

**Comprehensive Test Coverage** (`tests/unit/test_comprehensive_payload_coverage.py`):
- **All 11 Payload Types**: Complete coverage of workforce, DC plan, and administration events
- **Factory Method Validation**: Type-safe event creation with error handling testing
- **Discriminated Union Testing**: Proper routing through SimulationEvent union
- **Serialization Testing**: High-precision decimal and data integrity validation

**Performance Monitoring** (`scripts/performance_monitoring.py`):
- **Automated Metrics Collection**: Event creation, validation, and memory usage monitoring
- **Regression Detection**: Statistical analysis with baseline comparison and alerting
- **Historical Tracking**: SQLite database for metrics storage and trend analysis
- **Baseline Management**: Configurable performance baselines with threshold monitoring

### **Epic E021-A Completion Status**

✅ **S072-01**: Core Event Model - Foundation with Pydantic v2 discriminated unions
✅ **S072-02**: Workforce Events - Basic workforce event types (hire/promotion/termination/merit)
✅ **S072-03**: Core DC Plan Events - Essential DC plan events (eligibility/enrollment/contribution/vesting)
✅ **S072-04**: Plan Administration Events - Administrative events (forfeiture/HCE/compliance)
✅ **S072-06**: Performance & Validation Framework - Enterprise-grade testing and monitoring

**Result**: Complete DC plan event schema foundation ready for production deployment with comprehensive performance guarantees and automated quality assurance.

EOF < /dev/null
