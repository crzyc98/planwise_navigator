# Workforce Needs Architecture

## Overview

The workforce needs architecture provides a centralized, single source of truth for all workforce planning calculations in the Fidelity PlanAlign Engine system. This eliminates redundancy and ensures consistency across all event generation models.

## Key Components

### 1. `int_workforce_needs` - Core Planning Model

This model centralizes all workforce planning calculations:

- **Current State Analysis**: Starting workforce counts and compensation
- **Growth Targets**: Calculation of required net growth based on configuration
- **Termination Forecasts**: Expected terminations for experienced employees
- **Hiring Requirements**: Total hires needed accounting for new hire attrition
- **Financial Impact**: Compensation costs for all workforce changes
- **Balance Validation**: Ensures calculations result in target growth

#### Key Calculations

```sql
-- Core hiring formula accounting for new hire attrition
total_hires_needed = (target_net_growth + experienced_terminations) / (1 - new_hire_termination_rate)

-- Balance validation
calculated_net_change = total_hires_needed - experienced_terminations - new_hire_terminations
growth_variance = ABS(calculated_net_change - target_net_growth)
```

### 2. `int_workforce_needs_by_level` - Detailed Level Analysis

Provides granular visibility by job level:

- **Level-specific headcount planning**
- **Hiring distribution by level** (40% L1, 30% L2, 20% L3, 8% L4, 2% L5)
- **Compensation planning by level**
- **Additional costs**: Recruiting, training, severance
- **Budget impact analysis**

### 3. Event Model Integration

All event generation models now reference the centralized calculations:

#### `int_hiring_events.sql`
- References `total_hires_needed` from `int_workforce_needs`
- Uses `hires_needed` and `new_hire_avg_compensation` from `int_workforce_needs_by_level`
- Maintains audit trail with `workforce_needs_id` and `scenario_id`

#### `int_termination_events.sql`
- References `expected_experienced_terminations` from `int_workforce_needs`
- Uses hazard-based selection with gap-filling to meet exact targets
- Links back to workforce planning via `workforce_needs_id`

#### `int_new_hire_termination_events.sql`
- References `expected_new_hire_terminations` from `int_workforce_needs`
- Applies deterministic selection to achieve exact targets
- Maintains planning linkage through `workforce_needs_id`

## Performance Optimizations

### DuckDB-Specific Enhancements

1. **Columnar Storage Optimization**
   - Indexes on commonly filtered columns: `simulation_year`, `scenario_id`, `level_id`
   - Efficient column ordering for vectorized operations

2. **Optimization Macros**
   ```sql
   {{ optimize_duckdb_workforce_query() }}  -- Enables profiling and parallel processing
   {{ create_workforce_indexes('table_name') }}  -- Creates performance indexes
   {{ vectorized_workforce_aggregation(query, columns) }}  -- Optimized aggregations
   ```

3. **Scalability Features**
   - Handles 100K+ employee datasets efficiently
   - Supports multi-year simulations
   - Enables scenario comparison analysis

## Data Quality Framework

### Built-in Validations

1. **Balance Status Check**
   - `BALANCED`: Growth variance ≤ 1 employee
   - `MINOR_VARIANCE`: Growth variance ≤ 3 employees
   - `SIGNIFICANT_VARIANCE`: Growth variance > 3 employees

2. **Comprehensive Testing**
   - Unique constraint on `workforce_needs_id`
   - Combination uniqueness on `simulation_year` + `scenario_id`
   - Range validations on all numeric fields
   - Referential integrity checks

## Benefits of Centralized Architecture

1. **Single Source of Truth**
   - All models use consistent calculations
   - Eliminates discrepancies between models
   - Simplifies debugging and validation

2. **Transparency**
   - Complete visibility into workforce planning logic
   - Clear audit trail with UUID tracking
   - Scenario comparison capabilities

3. **Maintainability**
   - Changes to planning logic in one place
   - Reduced code duplication
   - Easier testing and validation

4. **Performance**
   - Calculations performed once and reused
   - Optimized for DuckDB's columnar engine
   - Efficient memory usage

## Usage Examples

### Basic Workforce Planning Query
```sql
SELECT
    simulation_year,
    starting_workforce_count,
    total_hires_needed,
    expected_experienced_terminations,
    expected_new_hire_terminations,
    calculated_net_change,
    balance_status
FROM {{ ref('int_workforce_needs') }}
WHERE scenario_id = 'default'
ORDER BY simulation_year;
```

### Level-Specific Analysis
```sql
SELECT
    level_id,
    current_headcount,
    hires_needed,
    expected_terminations,
    net_headcount_change,
    total_budget_impact
FROM {{ ref('int_workforce_needs_by_level') }}
WHERE simulation_year = 2025
ORDER BY level_id;
```

### Scenario Comparison
```sql
WITH scenario_metrics AS (
    SELECT
        scenario_id,
        simulation_year,
        total_hires_needed,
        total_expected_terminations,
        net_compensation_change_forecast
    FROM {{ ref('int_workforce_needs') }}
)
SELECT
    simulation_year,
    MAX(CASE WHEN scenario_id = 'baseline' THEN total_hires_needed END) AS baseline_hires,
    MAX(CASE WHEN scenario_id = 'optimistic' THEN total_hires_needed END) AS optimistic_hires,
    MAX(CASE WHEN scenario_id = 'pessimistic' THEN total_hires_needed END) AS pessimistic_hires
FROM scenario_metrics
GROUP BY simulation_year;
```

## Future Enhancements

1. **Department-Level Planning**: Add department dimension for more granular planning
2. **Skill-Based Forecasting**: Incorporate skill requirements into workforce needs
3. **Geographic Distribution**: Support multi-location workforce planning
4. **Advanced Analytics**: Machine learning-based demand forecasting

## Conclusion

The centralized workforce needs architecture provides a robust foundation for workforce simulation and planning, ensuring consistency, transparency, and performance across the entire system.
