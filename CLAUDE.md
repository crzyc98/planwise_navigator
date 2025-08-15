# PlanWise Navigator – Claude Code-Generation Playbook

A comprehensive, opinionated reference for generating enterprise-grade, production-ready code for workforce simulation and event sourcing.

-----

### **1. Purpose**

This playbook tells Claude exactly how to turn high-level feature requests into ready-to-ship artifacts for PlanWise Navigator, Fidelity's on-premises workforce-simulation platform. Follow it verbatim to guarantee:

  * Event-sourced architecture with immutable audit trails
  * Modular, maintainable components with single-responsibility design
  * Enterprise-grade transparency and reproducibility
  * Production-ready deployment to analytics servers

-----

### **2. System Overview**

| Layer | Technology | Version | Responsibility |
| :--- | :--- | :--- | :--- |
| **Storage** | DuckDB | 1.0.0 | Immutable event store; column-store OLAP engine |
| **Transformation** | dbt-core | 1.8.8 | Declarative SQL models, tests, documentation |
| **Adapter** | dbt-duckdb | 1.8.1 | Stable DuckDB integration |
| **Orchestration** | run_multi_year.py | Direct | Python script with dbt subprocess calls for multi-year simulation workflow |
| **Dashboard** | Streamlit | 1.39.0 | Interactive analytics and compensation tuning |
| **Configuration** | Pydantic | 2.7.4 | Type-safe config management with validation |
| **Parameters** | comp\_levers.csv | Dynamic | Analyst-adjustable compensation parameters |
| **Python** | CPython | 3.11.x | Long-term support version |
| **Context** | Context7 MCP | Latest | Extended context management and tool integration |

\<details\>
\<summary\>Multi-Year Simulation Pipeline\</summary\>

```mermaid
graph TD
    config[config/simulation_config.yaml] --> runner[run_multi_year.py]
    params[comp_levers.csv] --> parameters[int_effective_parameters]
    census[census_raw] --> baseline[int_baseline_workforce]
    baseline --> compensation[int_employee_compensation_by_year]
    compensation --> needs[int_workforce_needs]
    needs --> events[Event Models]
    events --> yearly_events[fct_yearly_events]
    yearly_events --> accumulators[State Accumulators (int_*)]
    accumulators --> workforce[fct_workforce_snapshot]
    workforce --> audit[Year Audit Results]
    audit --> tuning[Compensation Tuning UI]
    tuning --> params
```

\</details\>

-----

### **3. Event Sourcing Architecture**

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
  * **BENEFIT\_ENROLLMENT**: Plan participation changes.
  * **DC PLAN EVENTS** (S072-03): Eligibility, enrollment, contributions, vesting.
  * **PLAN ADMINISTRATION EVENTS** (S072-04): Forfeitures, HCE determination, compliance monitoring.

**Unified Event Model** (S072-01):

  * **SimulationEvent**: Core event model using Pydantic v2 with discriminated unions.
  * **Required Context**: `scenario_id`, `plan_design_id` for proper event isolation.
  * **EventFactory**: Type-safe event creation with comprehensive validation.
  * **Performance**: \<5ms validation, 1000 events/second creation rate.

**Modular Engines**:

  * **Compensation Engine**: COLA, merit, and promotion-based adjustments.
  * **Termination Engine**: Hazard-based turnover modeling.
  * **Hiring Engine**: Growth-driven recruitment with realistic sampling.
  * **Promotion Engine**: Band-aware advancement probabilities.
  * **Parameter Engine**: Analyst-driven compensation tuning via `comp_levers.csv`.
  * **DC Plan Engine**: Retirement plan contribution, vesting, and distribution modeling (S072-03).
  * **Plan Administration Engine**: Forfeiture processing, HCE determination, and IRS compliance monitoring (S072-04).

**Snapshot Reconstruction**: Any workforce state can be instantly reconstructed from the event log for historical analysis and scenario validation.

Guidance: Avoid circular dependencies. Intermediate (`int_*`) models must not read from marts (`fct_*`). Use temporal accumulators (e.g., enrollment/deferral state) to carry state across years using only `int_*` sources.

-----

### **4. Directory Layout**

