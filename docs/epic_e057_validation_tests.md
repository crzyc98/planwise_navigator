# Epic E057: Data Quality Validation Tests Documentation

## Overview

Epic E057 implemented comprehensive data quality validation tests to ensure the new hire termination and proration fixes are working correctly and to prevent regression. This document provides complete instructions for running, interpreting, and maintaining these validation tests.

## Epic E057 Background

Epic E057 addressed two critical issues in the workforce simulation system:

1. **Fixed termination date generation** in `int_new_hire_termination_events.sql`:
   - Ensures termination dates are within simulation year
   - Ensures termination dates are after hire dates
   - Prevents invalid date sequences that break event sourcing

2. **Fixed prorated compensation** in `fct_workforce_snapshot.sql`:
   - Includes termination date in compensation period calculations
   - Provides accurate prorated compensation for partial-year employees
   - Maintains proper compensation accounting

## Validation Test Structure

### 1. Schema.yml Tests (Simple Rules)

Located in `/models/marts/schema.yml` under `fct_workforce_snapshot` data_tests:

```yaml
# Test E057-1: No future terminations beyond simulation year
- dbt_utils.expression_is_true:
    expression: "employment_status != 'terminated' OR EXTRACT(YEAR FROM termination_date) <= simulation_year"
    name: "e057_no_future_terminations"

# Test E057-2: No terminations before hire dates
- dbt_utils.expression_is_true:
    expression: "termination_date IS NULL OR termination_date >= employee_hire_date"
    name: "e057_no_terminations_before_hires"

# Test E057-3: New hire terminations properly bounded within simulation year
- dbt_utils.expression_is_true:
    expression: "detailed_status_code != 'new_hire_termination' OR (termination_date >= employee_hire_date + INTERVAL 1 DAY AND EXTRACT(YEAR FROM termination_date) = simulation_year)"
    name: "e057_new_hire_termination_bounds"
```

### 2. Comprehensive Validation Model

Location: `/models/marts/data_quality/dq_e057_new_hire_termination_validation.sql`

This model performs detailed validation across four categories:

#### A. Termination Date Validation
- **future_termination**: Termination dates in future years
- **termination_before_hire**: Termination dates before hire dates
- **new_hire_termination_missing_date**: New hire terminations without dates
- **new_hire_termination_wrong_year**: New hire terminations not in simulation year
- **new_hire_termination_invalid_sequence**: New hire terminations not after hire dates

#### B. Prorated Compensation Validation (1-day tolerance)
- **prorated_compensation_mismatch**: Calculated compensation doesn't match expected days worked
- **prorated_exceeds_annual**: Prorated compensation exceeds annual compensation
- **terminated_not_prorated**: Terminated employees with full annual compensation

#### C. New Hire Specific Validations
- **new_hire_termination_status_mismatch**: Status code vs. employment status inconsistency
- **terminated_new_hire_wrong_status**: Terminated new hires not classified correctly
- **new_hire_id_date_mismatch**: New hire ID vs. actual hire date mismatch

#### D. Regression Testing
- **existing_employee_wrong_termination_status**: Existing employees with incorrect termination classification
- **existing_employee_wrong_active_status**: Existing employees with incorrect active classification
- **active_employee_zero_compensation**: Active employees with zero compensation

## Running the Tests

### 1. Run Individual Schema Tests

```bash
# Test Epic E057 specific validations on workforce snapshot
dbt test --select fct_workforce_snapshot --vars "simulation_year: 2025" --threads 1 | grep -E "e057_"

# Test just the future terminations rule
dbt test --select test_name:e057_no_future_terminations --vars "simulation_year: 2025"

# Test just the terminations before hires rule
dbt test --select test_name:e057_no_terminations_before_hires --vars "simulation_year: 2025"

# Test just the new hire termination bounds rule
dbt test --select test_name:e057_new_hire_termination_bounds --vars "simulation_year: 2025"
```

### 2. Run Comprehensive Validation Model

```bash
# Build the validation model
dbt run --select dq_e057_new_hire_termination_validation --vars "simulation_year: 2025" --threads 1

# Run all tests on the validation model
dbt test --select dq_e057_new_hire_termination_validation --vars "simulation_year: 2025" --threads 1
```

### 3. Run All Epic E057 Tests

```bash
# Run both schema tests and validation model tests
dbt test --select tag:epic_e057 --vars "simulation_year: 2025" --threads 1

# Or run specific Epic E057 validation tests
dbt test --select dq_e057_new_hire_termination_validation fct_workforce_snapshot --vars "simulation_year: 2025" --threads 1
```

### 4. Multi-Year Testing

```bash
# Test across multiple simulation years
for year in 2025 2026 2027; do
  echo "Testing year $year"
  dbt run --select dq_e057_new_hire_termination_validation --vars "{simulation_year: $year}" --threads 1
  dbt test --select dq_e057_new_hire_termination_validation --vars "{simulation_year: $year}" --threads 1
done
```

