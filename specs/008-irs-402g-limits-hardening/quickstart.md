# Quickstart: IRS 402(g) Limits Hardening

**Feature**: 008-irs-402g-limits-hardening
**Date**: 2025-12-23

## Prerequisites

- Python 3.11 with virtual environment activated
- dbt-core 1.8.8 and dbt-duckdb 1.8.1 installed
- Hypothesis library installed (`pip install hypothesis`)
- Existing simulation database at `dbt/simulation.duckdb`

## Implementation Steps

### Step 1: Rename Seed File

```bash
# Rename for consistency with config_* naming convention
git mv dbt/seeds/irs_contribution_limits.csv dbt/seeds/config_irs_limits.csv
```

### Step 2: Update dbt Model References

Update these files to use the new seed name:

```bash
# Files requiring {{ ref('irs_contribution_limits') }} → {{ ref('config_irs_limits') }}
# 1. dbt/models/intermediate/events/int_employee_contributions.sql (lines 44, 55)
# 2. dbt/tests/data_quality/test_employee_contributions.sql (line 48)
# 3. dbt/tests/data_quality/test_employee_contributions_validation.sql (line 102)
# 4. dbt/models/marts/data_quality/dq_contribution_audit_trail.sql
# 5. dbt/models/marts/data_quality/dq_compliance_monitoring.sql
# 6. dbt/models/marts/data_quality/dq_employee_contributions_simple.sql
```

### Step 3: Fix Hardcoded Age Thresholds

Update `fct_workforce_snapshot.sql` to join with seed:
```sql
-- Replace hardcoded >= 50 with seed reference
CASE
    WHEN current_age >= il.catch_up_age_threshold THEN il.catch_up_limit
    ELSE il.base_limit
END
```

Update `test_employee_contributions_validation.sql` to join with seed:
```sql
-- Replace hardcoded CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END
-- with join to config_irs_limits
```

### Step 4: Reload Seed and Verify

```bash
cd dbt

# Load renamed seed
dbt seed --select config_irs_limits --threads 1

# Verify no broken references
dbt compile --threads 1

# Run models to verify
dbt run --threads 1
```

### Step 5: Run Property-Based Tests

```bash
# Run new property-based tests
pytest tests/unit/test_irs_402g_limits.py -v

# Verify 10,000+ examples pass
pytest tests/unit/test_irs_402g_limits.py -v --hypothesis-show-statistics
```

### Step 6: Run dbt Data Quality Tests

```bash
cd dbt

# Run all contribution-related tests
dbt test --select tag:irs_compliance --threads 1

# Run specific validation tests
dbt test --select test_employee_contributions test_employee_contributions_validation --threads 1
```

### Step 7: Validate End-to-End

```bash
# Run a full simulation year
cd ..
PYTHONPATH=. python -m planalign_orchestrator run --years 2025 --threads 1 --verbose

# Query to verify no violations
duckdb dbt/simulation.duckdb "
SELECT COUNT(*) as violations
FROM int_employee_contributions
WHERE annual_contribution_amount > applicable_irs_limit
"
# Expected: 0 violations
```

## Verification Checklist

- [ ] Seed file renamed from `irs_contribution_limits.csv` to `config_irs_limits.csv`
- [ ] All 6 dbt models/tests updated with new `{{ ref('config_irs_limits') }}`
- [ ] Hardcoded `>= 50` removed from `fct_workforce_snapshot.sql`
- [ ] Hardcoded limits removed from `test_employee_contributions_validation.sql`
- [ ] `dbt seed` completes without errors
- [ ] `dbt run` completes without errors
- [ ] Property-based tests pass with 10,000+ examples
- [ ] `dbt test` passes for IRS compliance tests
- [ ] Query confirms 0 limit violations in simulation data

## Troubleshooting

### "Relation config_irs_limits does not exist"
Run `dbt seed --select config_irs_limits --threads 1` to load the renamed seed.

### "Column catch_up_age_threshold not found"
Ensure the CSV column headers match exactly: `limit_year,base_limit,catch_up_limit,catch_up_age_threshold`

### Property tests timing out
Reduce `max_examples` in `@settings` decorator or check for slow database connections.

### dbt test failures
Check that all model references have been updated from `irs_contribution_limits` to `config_irs_limits`.