```
planwise_navigator/
├─ run_multi_year.py                 # Main multi-year simulation orchestrator
├─ orchestrator_dbt/                 # Enhanced dbt orchestrator (production)
│  ├─ run_multi_year.py             # Production multi-year runner
│  ├─ core/                         # Core orchestration components
│  └─ simulation/                   # Simulation logic modules
├─ dbt/                              # dbt project
│  ├─ models/                        # SQL transformation models
│  │  ├─ staging/                    # Raw data cleaning (stg_*)
│  │  ├─ intermediate/               # Business logic (int_*)
│  │  │  ├─ events/                 # Event generation models
│  │  │  └─ int_enrollment_state_accumulator.sql # Temporal enrollment state
│  │  │  └─ int_deferral_rate_state_accumulator.sql # Temporal deferral rate state
│  │  └─ marts/                      # Final outputs (fct_*, dim_*)
│  ├─ seeds/                         # Configuration data (CSV)
│  └─ macros/                        # Reusable SQL functions
├─ streamlit_dashboard/              # Interactive dashboard
├─ config/                           # Configuration management
│  ├─ simulation_config.yaml        # Simulation parameters
│  ├─ schema.py                     # Legacy event schema (Pydantic v1)
│  └─ events.py                     # Unified event model (Pydantic v2)
├─ shared_utils.py                   # Shared utilities and mutex handling
├─ scripts/                          # Utility scripts
├─ tests/                            # Comprehensive testing
├─ data/                             # Raw input files (git-ignored)
└─ simulation.duckdb                 # DuckDB database file (git-ignored)
```

-----

### **5. Naming and Coding Standards**

#### **Naming Conventions**

  * **dbt models**: `tier_entity_purpose` (e.g., `fct_workforce_snapshot`, `int_termination_events`).
  * **Event tables**: `fct_yearly_events` (immutable), `fct_workforce_snapshot` (point-in-time).
  * **Modular operations**: `action_entity` (e.g., `clean_duckdb_data`, `run_year_simulation`).
  * **Python orchestration**: `snake_case`, descriptive (e.g., `run_year_simulation`, `audit_year_results`).
  * **Python**: PEP 8; mandatory type-hints; Pydantic models for config.
  * **Configuration**: `snake_case` in YAML, hierarchical structure.

#### **Coding Standards**

  * **SQL (dbt)**: Use 2-space indents, uppercase keywords, and one clause per line. Avoid `SELECT *`. Use `{{ ref() }}` and CTEs for readability.
  * **Python**: Keep functions under 40 lines. Raise explicit exceptions. Use Pydantic for data modeling.

Do/Don't (DuckDB/dbt):
- Do filter heavy models by `{{ var('simulation_year') }}` and join on `(scenario_id, plan_design_id, employee_id)` (and year when relevant).
- Do use incremental models with `incremental_strategy='delete+insert'` keyed by year for idempotent re-runs.
- Don't use adapter-unsupported configs like physical `partition_by`/indexes; rely on logical partitioning by year.

<!-- end list -->

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date

class EmployeeEvent(BaseModel):
    employee_id: str = Field(..., min_length=1)
    event_type: Literal["HIRE", "TERM", "PROMOTION", "RAISE"]
    effective_date: date
```

-----

### **6. Development Workflow and Testing**

#### **Generation Workflow**

Every feature request becomes a single Pull-Request following this checklist:

1.  **Clarify scope**: Echo back requirements; call out unknowns.
2.  **Plan**: Update `/docs/spec-${date}.md` with the solution outline.
3.  **Generate code**: Create/modify dbt models, Dagster assets, or Python helpers.
4.  **Write tests**: Use dbt `schema.yml` tests and Pytest for Python.
5.  **Self-review**: Run `./scripts/lint && ./scripts/test`. Fix any failures.
6.  **Document**: Add docstrings and dbt doc blocks.
7.  **Commit**: Use conventional commits (`feat:`, `fix:`, `refactor:`).
8.  **Open PR**: Attach the spec link, screenshots, and test output.

#### **Testing Strategy**

| Layer | Framework | Minimum Coverage |
| :--- | :--- | :--- |
| dbt | built-in tests + dbt-unit-testing | 90% of models |
| Python | Pytest + pytest-dots | 95% lines |
| Dashboards | Cypress end-to-end (critical paths) | smoke |

#### **Data-Quality Gates**

1.  **Row counts**: Raw vs. staged table counts must have a difference of `<= 0.5%`.
2.  **Uniqueness**: Primary key uniqueness tests on every model.
3.  **Distribution drift**: Maintain baseline distributions; Kolmogorov-Smirnov test p-value should be `>= 0.1`.

-----

### **7. Local Development Environment**

```bash
# Python Environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run Multi-Year Simulations
python run_multi_year.py                                # Simple multi-year runner (development)
python orchestrator_dbt/run_multi_year.py               # Enhanced multi-year runner (production)

