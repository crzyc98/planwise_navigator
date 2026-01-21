# Research: Fix Termination Event Data Quality

**Feature**: 021-fix-termination-events
**Date**: 2026-01-21

## Root Cause Analysis

### Bug 1: Uniform Termination Dates

**Location**: `dbt/models/intermediate/events/int_termination_events.sql:100`

**Current Code**:
```sql
(CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date
```

**Root Cause**: The hash function uses only `employee_id` without incorporating `simulation_year`. Since `employee_id` is constant across years, the expression `HASH(w.employee_id) % 365` produces the **same day offset for every employee regardless of simulation year**.

Example: If `HASH('EMP_001') % 365 = 258`, then EMP_001 will always terminate on day 258 (September 15) in every simulation year.

**Why all employees get the same date**: The employee IDs in the workforce follow a pattern (e.g., `EMP_NNNN`). Many hash values modulo 365 collide, causing clustering. The specific date 2026-09-15 corresponds to day 258, which is a common collision point.

**Decision**: Incorporate `simulation_year` into the hash to produce year-specific distribution.

**Rationale**: Including the year in the hash changes the distribution per year while maintaining determinism for a given (employee_id, year) pair.

**Alternatives Considered**:
1. **Add random jitter** - Rejected: breaks determinism requirement (FR-008)
2. **Use employee hire_date** - Rejected: would create correlation between hire timing and termination timing
3. **Multiple hash inputs** - Selected: `HASH(employee_id || '|' || simulation_year || '|DATE')` produces unique per-year values

---

### Bug 2: Incorrect new_hire_active Status

**Location**: `dbt/models/marts/fct_workforce_snapshot.sql:749-779`

**Current Code (status classification)**:
```sql
CASE
    WHEN COALESCE(ec.is_new_hire, false) = true AND fwc.employment_status = 'active'
    THEN 'new_hire_active'
    ...
```

**Root Cause**: The `is_new_hire` flag is set in `employee_events_consolidated` (line 92):
```sql
COUNT(CASE WHEN event_type = 'hire' THEN 1 END) > 0 AS is_new_hire
```

However, employees from the baseline census (hired before simulation years) who appear in `unioned_workforce_raw` via the `existing` record source are NOT being properly filtered. The issue is in the deduplication logic (lines 257-278):

1. For Year 2+, `int_active_employees_prev_year_snapshot` provides employees who were NEW HIRES in Year 1
2. These employees have `employee_hire_date` in Year 1 (e.g., 2025)
3. In Year 2, they should NOT be classified as new hires, but if their record somehow joins with a hire event OR the hire date check fails, they get misclassified

**Specific Issue**: The status classification at line 761-762 checks:
```sql
WHEN fwc.employment_status = 'active' AND EXTRACT(YEAR FROM fwc.employee_hire_date) < sp.current_year
THEN 'continuous_active'
```

But this condition is AFTER the `is_new_hire` check. If `ec.is_new_hire` is unexpectedly `true` for an employee without a current-year hire event, they get misclassified as `new_hire_active`.

**Decision**: Add explicit validation that `is_new_hire` is only true when there is actually a hire event in the current simulation year, not carried forward from previous years.

**Rationale**: The root issue is the `employee_events_consolidated` CTE only looks at `current_year_events`, so `is_new_hire` should already be correct. Need to investigate why the join is producing unexpected results.

**Additional Investigation**: The bug may be in how `unioned_workforce_raw` merges new_hire records with existing records. Line 267 shows prioritization logic that may be incorrect.

---

### Bug 3: New Hire Terminations Missing Data

**Location**: `dbt/models/marts/fct_workforce_snapshot.sql:199-228`

**Current Code (new_hires CTE)**:
```sql
new_hires AS (
    SELECT
        ...
        CASE
            WHEN ec.is_new_hire_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            WHEN ec.has_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            ELSE NULL
        END AS termination_date,
        CASE
            WHEN ec.is_new_hire_termination THEN 'terminated'
            WHEN ec.has_termination THEN 'terminated'
            ELSE 'active'
        END AS employment_status,
        ...
    FROM {{ ref('fct_yearly_events') }} ye
    LEFT JOIN employee_events_consolidated ec ON ye.employee_id = ec.employee_id
    WHERE ye.event_type = 'hire'
```

**Root Cause**: The `is_new_hire_termination` flag depends on `event_category = 'new_hire_termination'` (line 84):
```sql
COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination
```

