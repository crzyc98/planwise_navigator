# Research: Fix Hire Date Before Termination Date Ordering

**Feature**: 022-fix-hire-termination-order
**Date**: 2026-01-21

## Research Questions

### RQ1: How does the current `generate_termination_date` macro work?

**Findings**:
- Location: `dbt/macros/generate_termination_date.sql`
- Current implementation:
  ```sql
  CAST('{{ simulation_year }}-01-01' AS DATE)
  + INTERVAL (
      (ABS(HASH({{ employee_id_column }} || '|' || CAST({{ simulation_year }} AS VARCHAR) || '|DATE|{{ random_seed }}')) % 365)
  ) DAY
  ```
- The macro produces a date between January 1 and December 31 of the simulation year
- **Problem**: For employees hired mid-year, the hash can produce a date before their hire date

**Decision**: Modify macro to accept `hire_date_column` parameter and calculate days between hire_date and year_end, then add random offset from hire_date.

**Rationale**: This ensures termination date is always >= hire_date while maintaining deterministic distribution.

**Alternative Rejected**: Post-filtering (reject terminations before hire) - this would change selection counts and create non-deterministic workforce size.

---

### RQ2: How does `int_new_hire_termination_events.sql` handle this issue?

**Findings**:
- Location: `dbt/models/intermediate/events/int_new_hire_termination_events.sql`
- Already implements the correct pattern (lines 48-73):
  ```sql
  -- Compute a guaranteed in-year candidate termination date when possible
  CASE
      WHEN e.days_until_year_end >= 1 THEN
          e.hire_date
          + CAST(
              CAST(
                1 + (CAST(SUBSTR(e.employee_id, -3) AS INTEGER) % LEAST(240, e.days_until_year_end))
                AS VARCHAR
              ) || ' days' AS INTERVAL
            )
      ELSE NULL
  END AS candidate_termination_date

  -- Filter: candidate_termination_date > et.hire_date
  ```

**Decision**: Use similar pattern in experienced terminations macro, but generalized for reuse.

**Rationale**: Proven pattern already in production for new hire terminations.

---

### RQ3: Where does `fct_workforce_snapshot` get tenure for terminated employees?

**Findings**:
- Location: `dbt/models/marts/fct_workforce_snapshot.sql`
- Tenure flows through from `base_workforce` CTE without modification
- For year 1: comes from `int_baseline_workforce` (calculated to Dec 31)
- For subsequent years: comes from `int_active_employees_prev_year_snapshot`
- Termination events DO carry their own `employee_tenure` (calculated at termination date)
- **Problem**: The snapshot doesn't use the event's tenure - it uses the base workforce tenure

**Decision**: In the final select, use `CASE WHEN employment_status = 'terminated' THEN event_tenure ELSE base_tenure END` pattern.

**Rationale**: Terminated employees should show tenure at termination, active employees should show tenure at year-end.

---

### RQ4: How does the Polars pipeline generate termination dates?

**Findings**:
- Location: `planalign_orchestrator/polars_event_factory.py:394-423`
- Current implementation:
  ```python
  year_start = date(simulation_year, 1, 1)
  return (
      pl.lit(year_start) +
      pl.duration(days=(
          (pl.col('employee_id').hash() +
           pl.lit(simulation_year * 1000000) +
           pl.lit(random_seed * 31337)
          ) % 365
      ).cast(pl.Int64))
  ).cast(pl.Date)
  ```
- Same problem as SQL macro - uses year start as base

**Decision**: Modify to accept `hire_date_column` and compute: `hire_date + (hash % days_until_year_end)`

**Rationale**: Maintains parity with SQL implementation.

---

### RQ5: What is the correct tenure calculation for terminated employees?

**Findings**:
- User example: hire=2024-08-01, term=2026-01-10 → should be 1 year (not 2)
- Formula: `floor((termination_date - hire_date).days / 365.25)`
- The `calculate_tenure` macro already supports this via third parameter `termination_date_column`

**Calculation verification**:
```
2024-08-01 to 2026-01-10 = 528 days
528 / 365.25 = 1.445
floor(1.445) = 1 year ✓
```

**Decision**: Ensure `fct_workforce_snapshot` uses `calculate_tenure(hire_date, year_end, termination_date)` for all employees, which automatically uses termination_date when present.

**Rationale**: The macro already handles this correctly - just need to use it properly in the snapshot.

---

### RQ6: What data quality tests should be added?

**Findings**:
- FR-005: Validate no termination_date < hire_date exists
- FR-008: Validate terminated employees have tenure = floor((termination_date - hire_date) / 365.25)

**Decision**: Create two dbt data quality tests:
1. `test_termination_after_hire.sql` - checks `fct_workforce_snapshot` and `fct_yearly_events`
2. `test_tenure_at_termination.sql` - validates tenure formula for terminated employees

**Rationale**: Constitution III requires test-first development; these tests will fail before implementation and pass after.

---

## Summary of Decisions

| Decision | Approach | Files Affected |
|----------|----------|----------------|
| D1: Termination date generation | Add `hire_date_column` param, compute offset from hire_date | `generate_termination_date.sql` |
| D2: Experienced terminations | Pass hire_date to macro | `int_termination_events.sql` |
| D3: Snapshot tenure | Use `calculate_tenure` with termination_date param | `fct_workforce_snapshot.sql` |
| D4: Polars parity | Mirror SQL logic in Python | `polars_event_factory.py` |
| D5: Data quality | Add two validation tests | `tests/data_quality/` |

## Dependencies

- `generate_termination_date` macro modification must complete before model updates
- Tests should be created first (Constitution III: test-first)
- SQL changes should complete before Polars changes for validation reference
