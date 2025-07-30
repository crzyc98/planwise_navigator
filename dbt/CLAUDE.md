# dbt Project - Claude Development Guide

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
├── snapshots/                 # Slowly changing dimensions (SCD)
└── simulation.duckdb          # DuckDB database file
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
  enable_incremental: true
  max_workers: 4
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
```

## Performance Optimization

### Incremental Models
```sql
-- For large fact tables
{{ config(materialized='incremental', unique_key='event_id') }}

{% if is_incremental() %}
  WHERE created_at >= (SELECT max(created_at) FROM {{ this }})
{% endif %}
```

### Partitioning Strategy
- **fct_yearly_events**: Partition by `simulation_year`
- **fct_workforce_snapshot**: Partition by `simulation_year`
- **SCD tables**: Partition by `dbt_valid_from`

### Query Optimization
- Use column-store optimized queries
- Minimize shuffling with proper JOIN order
- Leverage DuckDB's vectorized execution

## Integration Points

### Orchestrator MVP
```python
# Called from orchestrator_mvp/loaders/staging_loader.py
def run_dbt_model(model_name: str, vars: Dict[str, Any] = None):
    cmd = ["dbt", "run", "--select", model_name]
    if vars:
        for key, value in vars.items():
            cmd.extend(["--vars", f"{key}: {value}"])
    subprocess.run(cmd, cwd="dbt/")
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
# Run full simulation for single year
dbt run --vars "simulation_year: 2025"

# Multi-year via orchestrator_mvp
python orchestrator_mvp/run_mvp.py --multi-year
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

---

**Key Reminders**:
- Always run from `/dbt` directory for dbt commands
- Use variables for parameterization
- Test data quality assumptions
- Document complex business logic
- Optimize for DuckDB's columnar engine
