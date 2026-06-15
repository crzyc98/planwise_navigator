# Quickstart: New Hires Voluntarily Enroll in Their Hire Year

**Feature**: 096-newhire-voluntary-enroll

## Reproduce the defect (baseline)

```bash
# From repo root — query any multi-year scenario database
DB="workspaces/049771e9-0a4a-44a3-84ce-d9aabd6dbdcf/scenarios/d3ab5ad3-224c-4a30-a1a9-6a123ae09d4d/simulation.duckdb"

# New hires never enroll in their hire year (first enroll is always year+1 or later):
duckdb "$DB" "SELECT SUBSTR(employee_id,1,7) cohort, MIN(simulation_year) first_enroll_yr
              FROM fct_yearly_events
              WHERE event_type='enrollment' AND employee_id LIKE 'NH_%'
              GROUP BY 1 ORDER BY 1"

# Hire-year new hires are absent from the compensation model that feeds the decision engine:
duckdb "$DB" "SELECT simulation_year, COUNT(*) FILTER (WHERE employee_id LIKE 'NH_%') new_hires
              FROM int_employee_compensation_by_year GROUP BY 1 ORDER BY 1"
# Expect: 0 new hires in the start year.
```

## Validate the fix

```bash
cd dbt

# Rebuild enrollment chain for the start year
dbt run --select int_voluntary_enrollment_decision int_enrollment_events \
  int_enrollment_state_accumulator fct_yearly_events fct_workforce_snapshot \
  --vars "simulation_year: 2025" --threads 1

# Run the new regression test + feature-095 reconciliation
dbt test --select tag:data_quality --threads 1
```

### Expected results after fix

1. A non-zero share (≈ configured voluntary rate, < 100%) of eligible new hires have a
   `voluntary_enrollment` event **dated within their hire year**.
2. Those new hires show `participating` with their deferral rate and employer match > 0 in the
   **hire-year** snapshot.
3. Exactly one enrollment event exists per new-hire enrollment decision (no Y+1 duplicate).
4. New regression test (`test_new_hire_voluntary_enrollment_hire_year`) returns 0 rows (passes).

```bash
# Spot-check: hire-year enrollees now appear participating in hire year
duckdb dbt/simulation.duckdb \
  "SELECT s.employee_id, s.simulation_year, s.participation_status, s.current_deferral_rate, s.employer_match_amount
   FROM fct_workforce_snapshot s
   JOIN fct_yearly_events e
     ON e.employee_id = s.employee_id
    AND e.simulation_year = s.simulation_year
    AND e.event_type = 'enrollment'
   WHERE s.employee_id LIKE 'NH_%'
     AND EXTRACT(YEAR FROM s.employee_hire_date) = s.simulation_year
   ORDER BY s.employee_id, s.simulation_year"
```

## Full end-to-end check

```bash
planalign simulate 2025-2027 --verbose
pytest -m "fast and events"
```
</content>
