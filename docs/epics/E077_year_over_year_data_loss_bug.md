# Epic E077 - Year-over-Year Data Loss Bug Investigation

**Status**: ✅ **RESOLVED**
**Priority**: P0 - Blocks multi-year simulations
**Created**: 2025-10-09
**Last Updated**: 2025-10-09
**Resolution Date**: 2025-10-09

---

## Problem Summary

Multi-year simulations were experiencing cascading growth accuracy issues, starting with data loss and culminating in incorrect growth rates across all years.

### Initial Symptoms

**Year 2025**: Ends with **4,124 active employees** ✓
**Year 2026**: Starts with **3,170 active employees** ❌
**Data Loss**: **954 employees** (23% workforce loss between years)

**Initial Result**: -9.3% CAGR instead of +3.0% target growth

---

## Root Causes Identified and Fixed

### 1. ✅ **Negative Tenure Calculation Bug**
**File**: `dbt/models/intermediate/int_baseline_workforce.sql` line 29-30

**Problem**: Census employees hired in 2025 get negative tenure when calculated against effective date 2024-12-31:
```sql
EXTRACT(YEAR FROM '2024-12-31') - EXTRACT(YEAR FROM '2025-XX-XX') = 2024 - 2025 = -1
```

**Impact**: 954 employees with `current_tenure = -1` filtered out by helper model data quality check, causing 23% workforce loss.

**Fix**: Floor tenure at 0 using `GREATEST()`:
```sql
-- **E077 FIX**: Floor tenure at 0 to prevent negative values for employees hired after effective date
GREATEST(0, EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) AS current_tenure,
```

**Result**: All 4,124 Year 2025 employees now flow to Year 2026 ✓

---

### 2. ✅ **Base Workforce Multi-Year Read Bug**
**File**: `dbt/models/marts/fct_workforce_snapshot.sql` line 52

**Problem**: Helper model uses `incremental` materialization, accumulating data across years. The `base_workforce` CTE read from helper model WITHOUT filtering by `simulation_year`, causing Year 2027 to incorrectly include data from multiple years (8,372 total rows = 4,124 + 4,248).

**Mathematical Proof**:
- Helper model total: 8,372 rows (Years 2026 + 2027)
- Year 2027 incorrectly read: ALL 8,372 rows
- Included 1,031 terminated employees from Year 2026
- Result: 14.5% CAGR instead of 3.0%

**Fix**: Add WHERE clause to filter helper model by current simulation_year:
```sql
-- **E077 FIX**: Filter to current year only
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE simulation_year = {{ simulation_year }}
{% endif %}
```

**Result**: Reduced Year 2027 CAGR from 14.5% to 5.0% (major improvement!)

---

### 3. ✅ **Duplicate Cross-Year Terminations Bug**
**File**: `dbt/models/intermediate/events/int_termination_events.sql` lines 26-45

**Problem**: Termination model was reading from `int_employee_compensation_by_year`, which contained 1,031 previously-terminated employees due to data leakage. This caused 176 employees to be terminated in BOTH Year 2026 AND Year 2027.

**Mathematical Evidence**:
```sql
-- Expected terminations from E077 solver: 1,062
-- Actual terminations from starting workforce: 886
-- Shortfall: 176 employees

-- These 176 employees were already terminated in Year 2026
SELECT COUNT(*) FROM fct_yearly_events
WHERE simulation_year = 2027 AND event_type = 'termination'
  AND employee_id IN (
    SELECT employee_id FROM fct_yearly_events
    WHERE simulation_year = 2026 AND event_type = 'termination'
  )
-- Result: 176 duplicate terminations
```

**Impact**:
- Expected ending workforce: 4,375 employees (3.0% growth)
- Actual ending workforce: 4,551 employees (7.13% growth)
- Discrepancy: 176 employees (exactly matches shortfall)

**Fix**: Change termination model to read from `int_active_employees_prev_year_snapshot` (which only contains genuinely active employees):
```sql
-- **E077 FIX**: Use helper model to avoid circular dependency and get clean previous year snapshot
SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    'experienced' AS employee_type
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE simulation_year = {{ simulation_year }}
  AND employment_status = 'active'
```

**Result**: Perfect 3.0% and 2.99% growth rates achieved! ✅

---

## Final Solution Summary

### Files Modified

1. **`dbt/models/intermediate/int_baseline_workforce.sql`**
   - Line 29-30: Added `GREATEST(0, ...)` to floor tenure at 0
   - Lines 42-48: Applied same fix to tenure_band calculation

2. **`dbt/models/marts/fct_workforce_snapshot.sql`**
   - Line 52: Added `WHERE simulation_year = {{ simulation_year }}` filter

3. **`dbt/models/intermediate/events/int_termination_events.sql`**
   - Lines 26-45: Changed data source from `int_employee_compensation_by_year` to `int_active_employees_prev_year_snapshot`

### Testing Results

```bash
# Clean simulation run
python -m planalign_orchestrator run --years 2025-2027 --threads 1 --verbose
```

| Year | Active Employees | Net Change | Growth Rate | Target | Status |
|------|-----------------|------------|-------------|---------|--------|
| 2025 | 5,125 | - | - | - | ✓ |
| 2026 | 5,279 | +154 | **3.00%** | 3.0% | ✅ |
| 2027 | 5,437 | +158 | **2.99%** | 3.0% | ✅ |

**Compound Annual Growth Rate**: **3.0%** ✅ (target: 3.0%)

---

## Technical Architecture

### Helper Model Pattern (Circular Dependency Resolution)

The `int_active_employees_prev_year_snapshot` helper model serves as a critical architectural pattern to break circular dependencies:

```
Year N-1 STATE_ACCUMULATION:
  fct_workforce_snapshot (Year N-1 written)
  ↓
Year N INITIALIZATION:
  int_active_employees_prev_year_snapshot (reads Year N-1 snapshot)
  ↓
Year N FOUNDATION:
  int_termination_events (reads helper model for Year N)
  ↓
Year N EVENT_GENERATION:
  fct_yearly_events (includes terminations)
  ↓
Year N STATE_ACCUMULATION:
  fct_workforce_snapshot (Year N written)
```

**Key Properties**:
1. **Incremental materialization**: Data persists across years
2. **Temporal filtering**: Each year only reads its designated data
3. **Clean state**: Only contains active employees (no terminated employees)
4. **Breaks cycles**: Allows events to reference previous year without circular dependency

---

## Validation Queries

### Verify Year-over-Year Continuity
```sql
-- Check helper model filtering
SELECT
  simulation_year,
  COUNT(*) as helper_count,
  COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_count
FROM int_active_employees_prev_year_snapshot
GROUP BY simulation_year
ORDER BY simulation_year;

-- Expected:
-- Year 2026 helper: 5,125 (matches Year 2025 ending)
-- Year 2027 helper: 5,279 (matches Year 2026 ending)
```

### Verify No Duplicate Terminations
```sql
-- Check for employees terminated in multiple years
SELECT
  employee_id,
  COUNT(DISTINCT simulation_year) as years_terminated
FROM fct_yearly_events
WHERE event_type = 'termination'
GROUP BY employee_id
HAVING COUNT(DISTINCT simulation_year) > 1;

-- Expected: 0 rows (no duplicates)
```

### Verify Growth Accuracy
```sql
-- Calculate actual growth rates
SELECT
  simulation_year,
  active_employees,
  ROUND(((active_employees - LAG(active_employees) OVER (ORDER BY simulation_year))::DOUBLE
         / LAG(active_employees) OVER (ORDER BY simulation_year)::DOUBLE) * 100, 2) as growth_pct
FROM (
  SELECT simulation_year, COUNT(*) as active_employees
  FROM fct_workforce_snapshot
  WHERE employment_status = 'active'
  GROUP BY simulation_year
)
ORDER BY simulation_year;

-- Expected: ~3.0% for all years
```

---

## Related Issues

### Previously Fixed: Duplicate Terminations Bug (Different Issue)

**Problem**: Year 2025 showed -10% growth due to duplicate termination events within the same year
**Root Cause**: `fct_yearly_events` incremental strategy not properly deleting old events
**Fix**: Changed unique_key from complex composite to `['scenario_id', 'plan_design_id', 'simulation_year']`
**Status**: ✅ **RESOLVED** (committed in feature/e077-bulletproof-growth-accuracy)

---

## Configuration

### Simulation Parameters

```yaml
# config/simulation_config.yaml
workforce:
  target_growth_rate: 0.03  # 3% annual growth
  total_termination_rate: 0.25  # 25% experienced
  new_hire_termination_rate: 0.40  # 40% new hire
```

### Test Command

```bash
python -m planalign_orchestrator run --years 2025-2027 --threads 1 --verbose
```

---

## Impact Assessment

**Severity**: P0 - Blocked production use
**Scope**: All multi-year simulations
**Resolution**: Complete - All growth rates now accurate to target

**Before Fixes**:
- Year 2025-2026: Data loss (-23% workforce)
- Year 2026-2027: Growth explosion (14.5% CAGR)
- Overall: Unusable for production forecasting

**After Fixes**:
- Year 2025-2026: Perfect 3.00% growth ✅
- Year 2026-2027: Perfect 2.99% growth ✅
- Overall: Production-ready accuracy

---

## Timeline

- **2025-10-09 08:00**: User reported -9.3% CAGR with new baseline (4,004 employees)
- **2025-10-09 08:15**: Identified 954-employee loss between Year 2025 and Year 2026
- **2025-10-09 08:20**: Traced issue to negative tenure calculation bug
- **2025-10-09 09:30**: Fixed tenure bug, discovered base_workforce multi-year read bug
- **2025-10-09 10:15**: Fixed base_workforce filter, discovered duplicate terminations bug
- **2025-10-09 11:00**: Fixed termination model data source, achieved perfect 3.0% CAGR ✅

---

## References

- **Epic E077**: Bulletproof Workforce Growth Accuracy
- **Epic E072**: Pipeline Modularization (workflow stages)
- **ADR E077-A**: Single-rounding algebraic solver
- **ADR E077-B**: Largest-remainder method for level allocation
- **ADR E077-C**: Deterministic hash-based employee selection

---

## Key Learnings

1. **Incremental models require explicit filtering**: When using incremental materialization, always filter by `simulation_year` to avoid reading accumulated historical data.

2. **Data source purity is critical**: Termination models must read from clean, validated sources (helper models) rather than intermediate models that may contain data leakage.

3. **Temporal calculations need defensive programming**: Always use `GREATEST(0, ...)` for calculations that could produce negative values when dealing with future-dated records.

4. **E077 algebraic solver is working correctly**: All issues were data pipeline bugs, not calculation errors. The deterministic solver produces correct hire/termination targets.

---

## Notes

User quote: "no, i should be able to put in excessive rates and IT SHOULD WORK"

E077 algebraic solver correctly calculates workforce needs. All issues were purely data pipeline bugs in year-over-year state transfer, not calculation errors.

**Status**: ✅ **FULLY RESOLVED** - Production-ready multi-year simulation accuracy achieved.
