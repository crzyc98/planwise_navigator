PlanWise Navigator – Claude Code-Generation Playbook

A concise, opinionated reference for generating maintainable, production-ready code.

⸻

1  Purpose

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for PlanWise Navigator, Fidelity’s on-premises workforce-simulation platform.
Follow it verbatim to guarantee:
	•	Architecture consistency (DuckDB + dbt + Dagster + Streamlit).
	•	Readable, test-covered code.
	•	Smooth deployment to the analytics server.

⸻

2  System Overview

Layer	Technology	Version	Responsibility
Storage	DuckDB	1.0.0	Column-store warehouse; in-process OLAP engine
Transformation	dbt	1.9.2	Declarative SQL models, tests, documentation
Orchestration	Dagster	1.10.20	Asset-based pipeline for simulation workflow
Dashboard	Streamlit	1.46	Interactive analytics and scenario comparison
Configuration	Pydantic + YAML	-	Type-safe config management with validation
Monitoring	Dagster Assets	-	Asset checks, sensors, and metadata for data quality

<details>
<summary>Unified Simulation Pipeline</summary>

```
graph TD
    config[config/simulation_config.yaml] --> dagster[Dagster Pipeline]
    census[census_raw] --> baseline[int_baseline_workforce]
    baseline --> snapshot[prepare_year_snapshot] 
    snapshot --> prev_year[int_previous_year_workforce]
    prev_year --> events[Event Models]
    events --> yearly_events[fct_yearly_events]
    yearly_events --> workforce[fct_workforce_snapshot]
    workforce --> state[simulation_year_state]
    state --> checks[Asset Checks]
    checks --> dashboard[Streamlit Dashboards]
```

</details>



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
	•	Dagster assets: snake_case, descriptive (simulation_year_state, dbt_simulation_assets).
	•	Dagster ops: action_entity_op (prepare_year_snapshot, run_simulation_year_op).
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

# Streamlit Dashboard
streamlit run streamlit_dashboard/main.py  # Launch interactive dashboard

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

10  Common Troubleshooting Patterns

# DuckDB Serialization Issues (CRITICAL)
- **Problem**: DuckDB objects cannot be serialized by Dagster
- **Solution**: Always convert to pandas DataFrames or Python dicts before returning from assets
- **Pattern**: Use `.df()` method on DuckDB query results
```python
@asset
def my_asset(context: AssetExecutionContext, duckdb_resource: DuckDBResource) -> pd.DataFrame:
    with duckdb_resource.get_connection() as conn:
        df = conn.execute("SELECT * FROM table").df()  # Convert immediately
        return df  # Return serializable DataFrame
```

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