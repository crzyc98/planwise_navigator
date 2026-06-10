# dbt Project – Claude Development Guide

A dbt project for workforce simulation and event sourcing with DuckDB as the analytical engine for Fidelity PlanAlign Engine.

## Overview

This dbt project implements a workforce simulation system with:

- **Event-sourced architecture** with immutable audit trails
- **Multi-year simulation** capability
- **Hazard-based modeling** for promotions, raises, and terminations
- **Parameter-driven configuration** via seeds and variables
- **Data quality monitoring** and validation

## Project Structure

```
dbt/
├── dbt_project.yml            # dbt configuration and variables
├── profiles.yml               # DuckDB connection settings
├── simulation.duckdb          # DuckDB database (standardized location)
├── models/
│   ├── staging/               # Raw data cleaning (stg_*)
│   ├── intermediate/          # Business logic (int_*)
│   ├── marts/                 # Final outputs (fct_*, dim_*)
│   ├── analysis/              # Ad-hoc analysis and debug models
│   └── monitoring/            # Data quality and performance monitoring
├── seeds/                     # Configuration data (CSV files)
├── macros/                    # Reusable SQL functions
└── snapshots/                 # Slowly changing dimensions (SCD)
```

## Naming Conventions

### Model Prefixes
- `stg_*` - **Staging**: Clean and standardize raw data
- `int_*` - **Intermediate**: Business logic and calculations
- `fct_*` - **Facts**: Event tables and metrics
- `dim_*` - **Dimensions**: Reference and lookup tables
- `dq_*` / `data_quality_*` - **Data Quality**: Validation and monitoring
- `mon_*` - **Monitoring**: Performance and operational metrics
- `debug_*` - **Debug**: Development-only models gated by `enable_debug_models`

### Examples
- `stg_census_data.sql` - Clean raw employee census
- `int_baseline_workforce.sql` - Prepare workforce for simulation
- `fct_yearly_events.sql` - Immutable event stream
- `dim_hazard_table.sql` - Risk probability lookup

## Core Architecture Patterns

### 1. Event Sourcing
All workforce changes are captured as immutable events in `fct_yearly_events`, which unions the per-type `int_*_events` models. Events carry audit fields (`parameter_scenario_id`, `parameter_source`, `created_at`, `event_sequence`).

### 2. Hazard-Based Modeling
Risk probabilities drive stochastic events:

```sql
-- int_hazard_promotion.sql (pattern)
SELECT
    employee_id,
    base_rate * age_multiplier * tenure_multiplier * level_dampener AS promotion_rate,
    random_value,
    random_value < promotion_rate AS is_promoted
FROM workforce_with_multipliers
```

### 3. Parameter-Driven Configuration
Analysts control simulation via seed files:

```sql
{{ resolve_parameter('merit_base', var('simulation_year'), var('scenario_id')) }}

-- Uses comp_levers.csv seed:
-- scenario_id, fiscal_year, event_type, parameter_name, parameter_value
-- default, 2025, RAISE, merit_base, 0.035
```

### 4. Multi-Year State Management

Year N reads Year N-1 state plus Year N events. Two mechanisms:

- **Temporal accumulators** (`int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`, `int_deferral_escalation_state_accumulator`): incremental models that read their own prior-year rows via `{{ this }}` — **never `--full-refresh` these mid-simulation or prior-year state is destroyed**.
- **Prior-year snapshot reads** (e.g., `int_active_employees_prev_year_snapshot`): read `fct_workforce_snapshot` at `simulation_year - 1`.

**Layering rule and its one sanctioned exception:** `int_*` models must not read from `fct_*` tables, **except `fct_yearly_events`**. The orchestrator builds `fct_yearly_events` at the start of STATE_ACCUMULATION, and 20+ downstream `int_*` state models legitimately `ref()` it within the same year. Reading any other `fct_*` table from an `int_*` model (other than prior-year `fct_workforce_snapshot` reads) is a circular-dependency bug.

## Key Models by Layer

### Staging Layer (stg_*)
- `stg_census_data.sql` - Employee master data with validation
- `stg_config_*.sql` - Configuration tables from seeds (job levels, age/tenure bands)

### Intermediate Layer (int_*)
- `int_baseline_workforce.sql` - Starting workforce state
- `int_employee_compensation_by_year.sql` - Year-aware compensation
- `int_hazard_*.sql` - Risk probability calculations
- `int_*_events.sql` - Event generation by type
- `int_*_state_accumulator.sql` - Cross-year temporal state

