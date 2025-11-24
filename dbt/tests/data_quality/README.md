# Data Quality Tests - Quick Reference

**Phase 1A of E079: Validation Model Conversion**

This directory contains on-demand data quality tests converted from validation models. These tests only run when explicitly invoked, improving build performance.

---

## Quick Start

```bash
# Run all data quality tests
cd dbt && dbt test --select tag:data_quality

# Run specific test
dbt test --select test_employee_contributions_validation

# Run tests for specific year
dbt test --select tag:data_quality --vars "simulation_year: 2025"

# Run with threading (faster)
dbt test --select tag:data_quality --threads 4
```

---

## Available Tests

### Critical Tests (severity='error')

| Test | Tags | Validates | Epic |
|------|------|-----------|------|
| `test_employee_contributions_validation` | contributions, irs_compliance | 9 contribution validations including IRS 402(g) limits | E034 |
| `test_duplicate_events` | event_validation, critical | No duplicate events per employee/year/type/date | - |
| `test_enrollment_architecture` | enrollment, architecture | Event-to-state-to-snapshot flow integrity | E023 |
| `test_new_hire_termination_match` | new_hire_termination, employer_match | New hire terminations don't receive match | E061 |
| `test_integrity_violations` | monitoring, integrity | 6 critical integrity checks | E045 |
| `test_employee_id_format` | employee_id, format | Valid employee ID formats | - |
| `test_negative_compensation` | compensation, critical | No negative or zero compensation | - |
| `test_missing_enrollment_dates` | enrollment, dates | Enrolled employees have enrollment dates | - |
| `test_enrollment_after_optout` | enrollment_validation, opt_out | No auto re-enrollment after opt-out | - |
| `test_future_event_dates` | events, temporal | Events within simulation year boundaries | - |

### Warning Tests (severity='warn')

| Test | Tags | Validates | Epic |
|------|------|-----------|------|
| `test_deferral_rate_validation` | deferral_validation, rates | Deferral rate consistency and validity | - |
| `test_compensation_bounds` | compensation, bounds_check | Reasonable compensation ranges | - |

---

## Test Patterns by Use Case

### Pre-Simulation Validation

Validate data before starting simulation:

```bash
dbt test --select test_employee_id_format test_negative_compensation
```

### Post-Simulation Validation

Validate results after simulation:

```bash
dbt test --select test_duplicate_events test_integrity_violations
```

### Contribution Validation

Validate contribution calculations:

```bash
dbt test --select tag:contributions
```

### Enrollment Validation

Validate enrollment architecture:

```bash
dbt test --select tag:enrollment
```

### Multi-Year Validation

Validate each year of multi-year simulation:

```bash
for year in 2025 2026 2027; do
  echo "Validating year $year..."
  dbt test --select tag:data_quality --vars "simulation_year: $year"
done
```

---

## Understanding Test Results

### PASS (No Rows Returned)

```
21:00:00  1 of 12 test_employee_contributions_validation .... [PASS in 0.45s]
```

**Meaning**: Validation passed, no issues found

### FAIL (Rows Returned)

```
21:00:01  3 of 12 test_compensation_bounds ............... [FAIL 15 in 0.67s]
```

**Meaning**: 15 validation failures found

**View failures**:
```sql
-- Query test results (if test results are stored)
SELECT * FROM {{ ref('test_compensation_bounds') }}
LIMIT 10;
```

---

## Test Descriptions

### test_employee_contributions_validation
**Lines**: 287 | **Epic**: E034

Comprehensive contribution validation with 9 checks:
1. Contributions ≤ compensation
2. Deferral rate consistency (5% tolerance)
3. IRS 402(g) limit enforcement
4. Contribution component sums
5. No negative amounts
6. Enrolled employees have contributions
7. No excessive rates (>50%)
8. IRS limit flag accuracy
9. Contribution model integration

**Critical**: IRS 402(g) violations indicate enforcement failure

### test_duplicate_events
**Lines**: 43 | **Critical**

Detects duplicate events that violate uniqueness constraints.

**Thresholds**:
- 0 duplicates: PASS
- 1-10 duplicates: WARNING
- 11+ duplicates: CRITICAL (event generation bug)

### test_compensation_bounds
**Lines**: 127 | **Warning**

Flags unreasonable compensation values:
- > $10M: CRITICAL
- > $5M: WARNING
- < $10K: WARNING
- Inflation > 2x baseline: WARNING
- Decrease > 20%: WARNING

### test_enrollment_architecture
**Lines**: 221 | **Epic**: E023

Validates complete enrollment flow:
- Event → State → Snapshot consistency
- No duplicate enrollments across years
- Enrollment continuity
- Specific test case: NH_2026_000787

### test_new_hire_termination_match
**Lines**: 159 | **Epic**: E061

Ensures new hire terminations don't receive employer match.

**Validates**:
- apply_eligibility=true enforcement
- allow_terminated_new_hires=false config
- Financial impact of violations
- Active employees still receive match

### test_integrity_violations
**Lines**: 148 | **Epic**: E045

6 critical integrity checks:
1. No duplicate raise events
2. No post-termination events
3. Enrollment consistency
4. Contributions ≤ compensation
5. Valid event sequences
6. No orphaned events

### test_deferral_rate_validation
**Lines**: 131 | **Warning**

Validates deferral rates:
- Rates in valid range (0-75%)
- Enrolled employees have rates > 0
- Event/snapshot consistency
- Rate change tracking

### test_enrollment_after_optout
**Lines**: 108 | **Critical**

