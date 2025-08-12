# Enrollment Participation Rate Fix - Rollback Plan

## Overview
This document provides rollback procedures for the enrollment participation rate fixes implemented to restore rates from 76%→52% degradation back to consistent ~76%.

## Changes Made

### Change 1: Remove Duplicate Model Execution
**File**: `/Users/nicholasamaral/planwise_navigator/run_multi_year.py`
**Line**: 617
**Change**: Removed `"int_employee_contributions",` from event_models list

**Rollback**:
```python
# Add back to line 617 in event_models list:
"int_employee_contributions",  # E034 Contribution calculations
```

### Change 2: Expand Base Workforce Selection
**File**: `/Users/nicholasamaral/planwise_navigator/dbt/models/marts/fct_workforce_snapshot.sql`
**Lines**: 40-83
**Change**: Added UNION to include employees from accumulator

**Rollback**:
```sql
-- Replace lines 40-83 with original logic:
{% else %}
-- Subsequent years: Use helper model to break circular dependency
-- This creates a temporal dependency (year N depends on year N-1) instead of circular
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    termination_date,
    employment_status
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
{% endif %}
```

## Rollback Procedure

### Step 1: Stop Any Running Simulations
```bash
# Check for running simulations and stop if needed
ps aux | grep python | grep run_multi_year
kill -9 <process_id_if_found>
```

### Step 2: Rollback Code Changes
```bash
cd /Users/nicholasamaral/planwise_navigator

# Option A: Use git to revert changes
git checkout HEAD~1 -- run_multi_year.py
git checkout HEAD~1 -- dbt/models/marts/fct_workforce_snapshot.sql

# Option B: Manual rollback (apply changes above)
```

### Step 3: Clean Database State
```bash
# Clear affected tables to ensure clean state
python -c "
import duckdb
conn = duckdb.connect('simulation.duckdb')
conn.execute('DELETE FROM fct_workforce_snapshot WHERE simulation_year >= 2025')
conn.execute('DELETE FROM int_employee_contributions WHERE simulation_year >= 2025')
conn.execute('DELETE FROM int_enrollment_state_accumulator WHERE simulation_year >= 2025')
conn.close()
"
```

### Step 4: Validate Rollback
```bash
# Test that models run with original logic
cd dbt
dbt run --select fct_workforce_snapshot --vars "simulation_year: 2025"
```

## Risk Assessment

### Low Risk
- **Change 1** (duplicate execution removal): Low risk - only removes redundant execution
- Database cleanup scripts are tested

### Medium Risk
- **Change 2** (workforce expansion): Medium risk - modifies core workforce logic
- May affect downstream models that depend on workforce snapshot

### Mitigation
- All changes are surgical and specific
- Rollback procedures tested
- Database backup recommended before implementing fixes
- Changes can be reverted individually if needed

## Testing After Rollback
Run the following to verify rollback success:
```bash
# 1. Check participation rates return to broken state (52%)
# 2. Verify no SQL compilation errors
# 3. Confirm multi-year simulation runs
python run_multi_year.py
```

## Contact
For rollback assistance, refer to this plan or consult the PlanWise Navigator development team.
