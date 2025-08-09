# Story S036-06: Add Data Quality Validation

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 2
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Quality Assurance

## Story

**As a** platform engineer
**I want** to add comprehensive data quality validation for the deferral rate state accumulator
**So that** state consistency is maintained across years and data integrity issues are detected early

## Business Context

The new `int_deferral_rate_state_accumulator` model is critical for multi-year simulation execution. Data quality validation ensures that state accumulation works correctly across year boundaries, deferral rates are within valid ranges, and no duplicate or inconsistent states exist. This validation provides confidence in the Epic E036 solution and early detection of data issues.

## Acceptance Criteria

### Data Quality Validation Models
- [ ] **Create `dq_deferral_rate_state_validation.sql`** comprehensive validation model with year scoping
- [ ] **Create `dq_deferral_rate_state_validation_details.sql`** for actionable failure details
- [ ] **Add downstream `dq_employee_contributions_validation.sql`** for contribution integrity
- [ ] **Add model-level dbt tests** with composite key constraints and severity levels

### State Integrity Validation
- [ ] **Monthly grain enforcement** ensuring 12 rows per active employee per year
- [ ] **Cross-year carryforward validation** with proper scenario/plan scoping
- [ ] **Deterministic temporal checks** using simulation year boundaries not wall clock
- [ ] **Composite key referential integrity** with scenario_id and plan_design_id scoping
- [ ] **Year-aware plan bounds validation** with effective date filtering

### Orchestrator Integration & Performance
- [ ] **Tag-based validation execution** in orchestration workflow with fail-fast
- [ ] **Year-scoped validation** filtering by simulation_year variable for performance
- [ ] **Severity-based failure handling** with error vs. warn level responses
- [ ] **Monitoring views** under `dbt/models/monitoring/` with proper materialization
- [ ] **JSON reporting capability** for external alerting hooks

## Data Quality Validation Implementation

### Comprehensive Validation Model