The issue is that `fct_yearly_events` may not have `event_category` properly set for new hire terminations. Check `int_new_hire_termination_events.sql` output:

Looking at line 122:
```sql
'new_hire_termination' AS termination_type,
```

This is `termination_type`, NOT `event_category`. The `employee_events_consolidated` CTE looks for `event_category = 'new_hire_termination'` but the field is named `termination_type` in the source.

**Decision**: Either rename the field to `event_category` in `int_new_hire_termination_events.sql`, or update `employee_events_consolidated` to check `termination_type`.

**Rationale**: This is a simple column name mismatch causing the join to fail silently (returns 0 for count).

**Alternatives Considered**:
1. **Rename in source** - Selected: cleaner, aligns with expected convention
2. **Add alias in fct_yearly_events** - More invasive change across event types
3. **Update consolidated CTE only** - Could miss other usages

---

## Design Decisions

### D1: Year-Aware Hash Function for Date Distribution

**Decision**: Use `HASH(employee_id || '|' || simulation_year || '|DATE') % 365` for termination date calculation.

**Rationale**:
- Maintains determinism (same employee + year + seed = same date)
- Produces different dates per year for the same employee
- Simple change with minimal risk

**Trade-off**: Employees who would have terminated on the same date in reality will now have different dates across years. This is acceptable because the original clustering was unrealistic anyway.

### D2: Explicit Hire Event Validation

**Decision**: Add explicit check in `detailed_status_code` logic:
```sql
WHEN COALESCE(ec.is_new_hire, false) = true
     AND EXISTS (SELECT 1 FROM current_year_events WHERE employee_id = fwc.employee_id AND event_type = 'hire')
     AND fwc.employment_status = 'active'
THEN 'new_hire_active'
```

**Rationale**: Belt-and-suspenders approach ensures no false positives even if upstream data has issues.

**Alternative Rejected**: Relying solely on `ec.is_new_hire` was the source of the bug.

### D3: Consistent Event Category Naming

**Decision**: Rename `termination_type` to `event_category` in `int_new_hire_termination_events.sql` to match the expected column in `fct_workforce_snapshot.sql`.

**Rationale**: Aligns with the existing pattern used elsewhere and fixes the root cause of the data propagation failure.

---

## Implementation Approach

### Phase 1: Fix Date Distribution (int_termination_events.sql)

1. Create new macro `generate_termination_date` that incorporates year
2. Update `int_termination_events.sql` to use the macro
3. Update `int_new_hire_termination_events.sql` to use the macro (if applicable)

### Phase 2: Fix Status Classification (fct_workforce_snapshot.sql)

1. Add explicit hire event existence check to `detailed_status_code` CASE
2. Add data quality test to validate no false positives

### Phase 3: Fix New Hire Termination Data (int_new_hire_termination_events.sql + fct_workforce_snapshot.sql)

1. Rename `termination_type` to `event_category` in output
2. Verify `is_new_hire_termination` flag now works correctly
3. Add data quality test for completeness

### Phase 4: Polars Pipeline Parity

1. Update `polars_state_pipeline.py` to use the same year-aware hash logic
2. Verify SQL/Polars parity with existing test infrastructure

---

## Validation Queries

### Verify Date Distribution
```sql
SELECT
    EXTRACT(MONTH FROM effective_date) AS term_month,
    COUNT(*) AS terminations,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM int_termination_events
WHERE simulation_year = 2026
GROUP BY 1
ORDER BY 1;
-- Expected: Each month should have 5-15% of terminations (roughly uniform)
```

### Verify Status Code Accuracy
```sql
SELECT
    detailed_status_code,
    COUNT(*) AS count,
    COUNT(CASE WHEN detailed_status_code = 'new_hire_active'
               AND employee_id NOT IN (SELECT employee_id FROM fct_yearly_events WHERE event_type = 'hire' AND simulation_year = 2026)
          THEN 1 END) AS false_positives
FROM fct_workforce_snapshot
WHERE simulation_year = 2026
GROUP BY 1;
-- Expected: false_positives = 0 for all status codes
```

### Verify New Hire Termination Completeness
```sql
SELECT
    COUNT(*) AS total_nh_terminations,
    COUNT(termination_date) AS with_term_date,
    COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) AS with_term_status
FROM fct_workforce_snapshot
WHERE simulation_year = 2026
  AND detailed_status_code = 'new_hire_termination';
-- Expected: All three counts should be equal
```
