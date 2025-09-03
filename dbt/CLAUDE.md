# dbt Project – Claude Development Guide

A dbt project for workforce simulation and event sourcing with DuckDB as the analytical engine for PlanWise Navigator.

## Overview

This dbt project implements a comprehensive workforce simulation system with:

- **Event-sourced architecture** with immutable audit trails
- **Multi-year simulation** capability (2025-2029)
- **Hazard-based modeling** for promotions, raises, and terminations
- **Parameter-driven configuration** via seeds and variables
- **Performance optimization** for 100K+ employee datasets
- **Data quality monitoring** and validation

## Project Structure

```
dbt/
├── dbt_project.yml            # dbt configuration and variables
├── profiles.yml               # DuckDB connection settings
├── models/                    # SQL transformation models
│   ├── staging/               # Raw data cleaning (stg_*)
│   ├── intermediate/          # Business logic (int_*)
│   ├── marts/                 # Final outputs (fct_*, dim_*)
│   ├── analysis/              # Ad-hoc analysis queries
│   └── monitoring/            # Data quality and performance monitoring
├── seeds/                     # Configuration data (CSV files)
├── macros/                    # Reusable SQL functions
└── snapshots/                 # Slowly changing dimensions (SCD)

Note: `simulation.duckdb` lives at the project root (e.g., `/planwise_navigator/simulation.duckdb`), not under `dbt/`.
```

## Naming Conventions

### Model Prefixes
- `stg_*` - **Staging**: Clean and standardize raw data
- `int_*` - **Intermediate**: Business logic and calculations
- `fct_*` - **Facts**: Event tables and metrics
- `dim_*` - **Dimensions**: Reference and lookup tables
- `dq_*` - **Data Quality**: Validation and monitoring
- `mon_*` - **Monitoring**: Performance and operational metrics

### Examples
- `stg_census_data.sql` - Clean raw employee census
- `int_baseline_workforce.sql` - Prepare workforce for simulation
- `fct_yearly_events.sql` - Immutable event stream
- `dim_hazard_table.sql` - Risk probability lookup

## Core Architecture Patterns

### 1. Event Sourcing
All workforce changes are captured as immutable events:

```sql
-- fct_yearly_events.sql
SELECT
    employee_id,
    event_type,           -- hire, termination, promotion, raise
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    event_sequence,       -- Processing order within year
    created_at,
    -- Audit fields
    parameter_scenario_id,
    parameter_source,
    data_quality_flag
FROM {{ ref('int_employee_event_stream') }}
```

### 2. Hazard-Based Modeling
Risk probabilities drive stochastic events:

```sql
-- int_hazard_promotion.sql
SELECT
    employee_id,
    base_rate * age_multiplier * tenure_multiplier * level_dampener as promotion_rate,
    random_value,
    CASE WHEN random_value < promotion_rate THEN true ELSE false END as is_promoted
FROM workforce_with_multipliers
```

### 3. Parameter-Driven Configuration
Analysts control simulation via seed files:

```sql
-- Resolve parameter macro
{{ resolve_parameter('merit_base', var('simulation_year'), var('scenario_id')) }}

-- Uses comp_levers.csv seed:
-- scenario_id, fiscal_year, event_type, parameter_name, parameter_value
-- default, 2025, RAISE, merit_base, 0.035
```

### 4. Multi-Year State Management
Workforce transitions between simulation years:

```sql
-- int_workforce_previous_year.sql
SELECT *
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }} - 1
  AND employment_status = 'active'
```

Guidance:
- Avoid circular dependencies: intermediate (`int_*`) models must not read from marts (`fct_*`).
- Use temporal accumulators (e.g., `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`) to carry state across years.

## Key Models by Layer

### Staging Layer (stg_*)
- `stg_census_data.sql` - Employee master data with validation
- `stg_comp_levers.csv` - Analyst-adjustable parameters
- `stg_config_*.sql` - Configuration tables from seeds

### Intermediate Layer (int_*)
- `int_baseline_workforce.sql` - Starting workforce state
- `int_effective_parameters.sql` - Parameter resolution with defaults
- `int_employee_compensation_by_year.sql` - Year-aware compensation
- `int_hazard_*.sql` - Risk probability calculations
- `int_*_events.sql` - Event generation by type

