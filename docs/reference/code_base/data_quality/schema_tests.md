# Schema Tests - Data Validation & Quality Assurance

## Purpose

The schema test files (`dbt/models/intermediate/schema.yml` and `dbt/models/marts/schema.yml`) define comprehensive data quality tests for all dbt models, ensuring data integrity, business rule compliance, and analytical accuracy throughout the Fidelity PlanAlign Engine simulation pipeline.

## Architecture

The testing framework implements a multi-layered validation approach:
- **Column-level Tests**: Individual field validation (not_null, unique, accepted_values)
- **Table-level Tests**: Cross-column and business rule validation
- **Custom Tests**: Domain-specific validation logic
- **Range Tests**: Numerical bounds and realistic value checking

## Key Test Categories

### 1. Data Integrity Tests

**Primary Key Validation**:
```yaml
- name: int_hiring_events
  description: "Generated hiring events for workforce growth"
  tests:
    - dbt_utils.unique_combination_of_columns:
        combination_of_columns:
          - employee_id
          - simulation_year
  columns:
    - name: employee_id
      description: "Unique identifier for hired employee"
      tests:
        - not_null
        - unique
```

**Referential Integrity**:
```yaml
- name: fct_workforce_snapshot
  description: "Annual workforce state after all events applied"
  columns:
    - name: employee_id
      tests:
        - not_null
        - relationships:
            to: ref('stg_census_data')
            field: employee_id
    - name: level_id
      tests:
        - accepted_values:
            values: [1, 2, 3, 4, 5]
```

### 2. Business Rule Validation

**Workforce Composition Rules**:
```yaml
- name: int_promotion_events
  tests:
    - dbt_utils.expression_is_true:
        expression: "from_level < to_level"
        config:
          severity: error
    - dbt_utils.expression_is_true:
        expression: "to_level <= 5"  # Max organizational level
```

**Financial Constraints**:
```yaml
- name: int_merit_events
  columns:
    - name: merit_increase
      tests:
        - dbt_utils.accepted_range:
            min_value: 0
            max_value: 50000  # Maximum reasonable merit increase
    - name: new_salary
      tests:
        - dbt_utils.accepted_range:
            min_value: 30000   # Minimum organizational salary
            max_value: 500000  # Maximum executive salary
```

### 3. Simulation Logic Validation

**Event Generation Validation**:
```yaml
- name: int_termination_events
  description: "Employee termination events with business rules"
  tests:
    # Validate termination rates are within expected bounds
    - dbt_utils.accepted_range:
        column_name: "COUNT(*)"
        min_value: "{{ (var('baseline_workforce_count') * var('min_termination_rate')) | int }}"
        max_value: "{{ (var('baseline_workforce_count') * var('max_termination_rate')) | int }}"
        group_by_columns:
          - simulation_year
```

**Growth Rate Validation**:
```yaml
- name: fct_workforce_snapshot
  tests:
    # Custom test to validate growth rates
    - assert_growth_rate_within_tolerance:
        target_growth_rate: "{{ var('target_growth_rate') }}"
        tolerance: "{{ var('growth_rate_tolerance', 0.005) }}"
```

### 4. Data Quality Checks

**Completeness Validation**:
```yaml
- name: fct_yearly_events
  columns:
    - name: employee_id
      tests:
        - not_null
    - name: event_type
      tests:
        - not_null
        - accepted_values:
            values: ['hire', 'promotion', 'termination', 'merit_raise']
    - name: simulation_year
      tests:
        - not_null
        - dbt_utils.accepted_range:
            min_value: 2020
            max_value: 2040
```

**Distribution Validation**:
```yaml
- name: mart_workforce_summary
  tests:
    # Validate reasonable workforce distribution
    - dbt_utils.accepted_range:
        column_name: turnover_rate_percent
        min_value: 5.0   # Minimum 5% turnover
        max_value: 30.0  # Maximum 30% turnover
    - dbt_utils.accepted_range:
        column_name: growth_rate_percent
        min_value: -10.0  # Allow up to 10% shrinkage
        max_value: 20.0   # Allow up to 20% growth
```

## Custom Test Macros

### Growth Rate Validation Test
```sql
-- macros/test_assert_growth_rate_within_tolerance.sql
{% macro test_assert_growth_rate_within_tolerance(model, target_growth_rate, tolerance=0.005) %}
  WITH growth_validation AS (
    SELECT
      simulation_year,
      active_headcount,
      LAG(active_headcount) OVER (ORDER BY simulation_year) AS prev_headcount,
      {{ target_growth_rate }} AS target_rate,
      {{ tolerance }} AS tolerance_threshold
    FROM {{ model }}
  ),

  growth_rates AS (
    SELECT
      simulation_year,
      CASE
        WHEN prev_headcount IS NOT NULL
        THEN (active_headcount - prev_headcount) * 1.0 / prev_headcount
        ELSE 0
      END AS actual_growth_rate,
      target_rate,
      tolerance_threshold
    FROM growth_validation
    WHERE prev_headcount IS NOT NULL
  )

  SELECT *
  FROM growth_rates
  WHERE ABS(actual_growth_rate - target_rate) > tolerance_threshold
{% endmacro %}
```