```sql
-- dbt/models/data_quality/dq_deferral_rate_state_validation.sql
-- Comprehensive data quality validation for deferral rate state accumulator
-- SCOPED BY SIMULATION YEAR for performance and accuracy

{{ config(
    materialized='view',
    tags=['data_quality', 'deferral_rate', 'validation']
) }}

WITH
-- Base scoped data for current simulation year
scoped_accumulator AS (
  SELECT *
  FROM {{ ref('int_deferral_rate_state_accumulator') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Test 1: Composite Key Uniqueness (scoped to current year)
duplicate_states AS (
  SELECT
    scenario_id, plan_design_id, employee_id, simulation_year, as_of_month,
    COUNT(*) as duplicate_count
  FROM scoped_accumulator
  GROUP BY scenario_id, plan_design_id, employee_id, simulation_year, as_of_month
  HAVING COUNT(*) > 1
),

-- Test 2: Deferral Rate Range Validation (scoped to current year)
invalid_deferral_rates AS (
  SELECT
    scenario_id, plan_design_id, employee_id, current_deferral_rate, simulation_year,
    'invalid_range' as validation_error
  FROM scoped_accumulator
  WHERE current_deferral_rate < 0.0000
     OR current_deferral_rate > 1.0000
     OR current_deferral_rate IS NULL
),

-- Test 3: Referential Integrity with Baseline Workforce (composite key scoped)
missing_employee_references AS (
  SELECT
    acc.scenario_id, acc.plan_design_id, acc.employee_id, acc.simulation_year,
    'missing_baseline_reference' as validation_error
  FROM scoped_accumulator acc
  LEFT JOIN {{ ref('int_baseline_workforce') }} base
    ON acc.scenario_id = base.scenario_id
    AND acc.plan_design_id = base.plan_design_id
    AND acc.employee_id = base.employee_id
    AND acc.simulation_year = base.simulation_year
  WHERE base.employee_id IS NULL
    AND acc.is_active = TRUE
),

-- Test 4: Monthly Grain Validation - Should be exactly 12 rows per active employee
incorrect_monthly_grain AS (
  SELECT
    scenario_id, plan_design_id, employee_id, simulation_year,
    COUNT(*) as month_count,
    'incorrect_monthly_grain' as validation_error
  FROM scoped_accumulator
  WHERE is_active = TRUE
  GROUP BY scenario_id, plan_design_id, employee_id, simulation_year
  HAVING COUNT(*) != 12  -- Should have exactly 12 monthly rows
),

-- Test 4b: is_current flag validation - exactly one per employee/year
multiple_current_states AS (
  SELECT
    scenario_id, plan_design_id, employee_id, simulation_year,
    COUNT(*) as current_state_count
  FROM scoped_accumulator
  WHERE is_current = TRUE
  GROUP BY scenario_id, plan_design_id, employee_id, simulation_year
  HAVING COUNT(*) > 1
),

-- Test 5: Cross-Year Carryforward Validation (when no current year changes exist)
invalid_carryforward_transitions AS (
  SELECT
    curr.scenario_id, curr.plan_design_id, curr.employee_id,
    curr.simulation_year as current_year,
    curr.current_deferral_rate as current_rate,
    prev.current_deferral_rate as previous_rate,
    'invalid_carryforward_transition' as validation_error
  FROM scoped_accumulator curr
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} prev
    ON curr.scenario_id = prev.scenario_id
    AND curr.plan_design_id = prev.plan_design_id
    AND curr.employee_id = prev.employee_id
    AND curr.simulation_year = prev.simulation_year + 1
  WHERE curr.simulation_year > (
      SELECT MIN(simulation_year)
      FROM {{ ref('int_deferral_rate_state_accumulator') }}
      WHERE scenario_id = curr.scenario_id AND plan_design_id = curr.plan_design_id
    )  -- Not first year for this scenario/plan
    AND curr.is_current = TRUE
    AND prev.is_current = TRUE
    AND curr.source_type = 'carryforward'  -- Only validate carryforward transitions
    AND ABS(curr.current_deferral_rate - prev.current_deferral_rate) > 0.0001  -- Should match if carryforward
),

-- Test 6: Temporal Logic Validation (deterministic using simulation year boundaries)
invalid_temporal_logic AS (
  SELECT
    scenario_id, plan_design_id, employee_id, simulation_year, effective_date, as_of_month,
    'invalid_temporal_logic' as validation_error
  FROM scoped_accumulator
  WHERE DATE_TRUNC('month', effective_date) != as_of_month  -- Temporal grain mismatch
     OR effective_date > DATE('{{ var("simulation_year") }}-12-31')  -- Future effective dates beyond year
     OR effective_date < DATE('{{ var("simulation_year") }}-01-01')  -- Effective dates before year
     OR applied_at < effective_date                         -- Applied before effective
),

-- Test 7: Source Event Audit Trail Validation (with JSON array length checks)
invalid_audit_trail AS (
  SELECT
    scenario_id, plan_design_id, employee_id, simulation_year, source_type, source_event_ids,
    'invalid_audit_trail' as validation_error
  FROM scoped_accumulator
  WHERE -- Event-sourced states should have non-empty source events
        (source_type IN ('enrollment', 'escalation') AND
         (source_event_ids IS NULL OR json_array_length(source_event_ids) = 0))
     -- Baseline and carryforward can have empty source events
     OR (source_type IN ('baseline', 'carryforward') AND source_event_ids IS NOT NULL AND
         json_array_length(source_event_ids) > 0)
     OR (state_version < 1)
     OR (applied_at IS NULL)
),

-- Test 8: Plan Bounds Compliance (year-aware plan parameters)
plan_bounds_violations AS (
  SELECT
    acc.scenario_id, acc.plan_design_id, acc.employee_id, acc.simulation_year,
    acc.current_deferral_rate, pd.plan_min_deferral_rate, pd.plan_max_deferral_rate,
    'plan_bounds_violation' as validation_error
  FROM scoped_accumulator acc
  LEFT JOIN {{ ref('dim_plan_designs') }} pd
    ON acc.plan_design_id = pd.plan_design_id
    -- TODO: Add year-aware filtering if plan limits vary by year:
    -- AND pd.effective_date <= DATE('{{ var("simulation_year") }}-12-31')
    -- AND (pd.end_date IS NULL OR pd.end_date >= DATE('{{ var("simulation_year") }}-01-01'))
  WHERE acc.current_deferral_rate < COALESCE(pd.plan_min_deferral_rate, 0.0000)
     OR acc.current_deferral_rate > COALESCE(pd.plan_max_deferral_rate, 1.0000)
),

-- Test 9: Active Employee State Consistency (composite key join)
inactive_employee_states AS (
  SELECT
    acc.scenario_id, acc.plan_design_id, acc.employee_id, acc.simulation_year,
    'inactive_employee_with_active_state' as validation_error
  FROM scoped_accumulator acc
  JOIN {{ ref('int_baseline_workforce') }} base
    ON acc.scenario_id = base.scenario_id
    AND acc.plan_design_id = base.plan_design_id
    AND acc.employee_id = base.employee_id
    AND acc.simulation_year = base.simulation_year
  WHERE acc.is_active = TRUE
    AND base.employment_status = 'terminated'
),

-- Test 10: Baseline Seeding Validation (per scenario/plan first year)
baseline_seeding_issues AS (
  SELECT
    base.scenario_id, base.plan_design_id, base.employee_id,
    'missing_baseline_seed' as validation_error
  FROM {{ ref('int_baseline_workforce') }} base
  WHERE base.simulation_year = {{ var('simulation_year') }}
    AND base.employment_status = 'active'
    -- Check if this is the first year for this scenario/plan combination
    AND {{ var('simulation_year') }} = (
      SELECT MIN(b2.simulation_year)
      FROM {{ ref('int_baseline_workforce') }} b2
      WHERE b2.scenario_id = base.scenario_id
        AND b2.plan_design_id = base.plan_design_id
    )
    -- Missing from accumulator for this year
    AND NOT EXISTS (
      SELECT 1 FROM scoped_accumulator acc
      WHERE acc.scenario_id = base.scenario_id
        AND acc.plan_design_id = base.plan_design_id
        AND acc.employee_id = base.employee_id
        AND acc.source_type IN ('baseline', 'enrollment')
    )
),

-- Test 11: Completeness vs baseline workforce
completeness_violations AS (
  SELECT
    base.scenario_id, base.plan_design_id, base.employee_id,
    'missing_accumulator_state' as validation_error
  FROM {{ ref('int_baseline_workforce') }} base
  WHERE base.simulation_year = {{ var('simulation_year') }}
    AND base.employment_status = 'active'
    AND NOT EXISTS (
      SELECT 1 FROM scoped_accumulator acc
      WHERE acc.scenario_id = base.scenario_id
        AND acc.plan_design_id = base.plan_design_id
        AND acc.employee_id = base.employee_id
    )
)

-- Final validation summary (all counts should be 0 for passing data quality)
SELECT 'duplicate_states' as validation_test, COUNT(*) as failure_count, 'error' as severity FROM duplicate_states
UNION ALL
SELECT 'invalid_deferral_rates', COUNT(*), 'error' FROM invalid_deferral_rates
UNION ALL
SELECT 'missing_employee_references', COUNT(*), 'error' FROM missing_employee_references
UNION ALL
SELECT 'incorrect_monthly_grain', COUNT(*), 'error' FROM incorrect_monthly_grain
UNION ALL
SELECT 'multiple_current_states', COUNT(*), 'error' FROM multiple_current_states
UNION ALL
SELECT 'invalid_carryforward_transitions', COUNT(*), 'warn' FROM invalid_carryforward_transitions
UNION ALL
SELECT 'invalid_temporal_logic', COUNT(*), 'error' FROM invalid_temporal_logic
UNION ALL
SELECT 'invalid_audit_trail', COUNT(*), 'warn' FROM invalid_audit_trail
UNION ALL
SELECT 'plan_bounds_violations', COUNT(*), 'error' FROM plan_bounds_violations
UNION ALL
SELECT 'inactive_employee_states', COUNT(*), 'error' FROM inactive_employee_states
UNION ALL
SELECT 'baseline_seeding_issues', COUNT(*), 'error' FROM baseline_seeding_issues
UNION ALL
SELECT 'completeness_violations', COUNT(*), 'error' FROM completeness_violations
```

