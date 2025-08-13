# Feature Request: Hours Worked Calculation (Business-Day Proration)

Status: proposed
Owner: Platform / Modeling
Priority: High (feeds eligibility, benefits, and compliance checks)

## Problem

We need a reproducible way to compute “hours worked” per employee per simulation year that:
- Prorates by hire and termination dates.
- Uses a normal business-day schedule (weekdays only; optional holiday calendar).
- Treats continuous active employees (employed for the entire plan year) as full-year hours.

This value will be consumed by downstream eligibility logic (e.g., employer match/core minimum hours) and analytics.

## Requirements

- Input dates: `employee_hire_date`, `employee_termination_date` (NULL if active throughout), simulation year bounds (`plan_year_start_date`, `plan_year_end_date`).
- Business-day schedule:
  - Default: Monday–Friday
  - Optional: holiday calendar (seeded table) for “US federal” or configurable
  - Hours per business day: default 8.0 (configurable)
- Proration logic:
  - If hire > year_end ⇒ 0 hours
  - If term < year_start ⇒ 0 hours
  - Else hours = business_days_between(max(hire, year_start), min(term_or_year_end, year_end)) * hours_per_day
  - Continuous active (no term; hire <= year_start) ⇒ full-year hours
- Output grain: one row per employee_id + simulation_year with `hours_worked` (DECIMAL), component columns for audit (business_days, hours_per_day_used, date_window_start, date_window_end).
- Deterministic and idempotent across re-runs.

## Proposed Design

1) New dbt model: `int_hours_worked_by_year`
- Tier: `intermediate`
- Inputs:
  - `fct_workforce_snapshot` (for simulation_year, employment_status, start/end window hints)
  - `int_baseline_workforce` (hire/term dates for baseline population)
  - Optional `stg_holidays` seed (date list) keyed by `holiday_calendar`
- Config vars:
  - `hours_per_business_day` (default: 8.0)
  - `holiday_calendar` (default: `us_federal`)
  - `plan_year_start_date` / `plan_year_end_date` (use existing vars from configs)
- Approach:
  - Derive `window_start = GREATEST(employee_hire_date, plan_year_start_date)`
  - Derive `window_end = LEAST(COALESCE(employee_termination_date, plan_year_end_date), plan_year_end_date)`
  - Generate a date series and count business days (exclude Sat/Sun and configured holidays)
  - `hours_worked = business_days * hours_per_business_day`

2) Macro support
- `is_business_day(date, holiday_calendar)` → boolean
- `count_business_days(start_date, end_date, holiday_calendar)` → integer
  - Use DuckDB’s `generate_series` for dates and exclusion joins to holiday seed

3) Contracts & Tests
- Schema tests:
  - not_null: employee_id, simulation_year, hours_worked
  - relationships to `fct_workforce_snapshot`
  - accepted_range: hours_worked ≥ 0
  - deterministic sample checks for known cases (e.g., full-year employee = 260 days * 8 hours = 2080 if default)

## SQL Sketch

```sql
WITH cfg AS (
  SELECT
    CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE) AS year_start,
    CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)   AS year_end,
    CAST({{ var('hours_per_business_day', 8.0) }} AS DOUBLE)           AS hours_per_day,
    '{{ var("enrollment_holiday_calendar", "us_federal") }}'        AS holiday_calendar
), base AS (
  SELECT
    s.employee_id,
    s.simulation_year,
    b.employee_hire_date,
    b.employee_termination_date,
    c.year_start,
    c.year_end,
    c.hours_per_day,
    c.holiday_calendar
  FROM {{ ref('fct_workforce_snapshot') }} s
  JOIN {{ ref('int_baseline_workforce') }} b USING (employee_id)
  CROSS JOIN cfg c
  WHERE s.simulation_year = {{ var('simulation_year') }}
), spans AS (
  SELECT
    employee_id,
    simulation_year,
    GREATEST(employee_hire_date, year_start) AS window_start,
    LEAST(COALESCE(employee_termination_date, year_end), year_end) AS window_end,
    hours_per_day,
    holiday_calendar
  FROM base
), days AS (
  SELECT
    employee_id,
    simulation_year,
    hours_per_day,
    COUNT(*) FILTER (
      WHERE EXTRACT(ISODOW FROM d) < 6  -- Mon-Fri
        AND NOT EXISTS (
          SELECT 1 FROM {{ ref('stg_holidays') }} h
          WHERE h.holiday_calendar = spans.holiday_calendar
            AND h.holiday_date = d
        )
    ) AS business_days
  FROM spans
  CROSS JOIN generate_series(window_start, window_end, INTERVAL 1 DAY) AS t(d)
  GROUP BY employee_id, simulation_year, hours_per_day
)
SELECT
  employee_id,
  simulation_year,
  CAST(business_days * hours_per_day AS DECIMAL(10,2)) AS hours_worked,
  business_days,
  hours_per_day
FROM days
```

## Configuration

- simulation_config.yaml (vars → dbt vars via orchestrator):
  - `hours_per_business_day: 8.0`
  - `enrollment_holiday_calendar: us_federal`

## Edge Cases
- Hire after year_end → 0 hours
- Term before year_start → 0 hours
- Hire == term within year → hours for those business days only
- Rehires (multiple spans) → future enhancement: support multiple spans; v1 assumes 1 hire/term per year

## Deliverables
- models/intermediate/int_hours_worked_by_year.sql
- seeds/stg_holidays.csv (calendar_name, holiday_date)
- macros/business_day_utils.sql (optional)
- schema.yml tests and docs

## Validation Plan
- Unit examples: 5 date windows including weekends/holidays
- Compare full-year sample: expect 260 days × 8 = 2,080 hours
- Cross-check with enrollment timing business-day logic if available