### Marts Layer (fct_*, dim_*)
- `fct_yearly_events.sql` - **Core event stream** (immutable)
- `fct_workforce_snapshot.sql` - **Point-in-time workforce state**
- `dim_hazard_table.sql` - Risk multiplier lookup
- `fct_compensation_growth.sql` - Compensation analytics

## Critical Macros

### Parameter Resolution
```sql
-- macros/resolve_parameter.sql
-- Resolves parameters with fallback hierarchy:
-- 1. Scenario-specific value
-- 2. Default scenario value
-- 3. Hard-coded fallback

{{ resolve_parameter('cola_rate', 2025, 'scenario_a') }}
-- Returns: 0.025 (from comp_levers.csv)
```

### Performance Optimization
```sql
-- macros/optimize_duckdb_scd.sql
-- SCD performance optimization for large datasets
-- Uses efficient MERGE operations
```

### Compensation Calculations
```sql
-- macros/get_salary_as_of_date.sql
-- Time-aware salary calculation considering all raise events
-- Handles promotion timing and merit raise sequencing
```

## Variable Configuration

Set in `dbt_project.yml`:

```yaml
vars:
  simulation_year: 2025
  scenario_id: "default"
  target_growth_rate: 0.03
  random_seed: 42

# Performance tuning
flags:
  # Configure threads via CLI or profiles; keep deterministic across runs
  # Example runtime flag: dbt build --threads 4
  send_anonymous_usage_stats: false
```

## Seeds Configuration

### Parameter Management (`comp_levers.csv`)
```csv
scenario_id,fiscal_year,event_type,parameter_name,job_level,parameter_value
default,2025,RAISE,merit_base,1,0.030
default,2025,RAISE,merit_base,2,0.035
default,2025,RAISE,cola_rate,,0.025
```

### Hazard Configuration
- `config_promotion_hazard_*.csv` - Promotion probability factors
- `config_termination_hazard_*.csv` - Turnover risk factors
- `config_job_levels.csv` - Compensation bands by level

## Data Quality Framework

### Validation Models
- `dq_employee_id_validation.sql` - Unique identifier checks
- `data_quality_summary.sql` - Comprehensive validation dashboard

### Built-in Tests
```yaml
# models/schema.yml
models:
  - name: fct_yearly_events
    tests:
      - unique:
          column_name: "concat(employee_id, event_type, simulation_year, effective_date)"
      - not_null:
          column_name: employee_id
  - name: int_deferral_rate_state_accumulator
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - scenario_id
            - plan_design_id
            - employee_id
            - simulation_year
            - as_of_month
      - not_null:
          column_name: current_deferral_rate
```

## Performance Optimization

### Multi-Threading Support (Epic E067) ✅

**🎉 Threading is now fully functional and working!**

For optimal performance with threading:

```bash
# Multi-threaded execution (recommended)
dbt build --threads 4  # Shows "Concurrency: 4 threads"
dbt run --threads 4 --select staging.*
dbt test --threads 4

# Expected performance improvement: 20-30% faster execution
# Example: fct_yearly_events + 13 tests completed in 0.69s with 4 threads
```

### Work Laptop Optimizations

Choose threading level based on your environment:

```bash
# High-performance systems (recommended)
dbt build --threads 4  # 20-30% performance improvement

# Work laptops with resource constraints
dbt run --threads 2 --select staging.* --fail-fast  # Balanced performance/stability

# Very constrained environments (fallback)
dbt run --threads 1 --select staging.* --fail-fast  # Single-threaded for maximum stability

# Memory-efficient model execution in dependency order
dbt run --threads 2 --select int_baseline_workforce
dbt run --threads 2 --select int_employee_compensation_by_year
dbt run --threads 2 --select int_workforce_needs+

# Incremental builds for large tables
dbt run --threads 4 --select fct_yearly_events --vars '{simulation_year: 2025}'

# Multi-threaded multi-year processing
for year in 2025 2026 2027; do
  echo "Processing year $year with threading"
  dbt run --threads 4 --select foundation --vars "{simulation_year: $year}"
  dbt run --threads 4 --select events --vars "{simulation_year: $year}"
  dbt run --threads 4 --select marts --vars "{simulation_year: $year}"
done
```

