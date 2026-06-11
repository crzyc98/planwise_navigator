# Feature Spec: Add scheduled_hours_per_week to Census + Fix Part-Time Eligibility Hours

**Branch**: `093-part-time-scheduled-hours` | **Date**: 2026-06-10 | **GitHub Issue**: #282

## Problem

Annual hours are currently prorated from employment dates alone (`days_employed × 2080/365`). A part-time employee on a 20 hr/week schedule is credited ~2080 hours if employed all year — making them eligible under a 1,000-hour plan requirement when they should have ~1,040 hours. Plan sponsors often supply `scheduled_hours_per_week` in the census file, and this data needs to flow through to eligibility.

**Root cause**: `int_employer_eligibility.sql` and `int_eligibility_computation_period.sql` hardcode `2080.0` with no concept of scheduled weekly hours. No `scheduled_hours_per_week` field exists anywhere in the census schema or staging models.

## Proposed Solution

### 1. Census Layer
- Add `scheduled_hours_per_week` to column alias normalization in `planalign_api/services/sql_security.py` (accepts `"hours_per_week"`, `"scheduled_hours"`, `"weekly_hours"`)
- Add optional nullable `DECIMAL(5,2)` column to `dbt/models/staging/stg_census_data.sql` — defaults to `NULL` (backward-compatible: NULL → assume 40 hrs/wk = 2080 annual)
- Document in `dbt/models/staging/schema.yml`

### 2. Hours Calculation Fix
In `int_employer_eligibility.sql` and `int_eligibility_computation_period.sql`, replace all hardcoded `2080.0` with:
```sql
COALESCE(scheduled_hours_per_week, 40.0) * 52.0
```
So the days-prorated formula becomes:
```sql
days * (COALESCE(scheduled_hours_per_week, 40.0) * 52.0 / 365.0)
```

### 3. New Hire Generation
- Add `part_time_new_hire_pct: float` config parameter to `config/workforce.py` (alongside `new_hire_termination_rate`)
- In `int_hiring_events.sql`: assign `scheduled_hours_per_week = 20` to `part_time_new_hire_pct` fraction of each cohort using existing deterministic hash pattern
- Carry `scheduled_hours_per_week` forward via `int_workforce_previous_year.sql` and `fct_workforce_snapshot`

### 4. Magic Button — `/analyze-part-time-pct`
New API endpoint (mirrors `/analyze-age-distribution`):
- Reads `workspaces/{id}/data/census.parquet`
- Computes employees where `(scheduled_hours_per_week * 52) < 1000` (would never satisfy annual hours requirement)
- Returns `{ part_time_pct, headcount, part_time_count }`
- Button disabled with tooltip when census lacks `scheduled_hours_per_week` column

## Acceptance Criteria

1. Upload census with `scheduled_hours_per_week = 20` for a subset → `annual_hours_worked ≈ 1040` for those employees
2. Full-time employees (NULL schedule) still get 2080 hours — no regression
3. `part_time_new_hire_pct = 0.2` causes ~20% of new hires to have 20 hrs/week
4. Magic button returns correct part-time % matching census
5. All existing tests pass

## Files to Modify

- `planalign_api/services/sql_security.py`
- `planalign_api/models/files.py`
- `planalign_api/routers/files.py`
- `dbt/models/staging/stg_census_data.sql` + `schema.yml`
- `dbt/models/intermediate/int_employer_eligibility.sql`
- `dbt/models/intermediate/int_eligibility_computation_period.sql`
- `dbt/models/intermediate/events/int_hiring_events.sql`
- `dbt/models/intermediate/int_workforce_previous_year.sql`
- `dbt/models/marts/fct_workforce_snapshot.sql`
- `planalign_orchestrator/config/workforce.py`
- `planalign_studio/` (NewHireSection.tsx, types.ts, API service)