### Detailed Failures Model for Actionable Triage

```sql
-- dbt/models/data_quality/dq_deferral_rate_state_validation_details.sql
-- Detailed failure records for remediation and debugging

{{ config(
    materialized='ephemeral',  -- Don't persist, used for aggregation only
    tags=['data_quality', 'details']
) }}

-- All the same CTEs as above, but return detailed failure records
WITH
-- ... [Same CTEs as validation summary model] ...

-- Union all detailed failure records with consistent schema
SELECT scenario_id, plan_design_id, employee_id, simulation_year,
       'duplicate_states' as error_type, 'error' as severity,
       'Composite key violation - multiple states for same key' as error_description,
       duplicate_count as error_value
FROM duplicate_states

UNION ALL

SELECT scenario_id, plan_design_id, employee_id, simulation_year,
       'invalid_deferral_rates' as error_type, 'error' as severity,
       'Deferral rate outside valid range [0, 1]' as error_description,
       current_deferral_rate as error_value
FROM invalid_deferral_rates

UNION ALL

SELECT scenario_id, plan_design_id, employee_id, simulation_year,
       'missing_employee_references' as error_type, 'error' as severity,
       'Employee not found in baseline workforce' as error_description,
       NULL as error_value
FROM missing_employee_references

-- ... Continue for all validation test types ...
```