# dbt Development
cd dbt
dbt build --threads 4 --fail-fast               # Build + test
dbt test --select tag:data_quality              # Run DQ-only tests
dbt docs generate                               # Generate docs

# Single Year Development (for testing specific models)
cd dbt
dbt build --select stg_census_data int_baseline_workforce --vars "simulation_year: 2025"
dbt build --select int_enrollment_events --vars "simulation_year: 2025"
dbt build --select fct_yearly_events fct_workforce_snapshot --vars "simulation_year: 2025"

# DuckDB Direct Access (Claude can execute these)
duckdb simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
duckdb simulation.duckdb "SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2025 LIMIT 10"
duckdb simulation.duckdb "SHOW TABLES"

# Python DuckDB Access (Claude can execute these)
python -c "
import duckdb
conn = duckdb.connect('simulation.duckdb')
result = conn.execute('SELECT COUNT(*) FROM fct_yearly_events').fetchall()
print(f'Total events: {result[0][0]}')
conn.close()
"

# Streamlit Dashboards
streamlit run streamlit_dashboard/main.py
# Or use Make targets for convenience:
make run-dashboard                                       # Launch main dashboard (port 8501)
make run-compensation-tuning                             # Launch compensation tuning interface (port 8502)
make run-optimization-dashboard                          # Launch optimization dashboard (port 8503)

# Configuration Management
# Edit config/simulation_config.yaml for simulation parameters:
# - start_year, end_year (e.g., 2025-2029)
# - target_growth_rate
# - termination_rates
# - random_seed for reproducibility

# Development Pattern
# 1. Test single year: dbt run --select model_name --vars "simulation_year: 2025"
# 2. Test multi-year: python run_multi_year.py
# 3. Validate results: check audit output and database contents
# 4. Deploy changes: commit and use orchestrator_dbt/run_multi_year.py

# Enrollment Architecture Validation
dbt run --select validate_enrollment_architecture --vars "simulation_year: 2025"
# Check for duplicate enrollments across years in fct_yearly_events
```

-----

### **7.1. Claude Database Interaction Capabilities**

Claude Code can directly interact with your DuckDB simulation database using multiple methods:

#### **Direct DuckDB CLI Access**
Claude can execute DuckDB commands via the Bash tool:
```bash
# Query simulation data
duckdb simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = 2025"

# Inspect table structure
duckdb simulation.duckdb "DESCRIBE fct_workforce_snapshot"

# Check database health
duckdb simulation.duckdb "SHOW TABLES"
```

#### **Python DuckDB Library Access**
Claude can run Python scripts that use the DuckDB library:
```python
# Data validation scripts
python -c "
import duckdb
conn = duckdb.connect('simulation.duckdb')
result = conn.execute('SELECT simulation_year, COUNT(*) FROM fct_yearly_events GROUP BY simulation_year').fetchall()
for year, count in result:
    print(f'Year {year}: {count} events')
conn.close()
"
```

#### **Data Quality Monitoring**
Claude can proactively monitor data quality:
```bash
# Check for data anomalies
duckdb simulation.duckdb "
SELECT
    simulation_year,
    COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as hires,
    COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations
FROM fct_yearly_events
GROUP BY simulation_year
ORDER BY simulation_year
"
```

#### **Integration with dbt Models**
Claude can verify dbt model outputs and troubleshoot issues:
```bash
# Validate model results after dbt run
duckdb simulation.duckdb "
SELECT
    COUNT(*) as total_employees,
    COUNT(CASE WHEN enrollment_date IS NOT NULL THEN 1 END) as enrolled_count
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
"
```

This enables Claude to:
- **Debug simulation issues** by querying raw data
- **Validate data transformations** after dbt runs
- **Monitor data quality** across simulation years
- **Investigate performance issues** with query analysis
- **Provide real-time insights** during development

-----

### **8. Deployment**

The CI pipeline (GitHub Actions) performs:

1.  Lint → Pytest → dbt build –fail-fast
2.  Multi-year simulation validation using orchestrator_dbt/run_multi_year.py
3.  Tag & release Docker image `ghcr.io/fidelity/planwise:${sha}`
4.  Ansible playbook updates the on-prem server (zero-downtime blue-green).

-----

### **9. Project Status & Changelog**

This section tracks the implementation of major epics and stories.

#### **Epic E021-A: DC Plan Event Schema Foundation**

  * **Status**: 🟡 Partially Complete (81% - 5 of 7 stories completed on 2025-07-11)
  * **Summary**: Establishing a comprehensive, enterprise-grade event schema for DC plan operations. Successfully delivered core event model, workforce integration, DC plan events, and performance framework. Outstanding work includes loan/investment events and ERISA compliance review.
  * **Completed Stories** (26 of 32 points):
      * **S072-01**: Core Event Model (Pydantic v2 discriminated unions) ✅
      * **S072-02**: Workforce Events (Hire, Promotion, Termination, Merit) ✅
      * **S072-03**: Core DC Plan Events (Eligibility, Enrollment, Contribution, Vesting) ✅
      * **S072-04**: Plan Administration Events (Forfeiture, HCE, Compliance) ✅
      * **S072-06**: Performance & Validation Framework ✅
  * **Outstanding Stories** (6 of 32 points):
      * **S072-05**: Loan & Investment Events (3 points) ❌
      * **S072-07**: ERISA Compliance Review & Documentation (3 points) ❌

#### **Story S072-04: Plan Administration Events**

  * **Status**: Completed (2025-07-11)
  * **Summary**: Implemented essential plan administration events for governance and compliance, including `ForfeiturePayload`, `HCEStatusPayload`, and `ComplianceEventPayload`. Integrated into the `SimulationEvent` discriminated union with a full suite of 24 unit tests.

#### **Epic E020: Polars Integration MVP**

  * **Status**: Completed (2025-07-10)
  * **Summary**: A proof-of-concept demonstrated that Polars offers a **2.1x speedup** for complex aggregation queries compared to pandas on the project's dataset. While pandas remains faster for simpler operations, Polars is recommended for future complex analytics, especially for multi-year simulations.
  * **Details**: Polars `1.31.0` was installed and tested, showing no conflicts with the existing environment.

#### **Epic E013-S013-01: dbt Command Utility Enhancement**

  * **Status**: Completed
  * **Summary**: Centralized all dbt command execution by creating a new `execute_dbt_command_streaming()` utility. This function provides streaming output for long-running dbt operations like `dbt build` and is now used across the orchestrator assets.

#### **Fix: dbt Contract Compliance**

  * **Status**: Resolved
  * **Summary**: Fixed a multi-year simulation failure caused by dbt contract errors. The `schema.yml` for `fct_yearly_events` and `fct_workforce_snapshot` was updated to include data type definitions for all columns and correct several data type mismatches.

#### **Epic E012: Compensation Tuning System**

  * **Status**: Mostly complete; auto-optimization features are planned.
  * **Summary**: Enables analysts to dynamically adjust compensation parameters via a Streamlit UI, which updates `comp_levers.csv` to influence simulation results without code changes.
  * **Completed Stories**:
      * **S043**: Parameter foundation (`comp_levers.csv`).
      * **S044**: Dynamic parameter integration into models.
      * **S046**: Streamlit analyst interface.
  * **Planned Stories**:
      * **S045**: Auto-optimization loops (goal-seeking).
      * **S047**: SciPy optimization engine integration.

#### **Epic E023: Enrollment Architecture Fix**

  * **Status**: ✅ Completed (2025-01-05)
  * **Summary**: Fixed critical enrollment architecture issues that caused 321 employees to have enrollment events but no enrollment dates in workforce snapshots. Implemented temporal state accumulator pattern to eliminate circular dependencies.
  * **Key Improvements**:
      * **Created** `int_enrollment_state_accumulator.sql` - temporal state tracking without circular dependencies
      * **Fixed** `int_enrollment_events.sql` - restored essential WHERE clauses to prevent duplicate enrollments
      * **Updated** `fct_workforce_snapshot.sql` - proper event-to-state flow for enrollment dates
      * **Removed** broken `int_historical_enrollment_tracker.sql` model
      * **Added** `validate_enrollment_architecture.sql` for ongoing data quality monitoring
  * **Results**: Zero employees with enrollment events missing enrollment dates, proper multi-year enrollment continuity

-----

### **10. Troubleshooting and Common Issues**

#### **CRITICAL: Database and Path Issues**

  * **Database Location**: The simulation database is `simulation.duckdb` in the project root.
  * **dbt Commands**: Always run `dbt` commands from the `/dbt` directory.
  * **Multi-year Orchestration**: Use `run_multi_year.py` from project root or `orchestrator_dbt/run_multi_year.py` for production.
  * **Correct Pattern for Database Access**:
    ```python
    def get_database_connection():
        db_path = Path("simulation.duckdb")
        return duckdb.connect(str(db_path))

    # Query pattern
    conn = get_database_connection()
    result = conn.execute("SELECT * FROM fct_yearly_events WHERE simulation_year = ?", [year]).fetchall()
    conn.close()
    ```

#### **Virtual Environment and Versioning**

  * **Problem**: `ModuleNotFoundError` when running Python or dbt commands.
  * **Cause**: Using system-installed packages instead of virtual environment packages.
  * **Solution**: Always activate the virtual environment (`source venv/bin/activate`) before running commands, or call the binary directly (`venv/bin/python`, `venv/bin/dbt`).
  * **Compatible Versions**: `dbt-core: 1.8.8`, `dbt-duckdb: 1.8.1`, `duckdb: 1.0.0`.

#### **Database Locks and State Management**

  * **Problem**: Simulations fail due to a `Conflicting lock is held` error.
  * **Cause**: An active database connection is held by an IDE (like VS Code or Windsurf).
  * **Solution**: Close all open database connections in other tools before running a simulation. The Streamlit UI has built-in error detection for this.
  * **Data Persistence**: To persist data across runs in a multi-year simulation, ensure the job is configured with `full_refresh: False`.

#### **Cumulative Growth Calculation**

  * **Problem**: Year-over-year growth appears flat.
  * **Cause**: Calculating growth from the baseline each year instead of cumulatively.
  * **Solution**: Sum all events from the beginning of the simulation up to the current year to get the correct state.
    ```sql
    -- CORRECT: Calculate cumulative metrics from all events
    SELECT
        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) as total_hires,
        SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) as total_terminations
    FROM fct_yearly_events
    WHERE simulation_year <= ?
    ```

#### **Enrollment Architecture and Temporal State**

  * **Problem**: Duplicate enrollment events across years or missing enrollment dates in workforce snapshots.
  * **Cause**: Circular dependencies in enrollment tracking or incorrect temporal state accumulation.
  * **Solution**: Use the `int_enrollment_state_accumulator` model which implements proper temporal state tracking:
    - Year N uses Year N-1 accumulator data + Year N events
    - No circular dependencies
    - Maintains enrollment state across simulation years
  * **Validation**: Run `dbt run --select validate_enrollment_architecture` to check for data integrity issues.

#### **Deferral Rate State Accumulator (E036)**

  * **Pattern**: Year N reads Year N-1 state + current-year enrollment/escalation (from `int_*`) to produce deferral rates without touching `fct_*`.
  * **Order**: Build accumulator before `int_employee_contributions`, then `fct_yearly_events`, then `fct_workforce_snapshot`.
  * **Incremental**: Filter by `{{ var('simulation_year') }}`; prefer `delete+insert` keyed by composite unique key including year.

-----

### **11. Further Reading**

  * `/docs/architecture.md` – Deep-dive diagrams
  * `/docs/events.md` – Workforce event taxonomy
  * `/docs/issues/enrollment-architecture-fix-plan.md` – Enrollment architecture fix documentation
  * [dbt Style Guide](https://docs.getdbt.com/docs/collaborate/style-guide)
  * [DuckDB Documentation](https://duckdb.org/docs/)
