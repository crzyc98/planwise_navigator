# Feature Request: Employer Contribution Eligibility (Hours + Active EOY)

Status: proposed
Owner: Benefits / Modeling
Priority: High (eligibility rules for match/core)

## Problem

We need to enforce employer match and/or employer core contribution eligibility based on:
- Minimum hours worked threshold within the plan year (e.g., 1,000 hours), and/or
- A flag requiring the employee to be active at year end (EOY).

These rules must be configurable per scenario and applied consistently wherever employer contributions are generated.

## Requirements

- Configurable policy per scenario/plan:
  - `min_hours_worked` (integer; default: null/no threshold)
  - `require_active_eoy` (boolean; default: false)
- Hours basis: consume `int_hours_worked_by_year` (see companion issue) for reproducible hours totals.
- Eligibility is evaluated per employee + simulation_year.
- Downstream gating:
  - Employer match events (and/or match accrual) must be suppressed if not eligible
  - Employer core contributions must be suppressed if not eligible
- Auditable and testable: expose an eligibility model with reasons/flags.

## Proposed Design

1) New dbt model: `int_employer_contribution_eligibility`
- Inputs:
  - `int_hours_worked_by_year` (hours_worked)
  - `fct_workforce_snapshot` (employment_status at EOY)
  - Policy vars from config/simulation_config.yaml
- Columns:
  - employee_id, simulation_year
  - meets_hours_threshold (bool)
  - is_active_eoy (bool)
  - eligible_for_match (bool)
  - eligible_for_core (bool)
  - rule_params (min_hours_worked, require_active_eoy) for audit

2) Policy mapping (vars → dbt):
- simulation_config.yaml:
```yaml
employer_eligibility:
  min_hours_worked: 1000   # null to disable
  require_active_eoy: true # false to disable
```
- Orchestrator maps to dbt vars, e.g., `elig_min_hours_worked`, `elig_require_active_eoy`.

3) Integration points
- Match logic models (e.g., `int_employee_match_calculations` or `fct_employer_match_events`) join to `int_employer_contribution_eligibility` and filter to eligible employees.
- Core contribution logic likewise gates on eligibility.

## SQL Sketch

```sql
WITH cfg AS (
  SELECT
    {{ var('elig_min_hours_worked', 'null') }}::INTEGER AS min_hours,
    {{ var('elig_require_active_eoy', false) }}::BOOLEAN AS require_active
), hours AS (
  SELECT employee_id, simulation_year, hours_worked
  FROM {{ ref('int_hours_worked_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
), eoy AS (
  SELECT employee_id, simulation_year,
         MAX(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) AS active_eoy
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  GROUP BY employee_id, simulation_year
)
SELECT
  h.employee_id,
  h.simulation_year,
  (CASE WHEN cfg.min_hours IS NULL THEN TRUE ELSE h.hours_worked >= cfg.min_hours END) AS meets_hours_threshold,
  (e.active_eoy = 1) AS is_active_eoy,
  -- Policy: BOTH conditions if both configured; each optional
  ((CASE WHEN cfg.min_hours IS NULL THEN TRUE ELSE h.hours_worked >= cfg.min_hours END)
    AND (CASE WHEN cfg.require_active THEN (e.active_eoy = 1) ELSE TRUE END)) AS eligible_for_match,
  ((CASE WHEN cfg.min_hours IS NULL THEN TRUE ELSE h.hours_worked >= cfg.min_hours END)
    AND (CASE WHEN cfg.require_active THEN (e.active_eoy = 1) ELSE TRUE END)) AS eligible_for_core,
  cfg.min_hours AS rule_min_hours,
  cfg.require_active AS rule_require_active_eoy
FROM hours h
CROSS JOIN cfg
LEFT JOIN eoy e USING (employee_id, simulation_year)
```

## Tests & Validation
- Schema tests: not_null (employee_id, simulation_year), accepted_values on booleans, relationships to inputs
- Data tests:
  - Active all year + min_hours unset ⇒ eligible
  - Partial-year hire below threshold ⇒ ineligible when `min_hours_worked` set
  - Terminated before year-end ⇒ eligibility depends on `require_active_eoy`

## Rollout Plan
- Add config block to simulation_config.yaml and map to dbt vars in the orchestrator
- Implement `int_hours_worked_by_year` (dependency)
- Implement `int_employer_contribution_eligibility`
- Join eligibility into match/core models and gate outputs
- Add docs and schema tests; run targeted `dbt test` for eligibility models

## Open Questions
- Do we require distinct thresholds per plan design (e.g., core vs match)? If yes, add `min_hours_worked_match` and `min_hours_worked_core`.
- Holiday calendar selection per scenario vs global? Default to global with override.
- Rehires with multiple spans in one year: v1 treats one continuous span; v2 could sum business-day spans.