### Downstream Contributions Validation

```sql
-- dbt/models/data_quality/dq_employee_contributions_validation.sql
-- Validation for downstream employee contributions model

{{ config(
    materialized='view',
    tags=['data_quality', 'contributions', 'validation']
) }}

WITH scoped_contributions AS (
  SELECT * FROM {{ ref('int_employee_contributions') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Test 1: IRS + Catch-up Limit Compliance
irs_limit_violations AS (
  SELECT
    c.scenario_id, c.plan_design_id, c.employee_id, c.simulation_year,
    c.final_annual_contribution_amount,
    p.annual_contribution_limit +
      CASE WHEN c.employee_age >= 50 THEN p.catch_up_contribution_limit ELSE 0 END as max_allowed,
    'irs_limit_violation' as validation_error
  FROM scoped_contributions c
  JOIN {{ ref('dim_plan_designs') }} p ON c.plan_design_id = p.plan_design_id
  WHERE c.final_annual_contribution_amount > (
    p.annual_contribution_limit +
    CASE WHEN c.employee_age >= 50 THEN p.catch_up_contribution_limit ELSE 0 END
  )
),

-- Test 2: Plan Rate Cap Compliance
plan_rate_violations AS (
  SELECT
    c.scenario_id, c.plan_design_id, c.employee_id, c.simulation_year,
    c.final_annual_contribution_amount,
    ROUND(c.prorated_annual_salary * p.employee_max_deferral_rate, 2) as max_by_rate,
    'plan_rate_violation' as validation_error
  FROM scoped_contributions c
  JOIN {{ ref('dim_plan_designs') }} p ON c.plan_design_id = p.plan_design_id
  WHERE c.final_annual_contribution_amount > ROUND(c.prorated_annual_salary * p.employee_max_deferral_rate, 2) + 0.01
),

-- Test 3: Completeness vs Active Accumulator Employees
missing_contributions AS (
  SELECT
    acc.scenario_id, acc.plan_design_id, acc.employee_id, acc.simulation_year,
    'missing_contribution_calculation' as validation_error
  FROM {{ ref('int_deferral_rate_state_accumulator') }} acc
  WHERE acc.simulation_year = {{ var('simulation_year') }}
    AND acc.is_current = TRUE
    AND acc.is_active = TRUE
    AND acc.current_deferral_rate > 0.0000
    AND NOT EXISTS (
      SELECT 1 FROM scoped_contributions c
      WHERE c.scenario_id = acc.scenario_id
        AND c.plan_design_id = acc.plan_design_id
        AND c.employee_id = acc.employee_id
        AND c.simulation_year = acc.simulation_year
    )
)

-- Summary
SELECT 'irs_limit_violations' as validation_test, COUNT(*) as failure_count, 'error' as severity FROM irs_limit_violations
UNION ALL
SELECT 'plan_rate_violations', COUNT(*), 'error' FROM plan_rate_violations
UNION ALL
SELECT 'missing_contributions', COUNT(*), 'error' FROM missing_contributions
```

### Schema-Level dbt Tests