### Marts Layer (fct_*, dim_*)
- `fct_yearly_events.sql` - **Core event stream** (immutable)
- `fct_workforce_snapshot.sql` - **Point-in-time workforce state**
- `fct_employer_match_events.sql` - Employer match events
- `dim_hazard_table.sql` - Risk multiplier lookup

## Critical Macros

- `resolve_parameter.sql` — parameter resolution with fallback hierarchy (scenario-specific → default scenario → hard-coded)
- `get_salary_as_of_date.sql` — time-aware salary calculation across raise/promotion events
- `assign_age_band` / `assign_tenure_band` — centralized band assignment from `config_age_bands.csv` / `config_tenure_bands.csv` ([min, max) convention)
- `optimize_duckdb_scd.sql` — SCD performance optimization

## Orchestrator Workflow Stages

The PipelineOrchestrator executes models per year in this sequence (see `planalign_orchestrator/pipeline/workflow.py` for the authoritative list):

1. **INITIALIZATION**: `staging.*` (Year 1 only)
2. **FOUNDATION**: `int_baseline_workforce`, `int_employee_compensation_by_year`, workforce needs
3. **EVENT_GENERATION**: termination → hiring → new-hire termination → promotion → merit → eligibility → enrollment → deferral events
4. **STATE_ACCUMULATION**: `fct_yearly_events` → state accumulators → contributions/match → `fct_workforce_snapshot` (batched dbt invocations; ordering comes from the dbt DAG)
5. **VALIDATION**: `dq_employee_contributions_validation`
6. **REPORTING**: Audit reports

`int_workforce_snapshot_optimized` and `int_deferral_rate_escalation_events` always run with `--full-refresh`; the orchestrator isolates them so the flag never touches the temporal accumulators.

## Performance Guidance

### Threading

**Default and recommended: `--threads 1`.** Multi-threaded dbt execution was benchmarked (E067/E068C) and reverted — it added overhead for this workload because most invocations select few models and DuckDB already parallelizes individual queries across all CPU cores regardless of dbt's thread count. Threading config lives in `config/simulation_config.yaml` under `optimization.e068c_threading.dbt_threads`.

```bash
cd dbt
dbt build --threads 1 --fail-fast
```

### What actually matters for speed
- **Subprocess count, not threads**: each `dbt run` invocation pays Python startup + project parse (~4-5s even on fast hardware). Batch model selections; don't loop one `dbt run` per model.
- **Partial parsing**: keep `target/partial_parse.msgpack` — never delete `dbt/target/` between runs.
- **Year filtering**: filter every heavy model by `{{ var('simulation_year') }}` to avoid full scans.
- **Memory**: `memory_limit` is set to 4GB in `profiles.yml` (laptop-conservative); raise it on machines with more RAM.

### Incremental Models (DuckDB)
```sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id','plan_design_id','employee_id','simulation_year']
) }}

SELECT ...
FROM {{ ref('upstream_model') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

### Query Optimization
- Avoid `SELECT *`; project only required columns.
- Join on `(scenario_id, plan_design_id, employee_id, simulation_year)` when relevant, with consistent types.
- Push filters early (especially year filters); DuckDB's vectorized engine rewards this.
- Don't use adapter-unsupported configs (`partition_by`, physical indexes) — DuckDB/dbt-duckdb ignores or rejects them.

### Debug Models (fast development)
```bash
# Run a debug model against a small employee subset
dbt run --select debug_hire_events --threads 1 \
  --vars '{"enable_debug_models": true, "dev_employee_limit": 100}'
```
Gated by `enable_debug_models` (default `false` in `dbt_project.yml`).

## Variable Configuration

Set in `dbt_project.yml` (overridable via `--vars`):

```yaml
vars:
  simulation_year: 2025
  scenario_id: "default"
  target_growth_rate: 0.03
  random_seed: 42
  enable_debug_models: false
  dev_employee_limit: null