## Interpreting Test Results

### Expected Results After Epic E057 Fixes

When Epic E057 fixes are properly implemented, you should see:

```bash
# SUCCESS: All tests pass
Done. PASS=27 WARN=1 ERROR=0 SKIP=0 TOTAL=28

# The validation model should return 0 rows (no failures)
# The warning is expected - it confirms no critical issues were found
```

### Pre-Fix Results (What Tests Catch)

Before Epic E057 fixes are applied, you'll see failures like:

```bash
# EXPECTED FAILURES: Tests correctly identify issues
Failure in test e057_no_future_terminations: Got 448 results, configured to fail if >0
Failure in test e057_no_terminations_before_hires: Got 36 results, configured to fail if >0
Failure in test e057_new_hire_termination_bounds: Got 485 results, configured to fail if >0
```

### Examining Specific Failures

```sql
-- Query the validation model to see specific failure details
SELECT
    validation_category,
    validation_rule,
    COUNT(*) as failure_count,
    validation_message
FROM dq_e057_new_hire_termination_validation
WHERE simulation_year = 2025
GROUP BY validation_category, validation_rule, validation_message
ORDER BY failure_count DESC;

-- Focus on the most critical issues
SELECT *
FROM dq_e057_new_hire_termination_validation
WHERE simulation_year = 2025
  AND severity = 'ERROR'
  AND validation_rule IN ('future_termination', 'termination_before_hire')
LIMIT 10;

-- Check prorated compensation issues
SELECT *
FROM dq_e057_new_hire_termination_validation
WHERE simulation_year = 2025
  AND validation_rule = 'prorated_compensation_mismatch'
LIMIT 10;
```

## Test Maintenance

### Adding New Validation Rules

1. **Simple Rules**: Add to `models/marts/schema.yml` under `fct_workforce_snapshot.data_tests`
2. **Complex Rules**: Add to the validation model in the appropriate CTE section
3. **Update Schema**: Add new rule values to `accepted_values` test in `models/marts/data_quality/schema.yml`

### Performance Considerations

- Tests run on single-threaded mode (`--threads 1`) for stability
- Validation model uses filtering to focus on new hires where needed
- Consider adding `WHERE` clauses to limit scope for large datasets

### Integration with CI/CD

Add to your CI pipeline:

```yaml
# In .github/workflows/dbt-test.yml
- name: Run Epic E057 Validation Tests
  run: |
    dbt test --select tag:epic_e057 --vars "simulation_year: 2025" --fail-fast
    dbt run --select dq_e057_new_hire_termination_validation --vars "simulation_year: 2025"
```

## Troubleshooting

### Common Issues

1. **Test Timeouts**: Use `--threads 1` for stability
2. **Missing Dependencies**: Ensure `fct_workforce_snapshot` is built first
3. **Year Variables**: Always specify `simulation_year` variable
4. **Database Locks**: Close other database connections before running

### Debug Commands

```bash
# Check if validation model compiled correctly
dbt compile --select dq_e057_new_hire_termination_validation

# Check dependencies
dbt deps --select dq_e057_new_hire_termination_validation

# Run with debug logging
dbt --debug run --select dq_e057_new_hire_termination_validation --vars "simulation_year: 2025"
```

### Data Quality Monitoring

Set up regular monitoring:

```bash
# Daily validation check (add to cron)
#!/bin/bash
YEAR=$(date +%Y)
dbt run --select dq_e057_new_hire_termination_validation --vars "simulation_year: $YEAR"
FAILURES=$(duckdb simulation.duckdb "SELECT COUNT(*) FROM dq_e057_new_hire_termination_validation WHERE severity = 'ERROR'")

if [ "$FAILURES" -gt 0 ]; then
    echo "ALERT: $FAILURES Epic E057 validation failures detected"
    # Send alert to monitoring system
fi
```

## Test Categories and Tags

- **epic_e057**: All Epic E057 related tests
- **critical**: Tests that must pass for production deployment
- **new_hire_termination**: Specific to new hire termination logic
- **data_quality**: General data quality validation tests
- **termination_date_validation**: Specific to termination date logic
- **comprehensive_validation**: Multi-category validation tests

## Summary

The Epic E057 validation framework provides:

1. **Comprehensive Coverage**: Tests all aspects of the termination and proration fixes
2. **Automated Detection**: Catches regressions before they reach production
3. **Clear Reporting**: Detailed failure messages for quick troubleshooting
4. **Performance Optimized**: Efficient execution even on large datasets
5. **Maintainable**: Easy to extend with new validation rules
6. **Production Ready**: Integrated with existing dbt test framework

Run these tests after any changes to termination logic, compensation calculations, or workforce snapshot generation to ensure Epic E057 fixes remain effective.
