# Quickstart: Testing Service-Based Core Contributions

**Date**: 2026-01-05
**Feature Branch**: `009-fix-service-based-core-contribution`

## Prerequisites

1. Activate virtual environment:
   ```bash
   source .venv/bin/activate
   ```

2. Ensure PlanAlign is installed:
   ```bash
   planalign health
   ```

---

## Option 1: Manual Testing via PlanAlign Studio

### Step 1: Configure Scenario with Service Tiers

1. Launch PlanAlign Studio:
   ```bash
   planalign studio
   ```

2. Open or create a workspace

3. Navigate to **Configuration > DC Plan**

4. Set Core Contribution Mode:
   - **Core Status**: Select "Graded by Service"
   - **Add Tiers**:
     - Tier 1: 0-9 years → 6%
     - Tier 2: 10+ years → 8%

5. Save configuration

### Step 2: Run Simulation

```bash
planalign simulate 2025 --verbose
```

### Step 3: Verify Results

```bash
duckdb dbt/simulation.duckdb "
SELECT
  CASE
    WHEN applied_years_of_service < 10 THEN '0-9 years'
    ELSE '10+ years'
  END AS tenure_band,
  COUNT(*) AS employee_count,
  ROUND(AVG(core_contribution_rate) * 100, 2) AS avg_rate_pct,
  ROUND(SUM(employer_core_amount), 2) AS total_contributions
FROM int_employer_core_contributions
WHERE simulation_year = 2025
  AND employer_core_amount > 0
GROUP BY 1
ORDER BY 1
"
```

**Expected Output**:
```
┌─────────────┬────────────────┬──────────────┬─────────────────────┐
│ tenure_band │ employee_count │ avg_rate_pct │ total_contributions │
├─────────────┼────────────────┼──────────────┼─────────────────────┤
│ 0-9 years   │ XXXX           │ 6.00         │ XXXXXXX.XX          │
│ 10+ years   │ XXXX           │ 8.00         │ XXXXXXX.XX          │
└─────────────┴────────────────┴──────────────┴─────────────────────┘
```

---

## Option 2: Testing via dbt Variables

### Step 1: Set Variables in dbt_project.yml

```yaml
# dbt/dbt_project.yml
vars:
  simulation_year: 2025
  employer_core_enabled: true
  employer_core_status: 'graded_by_service'
  employer_core_contribution_rate: 0.08  # Fallback rate
  employer_core_graded_schedule:
    - min_years: 0
      max_years: 10
      rate: 6.0
    - min_years: 10
      max_years: null
      rate: 8.0
```

### Step 2: Run dbt Model

```bash
cd dbt
dbt run --select int_employer_core_contributions --threads 1
```

### Step 3: Verify Results

```bash
duckdb simulation.duckdb "
SELECT
  applied_years_of_service,
  core_contribution_rate,
  COUNT(*) as employees
FROM int_employer_core_contributions
WHERE simulation_year = 2025
GROUP BY 1, 2
ORDER BY 1
"
```

---

## Test Scenarios

### Scenario 1: Two-Tier Service Schedule

**Config**:
- 0-9 years: 6%
- 10+ years: 8%

**Verification Query**:
```sql
SELECT
  employee_id,
  applied_years_of_service,
  core_contribution_rate,
  employer_core_amount
FROM int_employer_core_contributions
WHERE simulation_year = 2025
ORDER BY applied_years_of_service
LIMIT 20
```

### Scenario 2: Flat Rate (Regression Test)

**Config**:
- employer_core_status: 'flat'
- employer_core_contribution_rate: 0.08

**Expected**: All employees receive 8% regardless of tenure.

```sql
SELECT
  DISTINCT core_contribution_rate
FROM int_employer_core_contributions
WHERE simulation_year = 2025
  AND employer_core_amount > 0
```

**Expected Output**: Single row with `0.08`

### Scenario 3: Disabled Core Contributions

**Config**:
- employer_core_status: 'none'

**Expected**: All employees receive 0%.

```sql
SELECT
  SUM(employer_core_amount) as total
FROM int_employer_core_contributions
WHERE simulation_year = 2025
```

**Expected Output**: `0.00`

---

## Troubleshooting

### Issue: All employees still getting flat rate

**Check 1**: Verify variables are being read
```bash
cd dbt
dbt compile --select int_employer_core_contributions --vars "simulation_year: 2025"
cat target/compiled/planalign_engine/models/intermediate/int_employer_core_contributions.sql | grep -A5 "employer_core_status"
```

**Check 2**: Verify tenure data is available
```sql
SELECT
  employee_id,
  current_tenure,
  FLOOR(current_tenure) as years_of_service
FROM int_workforce_snapshot_optimized
WHERE simulation_year = 2025
LIMIT 10
```

### Issue: Tenure is NULL for some employees

New hires in the current simulation year may not have tenure calculated yet. The fix should use `COALESCE(years_of_service, 0)` to treat them as 0 years tenure.

---

## Fast Validation Script

```bash
#!/bin/bash
# Save as: scripts/validate_service_tiers.sh

echo "=== Service Tier Contribution Validation ==="

# Check if graded_by_service is configured
CONFIG_STATUS=$(duckdb dbt/simulation.duckdb -csv -noheader "
SELECT DISTINCT contribution_method
FROM int_employer_core_contributions
WHERE simulation_year = 2025
LIMIT 1
")

echo "Contribution Method: $CONFIG_STATUS"

# Check rate distribution
echo ""
echo "Rate Distribution by Tenure:"
duckdb dbt/simulation.duckdb "
SELECT
  applied_years_of_service,
  ROUND(core_contribution_rate * 100, 2) as rate_pct,
  COUNT(*) as employees
FROM int_employer_core_contributions
WHERE simulation_year = 2025
  AND employer_core_amount > 0
GROUP BY 1, 2
ORDER BY 1
"

echo ""
echo "=== Validation Complete ==="
```

---

## Related Documentation

- [spec.md](./spec.md) - Feature specification
- [plan.md](./plan.md) - Implementation plan
- [research.md](./research.md) - Bug investigation findings
- [data-model.md](./data-model.md) - Entity definitions