### Navigator Orchestrator Workflow Stages

The PipelineOrchestrator executes models in optimized sequence:

1. **INITIALIZATION**: `staging.*`, `int_baseline_workforce` (Year 1 only)
2. **FOUNDATION**: `int_employee_compensation_by_year`, `int_workforce_needs`, `int_workforce_needs_by_level`
3. **EVENT_GENERATION**: `int_termination_events`, `int_hiring_events`, `int_promotion_events`, `int_merit_events`, `int_enrollment_events`
4. **STATE_ACCUMULATION**: `fct_yearly_events`, `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator_v2`, `fct_workforce_snapshot`
5. **VALIDATION**: `dq_employee_contributions_validation`
6. **REPORTING**: Audit and performance reports

### Memory-Efficient Configuration

```yaml
# dbt_project.yml - Work laptop optimizations
flags:
  send_anonymous_usage_stats: false

vars:
  # Threading configuration (Epic E067)
  dbt_threads: 4  # Use 4 threads for optimal performance, reduce to 2 or 1 for constrained systems

  # Memory management
  max_batch_size: 1000  # Increased for multi-threaded performance
  enable_caching: true   # Can enable with sufficient memory

models:
  planwise_navigator:
    # Incremental models for large tables
    intermediate:
      events:
        +materialized: incremental
        +incremental_strategy: delete+insert
        +on_schema_change: sync_all_columns

    marts:
      +materialized: incremental
      +incremental_strategy: delete+insert
      +unique_key: ['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year']
```

### Incremental Models (DuckDB)
```sql
-- Scope by simulation_year and use delete+insert for idempotent re-runs
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['scenario_id','plan_design_id','employee_id','simulation_year']
) }}

SELECT ...
FROM {{ ref('upstream_model') }}
WHERE simulation_year = {{ var('simulation_year') }}
```

### Logical Partitioning
- Filter every heavy model by `{{ var('simulation_year') }}` to avoid full scans.
- Prefer `incremental_strategy='delete+insert'` keyed by year; DuckDB does not use table partitions/indexes.
- For large persistent tables, consider output ordering on `(scenario_id, plan_design_id, employee_id, simulation_year)` for scan locality.

### Query Optimization
- Avoid `SELECT *`; project only required columns.
- Keep JOIN keys minimal and typed consistently; join on `(scenario_id, plan_design_id, employee_id, simulation_year)` when relevant.
- Leverage DuckDB’s vectorized execution; push filters early (especially year filters).
- Avoid adapter-unsupported configs (e.g., `partition_by`, physical indexes).

### Contracts & Tags
- Enable contracts on critical models; enforce schemas for stability.
- Tag pipelines (e.g., `tags: ['deferral_pipeline']`) and use selectors for targeted builds.

## Integration Points

### Navigator Orchestrator Integration
```python
# Integration with navigator_orchestrator.pipeline.PipelineOrchestrator
from navigator_orchestrator import create_orchestrator
from navigator_orchestrator.config import load_simulation_config

# Load configuration and create orchestrator
config = load_simulation_config('config/simulation_config.yaml')
orchestrator = create_orchestrator(config)

# Execute multi-year simulation with staged workflow
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025, end_year=2027, fail_on_validation_error=False
)

# Individual model execution via DbtRunner
from navigator_orchestrator.dbt_runner import DbtRunner
dbt_runner = DbtRunner(project_dir="dbt", profiles_dir="dbt")
result = dbt_runner.execute_command(
    ["run", "--select", "int_baseline_workforce", "--threads", "1"],
    simulation_year=2025,
    stream_output=True
)
```

### Eligibility Engine Integration
For E022 Eligibility Engine, add:

```sql
-- models/intermediate/int_eligibility_determination.sql
{{ config(materialized='table') }}

WITH eligibility_checks AS (
    SELECT
        employee_id,
        current_age >= {{ var('minimum_age', 21) }} as is_age_eligible,
        current_tenure >= {{ var('minimum_service_months', 12) }} as is_service_eligible,
        annual_hours >= {{ var('minimum_hours_annual', 1000) }} as is_hours_eligible,
        lower(trim(employee_type)) NOT IN ('intern', 'contractor') as is_classification_eligible
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
)

SELECT
    *,
    (is_age_eligible AND is_service_eligible AND is_hours_eligible AND is_classification_eligible) as is_eligible
FROM eligibility_checks
```

## Development Workflow

### Model Development
```bash
# Develop single model
dbt run --select stg_census_data

# Test model
dbt test --select stg_census_data

# Build with dependencies
dbt run --select +fct_workforce_snapshot

# Full refresh
dbt run --full-refresh --select fct_yearly_events
```

### Multi-Year Simulation
```bash
# Run full simulation for single year (work laptop optimized)
dbt run --threads 1 --vars "simulation_year: 2025"

# Multi-year via Navigator Orchestrator (with threading!)
python -m navigator_orchestrator run --years 2025 2026 2027 --threads 4 --verbose

# Direct orchestrator execution
python -c "
from navigator_orchestrator import create_orchestrator
from navigator_orchestrator.config import load_simulation_config
config = load_simulation_config('config/simulation_config.yaml')
orchestrator = create_orchestrator(config)
summary = orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
print(f'Completed {len(summary.completed_years)} years')
"
```

### Database Interaction (Claude Capabilities)

Claude can directly interact with your DuckDB simulation database:

#### **Direct DuckDB Queries**
```bash
# Query simulation database (located at dbt/simulation.duckdb)
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
duckdb dbt/simulation.duckdb "SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2025 LIMIT 5"

# From dbt directory
cd dbt
duckdb simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events"
```

#### **Python Database Access**
```bash
# Python scripts for data validation using Navigator Orchestrator
python -c "
from navigator_orchestrator.config import get_database_path
import duckdb
conn = duckdb.connect(str(get_database_path()))
tables = conn.execute('SHOW TABLES').fetchall()
print('Available tables:', [t[0] for t in tables])
conn.close()
"

# Direct database access
python -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb')
tables = conn.execute('SHOW TABLES').fetchall()
print('Available tables:', [t[0] for t in tables])
conn.close()
"
```

#### **Model Validation Queries**
```bash
# Validate dbt model results
duckdb dbt/simulation.duckdb "
SELECT
    model_name,
    COUNT(*) as row_count
FROM (
    SELECT 'fct_yearly_events' as model_name FROM fct_yearly_events
    UNION ALL
    SELECT 'fct_workforce_snapshot' as model_name FROM fct_workforce_snapshot
)
GROUP BY model_name
"
```

### Documentation
```bash
# Generate docs
dbt docs generate

# Serve docs locally
dbt docs serve --port 8080
```

## Common Patterns

### Year-Aware Models
```sql
-- Template for multi-year models
{% set simulation_year = var('simulation_year') %}

SELECT *
FROM source_table
WHERE fiscal_year = {{ simulation_year }}
```

### Event Generation Pattern
```sql
-- Template for event models
SELECT
    employee_id,
    '{{ event_type }}' as event_type,
    {{ var('simulation_year') }} as simulation_year,
    event_date as effective_date,
    event_sequence,
    -- Standard audit fields
    current_timestamp as created_at,
    '{{ var('scenario_id') }}' as parameter_scenario_id
FROM event_calculation_cte
```

### Hazard Calculation Pattern
```sql
-- Template for risk-based events
WITH hazard_calculation AS (
    SELECT
        employee_id,
        base_rate *
        {{ get_age_multiplier('age_band') }} *
        {{ get_tenure_multiplier('tenure_band') }} as event_rate,
        {{ get_random_value('employee_id', var('simulation_year'), var('random_seed')) }} as random_value
    FROM workforce
)

SELECT *,
    CASE WHEN random_value < event_rate THEN true ELSE false END as event_occurs
FROM hazard_calculation
```

## Best Practices