```yaml
# dbt/models/intermediate/schema.yml - Enhanced with comprehensive data quality tests

version: 2

models:
  - name: int_deferral_rate_state_accumulator
    description: "Deferral rate state accumulator with comprehensive data quality validation"

    tests:
      # Composite uniqueness test
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - scenario_id
            - plan_design_id
            - employee_id
            - simulation_year
            - as_of_month
          config:
            severity: error

      # Row count expectations
      - dbt_expectations.expect_table_row_count_to_be_between:
          min_value: 1
          max_value: 100000
          config:
            severity: warn

    columns:
      - name: current_deferral_rate
        description: "Employee deferral rate (0% to 100%)"
        tests:
          # Range validation for deferral rates
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 0.0000
              max_value: 1.0000
              strictly: false
              config:
                severity: error
          # Not null validation
          - not_null:
              config:
                severity: error

      - name: employee_id
        description: "Employee identifier with referential integrity"
        tests:
          # Composite referential integrity with baseline workforce
          - dbt_utils.relationships_where:
              to: ref('int_baseline_workforce')
              field: employee_id
              from_condition: "is_active = TRUE AND simulation_year = {{ var('simulation_year') }}"
              to_condition: "employment_status = 'active' AND simulation_year = {{ var('simulation_year') }}"
              config:
                severity: error

      - name: source_type
        description: "Source of deferral rate change"
        tests:
          # Valid source type values
          - accepted_values:
              values: ['enrollment', 'escalation', 'baseline', 'carryforward']
              config:
                severity: error

      - name: is_current
        description: "Current state flag validation"
        tests:
          # Boolean validation
          - accepted_values:
              values: [true, false]
              config:
                severity: error

      - name: simulation_year
        description: "Simulation year validation"
        tests:
          # Reasonable year range
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 2020
              max_value: 2050
              strictly: false
              config:
                severity: warn

      - name: state_version
        description: "State version incrementing validation"
        tests:
          # Positive version numbers
          - dbt_expectations.expect_column_values_to_be_between:
              min_value: 1
              max_value: 1000
              strictly: false
              config:
                severity: warn

  # Data Quality validation model tests
  - name: dq_deferral_rate_state_validation
    description: "Data quality validation results for deferral rate state accumulator"
    tests:
      # Critical: All validation tests should return 0 failures
      - dbt_expectations.expect_column_max_to_be_between:
          column: failure_count
          min_value: 0
          max_value: 0
          config:
            severity: error
            error_if: ">= 1"
```

### Integration with Orchestration

```python
# run_multi_year.py - Tag-based data quality validation with severity handling

def validate_data_quality_with_severity(year: int, config: SimulationConfig):
    """Run data quality validation with severity-based failure handling."""

    logger.info(f"Running comprehensive data quality validation for year {year}")

    # Build complete variable context
    vars_dict = {
        "simulation_year": year,
        "scenario_id": config.scenario_id,
        "plan_design_id": config.plan_design_id or "default"
    }
    vars_str = json.dumps(vars_dict)

    # Build all data quality models using tag selector
    dbt_cmd_with_retry([
        "dbt", "build",
        "--select", "tag:data_quality",
        "--vars", vars_str,
        "--fail-fast"
    ])

    # Check validation results with severity handling
    conn = get_database_connection()
    try:
        # Get error-level failures (should cause immediate failure)
        error_results = conn.execute("""
            SELECT validation_test, failure_count, severity
            FROM dq_deferral_rate_state_validation
            WHERE failure_count > 0 AND severity = 'error'
        """).fetchall()

        # Get warning-level failures (log but don't fail)
        warning_results = conn.execute("""
            SELECT validation_test, failure_count, severity
            FROM dq_deferral_rate_state_validation
            WHERE failure_count > 0 AND severity = 'warn'
        """).fetchall()

        # Also check downstream contributions validation
        contrib_errors = conn.execute("""
            SELECT validation_test, failure_count, severity
            FROM dq_employee_contributions_validation
            WHERE failure_count > 0 AND severity = 'error'
        """).fetchall()

        # Handle warnings (log but continue)
        if warning_results:
            warning_summary = "\n".join([
                f"  - {test}: {count} warnings"
                for test, count, severity in warning_results
            ])
            logger.warning(f"Data quality warnings for year {year}:\n{warning_summary}")

        # Handle errors (fail fast)
        all_errors = error_results + contrib_errors
        if all_errors:
            error_summary = "\n".join([
                f"  - {test}: {count} failures"
                for test, count, severity in all_errors
            ])

            # Get sample detailed failures for debugging
            sample_failures = conn.execute("""
                SELECT error_type, scenario_id, plan_design_id, employee_id,
                       error_description, error_value
                FROM dq_deferral_rate_state_validation_details
                WHERE severity = 'error'
                LIMIT 5
            """).fetchall()

            failure_details = "\n".join([
                f"    {error_type}: {employee_id} - {description} ({value})"
                for error_type, scenario_id, plan_id, employee_id, description, value in sample_failures
            ]) if sample_failures else "No detailed failures available"

            raise ValueError(
                f"Data quality validation FAILED for year {year}:\n{error_summary}\n\n" +
                f"Sample failures:\n{failure_details}"
            )

        logger.info(f"Data quality validation passed for year {year}")

    finally:
        conn.close()

# Enhanced phase integration with quality gates
def run_year_simulation_with_quality_gates(year: int, config: SimulationConfig):
    """Run year simulation with integrated quality gates after each phase."""

    # ... existing phase execution ...

    # Quality Gate 2: Validate accumulator after building
    logger.info(f"Quality Gate 2: Accumulator validation for year {year}")
    dbt_cmd_with_retry([
        "dbt", "test",
        "--select", "int_deferral_rate_state_accumulator",
        "--vars", vars_str,
        "--fail-fast"
    ])
    validate_data_quality_with_severity(year, config)  # Custom validation

    # ... continue with other phases ...

    # Quality Gate 4: Final validation after all models built
    logger.info(f"Quality Gate 4: Comprehensive validation for year {year}")
    dbt_cmd_with_retry([
        "dbt", "test",
        "--select", "tag:data_quality tag:marts",
        "--vars", vars_str
    ])
```