### Event Volume Validation Test
```sql
-- macros/test_validate_event_volumes.sql
{% macro test_validate_event_volumes(model, event_type, min_count, max_count) %}
  WITH event_counts AS (
    SELECT
      simulation_year,
      COUNT(*) as event_count
    FROM {{ model }}
    WHERE event_type = '{{ event_type }}'
    GROUP BY simulation_year
  )

  SELECT *
  FROM event_counts
  WHERE event_count < {{ min_count }} OR event_count > {{ max_count }}
{% endmacro %}
```

## Test Execution & Monitoring

### Running Tests
```bash
# Run all tests
dbt test

# Run tests for specific model
dbt test --select int_hiring_events

# Run only data quality tests
dbt test --select tag:data_quality

# Run with specific severity
dbt test --fail-fast
```

### Test Configuration
```yaml
# dbt_project.yml test configuration
tests:
  planalign_engine:
    +store_failures: true
    +severity: error
    data_quality:
      +severity: warn
    business_rules:
      +severity: error
```

## Common Test Patterns

### 1. Workforce Consistency Tests
```yaml
tests:
  - name: workforce_balance_check
    description: "Ensure workforce changes match event volumes"
    sql: |
      WITH workforce_changes AS (
        SELECT
          w.simulation_year,
          w.active_headcount - LAG(w.active_headcount) OVER (ORDER BY w.simulation_year) AS net_change,
          e.total_hires - e.total_terminations AS expected_change
        FROM {{ ref('fct_workforce_snapshot') }} w
        JOIN {{ ref('mart_workforce_summary') }} e ON w.simulation_year = e.simulation_year
      )
      SELECT * FROM workforce_changes
      WHERE ABS(net_change - expected_change) > 5  -- Allow small rounding differences
```

### 2. Financial Validation Tests
```yaml
tests:
  - name: compensation_budget_check
    description: "Validate total compensation changes within budget"
    sql: |
      SELECT simulation_year, total_compensation_investment
      FROM {{ ref('mart_workforce_summary') }}
      WHERE total_compensation_investment > {{ var('annual_compensation_budget') }}
```

### 3. Event Sequencing Tests
```yaml
tests:
  - name: event_sequence_validation
    description: "Ensure proper event ordering within years"
    sql: |
      SELECT employee_id, simulation_year, event_sequence
      FROM {{ ref('fct_yearly_events') }}
      WHERE event_sequence != ROW_NUMBER() OVER (
        PARTITION BY employee_id, simulation_year
        ORDER BY event_date,
        CASE event_type
          WHEN 'termination' THEN 1
          WHEN 'hire' THEN 2
          WHEN 'promotion' THEN 3
          WHEN 'merit_raise' THEN 4
        END
      )
```

## Test Results & Monitoring

### Test Result Storage
- Failed tests stored in dedicated tables for analysis
- Test execution logs captured for performance monitoring
- Historical test results tracked for trend analysis

### Alert Configuration
```yaml
# Example alert configuration
alerts:
  test_failures:
    enabled: true
    severity: error
    channels: ['slack', 'email']
  data_quality_warnings:
    enabled: true
    severity: warn
    channels: ['slack']
```

## Dependencies

### Required Packages
- `dbt-utils` - Advanced testing utilities
- `dbt-expectations` - Great expectations style tests
- Custom test macros for domain-specific validation

### Configuration Dependencies
- Simulation configuration variables
- Business rule parameters
- Data quality thresholds

## Related Files

### Test Definitions
- `dbt/models/intermediate/schema.yml` - Intermediate model tests
- `dbt/models/marts/schema.yml` - Final output tests
- `dbt/macros/test_*.sql` - Custom test macros

### Monitoring Components
- `dbt/models/monitoring/mon_data_quality.sql` - Quality monitoring
- `scripts/validation_checks.py` - Additional validation utilities

## Implementation Notes

### Best Practices
1. **Test Early and Often**: Run tests during development
2. **Meaningful Test Names**: Clear descriptions of what's being tested
3. **Appropriate Severity**: Error for business-critical, warn for quality
4. **Performance Consideration**: Balance thoroughness with execution time

### Common Issues
- **Test Performance**: Large datasets can slow test execution
- **False Positives**: Overly strict tests may flag valid edge cases
- **Test Maintenance**: Keep tests updated with business rule changes

### Testing Strategy
- Unit tests for individual model logic
- Integration tests for cross-model dependencies
- Regression tests for critical business scenarios
- Performance tests for large data volumes