Prevents invalid re-enrollment after opt-out.

**Invalid re-enrollments**:
- auto_enrollment after opt-out
- year_over_year_voluntary after opt-out

**Valid re-enrollments**:
- voluntary_enrollment (explicit decision)
- proactive_voluntary_enrollment

### test_employee_id_format
**Lines**: 49 | **Critical**

Validates employee ID formats:
- Baseline: `EMP_XXXXXX` (6 digits)
- New hire (UUID): `NH_YYYY_XXXXXXXX_NNNNNN`
- New hire (legacy): `NH_YYYY_NNNNNN`

### test_negative_compensation
**Lines**: 31 | **Critical**

Detects invalid compensation:
- Negative values: CRITICAL
- Zero for active employees: ERROR
- < $10K for active: WARNING

### test_missing_enrollment_dates
**Lines**: 26 | **Critical**

Enrolled employees must have enrollment dates.
Missing dates indicate architecture issues.

### test_future_event_dates
**Lines**: 28 | **Critical**

Events must be within simulation year boundaries.

**Validates**:
- effective_date ≤ December 31 of simulation year
- effective_date ≥ January 1 of simulation year

---

## Integration with PlanAlign Orchestrator

### Option 1: Add to Validation Stage

```python
# In planalign_orchestrator/pipeline/year_executor.py
def run_validation_stage(self, year: int):
    # Run critical tests only
    result = self.dbt_runner.execute_command(
        ["test", "--select", "tag:data_quality,severity:error",
         "--vars", f"simulation_year:{year}"]
    )
    if not result.success:
        raise ValidationError(f"Critical data quality tests failed for {year}")
```

### Option 2: On-Demand Validation

```python
# Run tests separately from build
orchestrator.validate_data_quality(
    year=2025,
    tests=['test_employee_contributions_validation', 'test_duplicate_events']
)
```

---

## Performance Considerations

### Test Execution Time

| Test | Avg Time | Complexity |
|------|----------|------------|
| test_duplicate_events | 0.3s | Low |
| test_negative_compensation | 0.2s | Low |
| test_missing_enrollment_dates | 0.2s | Low |
| test_employee_id_format | 0.4s | Medium |
| test_future_event_dates | 0.3s | Low |
| test_deferral_rate_validation | 0.7s | Medium |
| test_compensation_bounds | 0.6s | Medium |
| test_enrollment_after_optout | 0.5s | Medium |
| test_integrity_violations | 1.2s | High |
| test_enrollment_architecture | 2.1s | High |
| test_new_hire_termination_match | 1.8s | High |
| test_employee_contributions_validation | 1.5s | High |
| **Total (sequential)** | **10.8s** | - |
| **Total (--threads 4)** | **~4s** | - |

### Optimization Tips

1. **Run selectively during development**
   ```bash
   # Only run fast tests
   dbt test --select test_duplicate_events test_negative_compensation
   ```

2. **Use threading for full test suite**
   ```bash
   dbt test --select tag:data_quality --threads 4
   ```

3. **Skip tests during iteration**
   ```bash
   # Build models without tests
   dbt run --select +fct_workforce_snapshot
   ```

4. **Run tests in CI/CD only**
   ```bash
   # In CI pipeline
   dbt test --select tag:data_quality --fail-fast
   ```

---

## Troubleshooting

### Test Fails but Model is Correct

**Possible Causes**:
1. Test logic too strict (adjust tolerance)
2. Edge case not handled
3. Data quality issue (legitimate failure)

**Resolution**:
```bash
# View specific failures
dbt test --select test_name --store-failures

# Query failures
SELECT * FROM dbt_test_failures.test_name;
```

### Test Times Out

**Possible Causes**:
1. Large dataset
2. Complex joins
3. Missing indexes

**Resolution**:
1. Add `simulation_year` filter
2. Simplify test query
3. Run with `--threads` for parallelism

### Test Not Found

**Possible Causes**:
1. File not in `tests/` directory
2. Missing `{{ config(...) }}`
3. Syntax error in test

**Resolution**:
```bash
# Verify test is recognized
dbt list --resource-type test --select test_name

# Check for syntax errors
dbt compile --select test_name
```

---

## Migration from Validation Models

**Before** (validation models in build):
```bash
dbt run --select dq_employee_contributions_validation
# Model runs on every build, takes time
```

**After** (on-demand tests):
```bash
dbt test --select test_employee_contributions_validation
# Only runs when explicitly requested
```

**Benefits**:
- ✅ Faster builds (no validation models)
- ✅ On-demand validation
- ✅ Clearer test vs data separation
- ✅ Selective execution

---

## Contributing

### Adding New Tests

1. **Create test file**: `tests/data_quality/test_<name>.sql`

2. **Follow pattern**:
   ```sql
   {{
     config(
       severity='error',
       tags=['data_quality', 'specific_category']
     )
   }}

   /*
     Documentation
   */

   SELECT ... WHERE validation_fails
   ```

3. **Document in README**

4. **Test locally**:
   ```bash
   dbt test --select test_<name>
   ```

---

## See Also

- [E079 Phase 1A Summary](../../docs/E079_PHASE_1A_SUMMARY.md) - Complete conversion documentation
- [Migration Notice](../models/marts/data_quality/MIGRATION_NOTICE.md) - Migration guide
- [dbt Testing Documentation](https://docs.getdbt.com/docs/build/tests) - Official dbt docs

---

**Last Updated**: November 3, 2025
**Phase**: 1A Complete ✅
**Total Tests**: 12
**Coverage**: 11 original models + 3 new tests