### Monitoring Dashboard Queries

### Monitoring Views (dbt models under monitoring/)

```sql
-- dbt/models/monitoring/accumulator_health_summary.sql
-- Daily accumulator health monitoring view

{{ config(
    materialized='view',
    tags=['monitoring', 'health']
) }}

-- Monitoring query 1: Daily state health check
SELECT
SELECT
  simulation_year,
  COUNT(*) as total_employee_states,
  COUNT(*) FILTER (WHERE is_current = TRUE) as current_states,
  COUNT(*) FILTER (WHERE is_active = TRUE) as active_employees,
  AVG(current_deferral_rate) as avg_deferral_rate,
  MIN(current_deferral_rate) as min_deferral_rate,
  MAX(current_deferral_rate) as max_deferral_rate,
  COUNT(DISTINCT source_type) as source_type_variety
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE last_updated_at >= CURRENT_DATE - INTERVAL '7 days'  -- Recent data only
GROUP BY simulation_year
ORDER BY simulation_year
```

```sql
-- dbt/models/monitoring/cross_year_transitions_summary.sql
-- Cross-year transition monitoring

{{ config(
    materialized='view',
    tags=['monitoring', 'transitions']
) }}

-- Monitoring query 2: Cross-year transition summary
SELECT
SELECT
  curr.simulation_year,
  COUNT(*) as total_transitions,
  COUNT(*) FILTER (WHERE curr.source_type = 'carryforward') as carryforward_count,
  COUNT(*) FILTER (WHERE curr.source_type = 'enrollment') as enrollment_changes,
  COUNT(*) FILTER (WHERE curr.source_type = 'escalation') as escalation_changes,
  AVG(ABS(curr.current_deferral_rate - prev.current_deferral_rate)) as avg_rate_change
FROM int_deferral_rate_state_accumulator curr
LEFT JOIN int_deferral_rate_state_accumulator prev
  ON curr.employee_id = prev.employee_id
  AND curr.scenario_id = prev.scenario_id
  AND curr.simulation_year = prev.simulation_year + 1
WHERE curr.is_current = TRUE
  AND prev.is_current = TRUE
GROUP BY curr.simulation_year
ORDER BY curr.simulation_year;

-- Monitoring query 3: Data quality trend analysis
CREATE OR REPLACE VIEW v_data_quality_trends AS
SELECT
  DATE_TRUNC('day', last_updated_at) as validation_date,
  COUNT(*) as total_validations,
  SUM(CASE WHEN current_deferral_rate BETWEEN 0.0000 AND 1.0000 THEN 1 ELSE 0 END) as valid_rates,
  COUNT(*) FILTER (WHERE source_type = 'enrollment') as enrollment_sourced,
  COUNT(*) FILTER (WHERE is_active = TRUE) as active_employees
FROM int_deferral_rate_state_accumulator
WHERE last_updated_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', last_updated_at)
ORDER BY validation_date;
```