```

## Seeds Configuration

### Parameter Management (`comp_levers.csv`)
```csv
scenario_id,fiscal_year,event_type,parameter_name,job_level,parameter_value
default,2025,RAISE,merit_base,1,0.030
default,2025,RAISE,merit_base,2,0.035
default,2025,RAISE,cola_rate,,0.025
```

### Hazard & Band Configuration
- `config_promotion_hazard_*.csv` - Promotion probability factors
- `config_termination_hazard_*.csv` - Turnover risk factors
- `config_job_levels.csv` - Compensation bands by level
- `config_age_bands.csv` / `config_tenure_bands.csv` - Band boundaries (rebuild with `dbt seed --threads 1` after edits)

## Data Quality Framework

- `dq_*` models and `data_quality_*` analysis models for validation
- Schema tests in `schema.yml` files (uniqueness on event grain, not-null on keys, `dbt_utils.unique_combination_of_columns` on accumulator grain)
- Band validation tests: `test_age_band_no_gaps`, `test_age_band_no_overlaps`, and tenure equivalents

## Development Workflow

### Model Development
```bash
cd dbt   # always run dbt from this directory

dbt run --select stg_census_data --threads 1
dbt test --select stg_census_data --threads 1
dbt run --select +fct_workforce_snapshot --threads 1   # with upstream deps

# Full refresh — safe for non-accumulator models only
dbt run --full-refresh --select fct_yearly_events --threads 1
```

### Multi-Year Simulation
```bash
# Primary interface
planalign simulate 2025-2027

# Orchestrator CLI
python -m planalign_orchestrator run --years 2025 2026 2027 --verbose

# Programmatic
python -c "
from planalign_orchestrator import create_orchestrator
from planalign_orchestrator.config import load_simulation_config
config = load_simulation_config('config/simulation_config.yaml')
orchestrator = create_orchestrator(config)
summary = orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
"
```

### Database Interaction (Claude Capabilities)

Claude can directly query the simulation database at `dbt/simulation.duckdb`:

```bash
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
duckdb dbt/simulation.duckdb "SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2025 LIMIT 5"

# Event distribution check
duckdb dbt/simulation.duckdb "
SELECT simulation_year, event_type, COUNT(*) AS event_count
FROM fct_yearly_events
GROUP BY ALL ORDER BY 1, 2"
```

```python
# Python access — always via get_database_path()
from planalign_orchestrator.config import get_database_path
import duckdb
conn = duckdb.connect(str(get_database_path()), read_only=True)
print(conn.execute('SHOW TABLES').fetchall())
conn.close()
```

Note: DuckDB allows one writer at a time — close IDE/DBeaver connections before running simulations (`planalign health` detects locks).

### Documentation
```bash
dbt docs generate
dbt docs serve --port 8080
```

## Common Patterns

### Event Generation Pattern
```sql
SELECT
    employee_id,
    '{{ event_type }}' AS event_type,
    {{ var('simulation_year') }} AS simulation_year,
    event_date AS effective_date,
    event_sequence,
    current_timestamp AS created_at,
    '{{ var('scenario_id') }}' AS parameter_scenario_id
FROM event_calculation_cte
```

### Hazard Calculation Pattern
```sql
WITH hazard_calculation AS (
    SELECT
        employee_id,
        base_rate *
        {{ get_age_multiplier('age_band') }} *
        {{ get_tenure_multiplier('tenure_band') }} AS event_rate,
        {{ get_random_value('employee_id', var('simulation_year'), var('random_seed')) }} AS random_value
    FROM workforce
)
SELECT *, random_value < event_rate AS event_occurs
FROM hazard_calculation
```

## Best Practices

- **Single responsibility**: one clear purpose per model
- **Idempotent**: re-runs produce identical results (delete+insert keyed by year)
- **Deterministic**: same `random_seed` → same events
- **Tested and documented**: schema tests + `description` fields for all models
- **Explicit null handling** in all calculations

## Troubleshooting

1. **Memory errors**: lower selection scope or check `memory_limit` in `profiles.yml`
2. **Database locks**: close other DuckDB connections (`planalign health` detects them)
3. **Duplicate/missing enrollment state**: rebuild via the accumulator pattern, never by full-refreshing accumulators mid-simulation
4. **Variable errors**: ensure `simulation_year` / `scenario_id` are passed via `--vars`
5. **Debug logging**: `dbt --debug run --select problematic_model`

---

**Key Reminders**:
- Always run dbt commands from the `dbt/` directory
- Database file is `dbt/simulation.duckdb` (standardized location)
- Default to `--threads 1`; DuckDB parallelizes queries internally regardless
- Never `--full-refresh` the temporal state accumulators mid-simulation
- `int_*` models may read `fct_yearly_events` (sanctioned exception) but no other `fct_*` tables in the same year
- Use the PlanAlign Orchestrator (`planalign simulate`) for production multi-year runs