### Model Design
- **Single responsibility**: Each model should have one clear purpose
- **Idempotent**: Models should produce same results on re-run
- **Testable**: Include data quality tests for all models
- **Documented**: Use `description` fields in schema.yml

### Performance
- **Incremental where appropriate**: Large fact tables should be incremental
- **Efficient JOINs**: JOIN on indexed columns when possible
- **Minimize data movement**: Filter early in CTEs
- **Use variables**: Parameterize for different scenarios

### Data Quality
- **Validate inputs**: Test source data assumptions
- **Monitor outputs**: Track row counts and key metrics
- **Handle nulls**: Explicit null handling in all calculations
- **Audit trail**: Track data lineage and transformations

## Troubleshooting

### Common Issues
1. **Memory errors**: Reduce batch size or use incremental models
2. **Performance**: Check query plans and optimize JOINs
3. **Data quality**: Add tests for edge cases and null handling
4. **Variable errors**: Ensure all required variables are set

### Debug Mode
```bash
# Enable debug logging
dbt --debug run --select problematic_model

# Profile query performance
dbt run --select model_name --profiles-dir profiles/
```

### Claude-Assisted Debugging

Claude can help debug dbt models by directly querying the database:

```bash
# Check model output after dbt run (using correct database path)
duckdb dbt/simulation.duckdb "SELECT COUNT(*), MIN(simulation_year), MAX(simulation_year) FROM fct_yearly_events"

# Investigate data quality issues
duckdb dbt/simulation.duckdb "
SELECT
    simulation_year,
    event_type,
    COUNT(*) as event_count
FROM fct_yearly_events
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type
"

# Check for missing data
duckdb dbt/simulation.duckdb "
SELECT
    COUNT(*) as total_employees,
    COUNT(enrollment_date) as employees_with_enrollment,
    COUNT(*) - COUNT(enrollment_date) as missing_enrollment_dates
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
"
```

Claude can also run Python scripts to perform advanced diagnostics:
```python
python -c "
import duckdb
import os
os.chdir('..')  # Navigate to project root
conn = duckdb.connect('simulation.duckdb')

# Check data consistency across tables
events_count = conn.execute('SELECT COUNT(DISTINCT employee_id) FROM fct_yearly_events WHERE simulation_year = 2025').fetchone()[0]
snapshot_count = conn.execute('SELECT COUNT(DISTINCT employee_id) FROM fct_workforce_snapshot WHERE simulation_year = 2025').fetchone()[0]

print(f'Unique employees in events: {events_count}')
print(f'Unique employees in snapshot: {snapshot_count}')
print(f'Difference: {abs(events_count - snapshot_count)}')

conn.close()
"
```

---

## Epic E067: Multi-Threading Success ✅

**Status**: 🟢 **Production Ready** (January 2025)

Epic E067 Multi-Threading Support has been successfully implemented and is fully operational:

### **✅ Delivered Capabilities:**
- **dbt Threading**: `--threads 4` support with 20-30% performance improvement
- **Model Parallelization**: Independent models execute concurrently
- **Resource Management**: Memory and CPU monitoring with adaptive scaling
- **Deterministic Execution**: Reproducible results across all thread configurations

### **🚀 Performance Results:**
- **Confirmed**: `Concurrency: 4 threads (target='dev')` in dbt output
- **Measured**: 0.69s execution time for complex model + 13 tests with 4 threads
- **Expected**: 20-30% improvement over single-threaded execution

### **📋 Usage:**
```bash
# Optimal threading for most systems
cd dbt && dbt build --threads 4

# Navigator Orchestrator with threading
python -m navigator_orchestrator run --years 2025-2026 --threads 4 --verbose
```

---

**Key Reminders**:
- Always run from `/dbt` directory for dbt commands
- Database file `simulation.duckdb` is in `/dbt` directory (standardized location)
- Use variables for parameterization
- Test data quality assumptions
- Document complex business logic
- Optimize for DuckDB's columnar engine
- Use Navigator Orchestrator for production multi-year simulations
- **NEW**: Use `--threads 4` for optimal performance (reduce to 2 or 1 for constrained systems)
- Enable checkpointing for long-running simulations