## Implementation Tasks

### Phase 1: Core Validation Models
- [ ] **Create `dq_deferral_rate_state_validation.sql`** with year-scoped validation logic
- [ ] **Create `dq_deferral_rate_state_validation_details.sql`** for actionable failure details
- [ ] **Create `dq_employee_contributions_validation.sql`** for downstream integrity
- [ ] **Implement 12+ validation tests** with deterministic temporal checks and severity levels
- [ ] **Add monthly grain enforcement** and composite key referential integrity

### Phase 2: Schema-Level Tests Integration
- [ ] **Add dbt tests to schema.yml** for model and column-level validation
- [ ] **Configure test severity levels** (error vs. warn) appropriately
- [ ] **Test dbt test execution** in CI/CD pipeline and local development
- [ ] **Document test failure remediation** procedures

### Phase 3: Orchestration Integration
- [ ] **Integrate validation calls** into `run_multi_year.py` workflow
- [ ] **Add validation error handling** with clear error messages
- [ ] **Implement validation checkpoints** after critical model builds
- [ ] **Add cross-year consistency validation** for multi-year runs

### Phase 4: Monitoring & Integration
- [ ] **Create monitoring models** under `dbt/models/monitoring/` with view materialization
- [ ] **Integrate tag-based validation** into orchestrator with severity-based failure handling
- [ ] **Add JSON reporting capability** for external alerting hooks
- [ ] **Test performance optimization** with year-scoped queries and ephemeral details
- [ ] **Document validation architecture** and remediation procedures for each test type

## Dependencies

### Story Dependencies
- **S036-03**: Temporal State Tracking (needs working accumulator)
- **S036-05**: Update Orchestrator (needs orchestration integration points)

### Technical Dependencies
- Working `int_deferral_rate_state_accumulator` model
- `dbt-expectations` package for advanced testing
- `dbt-utils` package for combination tests
- Orchestration framework for validation integration

### Blocking for Other Stories
- **S036-07**: Performance Testing (needs data quality baseline)

## Success Metrics

### Validation Coverage & Accuracy
- [ ] **All 12+ validation tests implemented** with proper year/scenario scoping
- [ ] **Deterministic temporal checks** using simulation year boundaries not wall clock
- [ ] **Monthly grain enforcement** with 12 rows per active employee validation
- [ ] **Downstream contributions validation** with IRS/plan limit compliance
- [ ] **Composite key referential integrity** across scenario/plan/employee dimensions

### Data Quality Assurance & Performance
- [ ] **Severity-based failure handling** with error vs. warn level responses
- [ ] **Year-scoped validation execution** filtering by simulation_year for performance
- [ ] **Detailed failure records** with actionable employee/scenario/error information
- [ ] **Tag-based orchestrator integration** with fail-fast on error-level failures
- [ ] **Monitoring views** materialized under dbt/models/monitoring/ structure

### Integration & Automation
- [ ] **Tag-based quality gates** integrated in orchestration after each phase
- [ ] **Complete variable context** passing scenario_id and plan_design_id
- [ ] **JSON reporting capability** for external alerting hooks if needed
- [ ] **Performance optimized** with scoped queries and ephemeral materialization
- [ ] **Cross-year consistency validation** ensuring accumulator continuity

## Testing Strategy

### Validation Test Cases
```sql
-- Test case 1: Inject duplicate states (should be caught)
INSERT INTO int_deferral_rate_state_accumulator
  (scenario_id, plan_design_id, employee_id, simulation_year, as_of_month, ...)
VALUES
  ('test', 'plan1', 'emp1', 2025, '2025-01-01', ...),
  ('test', 'plan1', 'emp1', 2025, '2025-01-01', ...);  -- Duplicate

-- Test case 2: Invalid deferral rate ranges (should be caught)
INSERT INTO int_deferral_rate_state_accumulator
  (employee_id, current_deferral_rate, ...)
VALUES ('emp2', -0.0500, ...);  -- Negative rate

-- Test case 3: Missing referential integrity (should be caught)
INSERT INTO int_deferral_rate_state_accumulator
  (employee_id, ...)
VALUES ('nonexistent_emp', ...);  -- Employee not in baseline
```

### Performance Testing
```python
# Validation performance test
def test_validation_performance():
    start_time = time.time()
    validate_accumulator_data_quality(2025)
    validation_time = time.time() - start_time

    assert validation_time < 30.0  # Should complete within 30 seconds
```

## Definition of Done

- [ ] **`dq_deferral_rate_state_validation.sql` model created** with all 10 validation tests
- [ ] **Schema-level dbt tests added** with appropriate severity configurations
- [ ] **Orchestration integration complete** with validation checkpoints
- [ ] **Monitoring queries operational** for dashboard and alerting
- [ ] **Comprehensive testing completed** with known failure scenarios
- [ ] **Documentation complete** with remediation procedures
- [ ] **Performance validated** with acceptable overhead
- [ ] **Ready for production use** with automated quality assurance

## Implementation Notes & Design Improvements

### Year and Scope Filtering Strategy
All validation CTEs now include **proper scoping**:
- `WHERE simulation_year = {{ var('simulation_year') }}` for performance and accuracy
- Composite key joins on `(scenario_id, plan_design_id, employee_id, simulation_year)`
- Prevents validation from scanning unnecessary historical data
- Enables multi-scenario and multi-plan validation support

### Deterministic Temporal Validation
**Replaced non-deterministic date checks** with simulation-year boundaries:
- **Before**: `effective_date > CURRENT_DATE` (depends on when validation runs)
- **After**: `effective_date > DATE('{{ var("simulation_year") }}-12-31')` (deterministic)
- Ensures consistent validation results regardless of execution time
- Enables reproducible data quality testing

### Monthly Grain Enforcement
**Added explicit monthly grain validation**:
- Test ensures exactly **12 rows per active employee per year**
- Validates `DATE_TRUNC('month', effective_date) = as_of_month` alignment
- Catches incomplete monthly state accumulation issues
- Critical for payroll-period aware contribution calculations

### Enhanced Audit Trail Validation
**Improved source event validation** with JSON array length checks:
- Event-sourced states (`enrollment`, `escalation`) must have non-empty `source_event_ids`
- Baseline/carryforward states should have empty or minimal audit trail
- Uses `json_array_length()` for proper DuckDB compatibility
- Enables complete event lineage tracking

### Cross-Year Carryforward Logic
**Refined state transition validation**:
- Only validates carryforward when no explicit enrollment/escalation changes exist
- Partitions by `(scenario_id, plan_design_id)` for proper first-year detection
- Accounts for multi-scenario environments with different start years
- Prevents false positives when legitimate rate changes occur

### Severity-Based Failure Handling
**Two-tier validation approach**:
- **Error severity**: Stops execution immediately (data corruption, uniqueness violations)
- **Warn severity**: Logs but continues (audit trail gaps, minor inconsistencies)
- Orchestrator handles each severity level appropriately
- Prevents over-alerting while catching critical issues

### Detailed Failure Model
**Actionable triage information**:
- `dq_deferral_rate_state_validation_details.sql` provides specific failure records
- Includes `scenario_id`, `plan_design_id`, `employee_id` for targeted remediation
- Error descriptions explain the specific validation failure
- Error values show the problematic data for debugging

### Downstream Integration
**Comprehensive validation coverage**:
- `dq_employee_contributions_validation.sql` validates contribution calculations
- IRS + catch-up limit compliance checks
- Plan rate cap enforcement validation
- Completeness checks ensure all active accumulator employees have contributions

### Performance Optimization
**Efficient validation execution**:
- Scoped CTEs prevent full table scans
- Ephemeral materialization for details model
- Tag-based orchestrator integration (`--select tag:data_quality`)
- View materialization for summary models

### Monitoring Architecture
**Production-ready monitoring**:
- Models under `dbt/models/monitoring/` with proper `materialized='view'`
- Health summary views for ongoing operational monitoring
- Trend analysis for data quality degradation detection
- JSON reporting capability for external alerting systems

This comprehensive validation suite ensures **data integrity, performance, and actionability** while supporting multi-scenario, multi-plan simulation environments with deterministic, reproducible validation results.
