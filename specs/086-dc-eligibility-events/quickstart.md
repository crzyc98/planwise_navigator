# Quickstart: DC Plan Eligibility Audit Trail (086)

**Branch**: `086-dc-eligibility-events`

---

## Prerequisites

```bash
source .venv/bin/activate
cd /workspace
```

## Verify Starting State (confirm the bug)

```bash
# Confirm no eligibility events are currently generated
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'eligibility'"
# Expected: 0

# Confirm the event type slot exists in macros
grep "evt_eligibility" dbt/macros/constants.sql
# Expected: macro definition + priority 3 in event_priority CASE
```

## Build New Model (after implementation)

```bash
cd dbt

# Build only the new model
dbt run --select int_eligibility_events --vars '{"simulation_year": 2025}' --threads 1

# Run schema tests for the new model
dbt test --select int_eligibility_events --threads 1

# Rebuild fct_yearly_events to include eligibility events
dbt run --select fct_yearly_events --vars '{"simulation_year": 2025}' --threads 1

# Run the prerequisite chain test
dbt test --select test_enrollment_requires_prior_eligibility --threads 1
```

## Verify After Implementation

```bash
# Should now return > 0
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'eligibility'"

# Verify exact date computation (0-day wait → effective_date = hire_date)
duckdb dbt/simulation.duckdb "
  SELECT e.employee_id, e.effective_date, h.effective_date AS hire_date
  FROM fct_yearly_events e
  JOIN fct_yearly_events h ON e.employee_id = h.employee_id AND e.simulation_year = h.simulation_year
  WHERE e.event_type = 'eligibility' AND h.event_type = 'hire'
  LIMIT 10
"

# Verify prerequisite chain — should return 0 rows
duckdb dbt/simulation.duckdb "
  SELECT COUNT(*) AS violations
  FROM fct_yearly_events enroll
  LEFT JOIN fct_yearly_events elig
    ON enroll.employee_id = elig.employee_id
    AND enroll.simulation_year = elig.simulation_year
    AND elig.event_type = 'eligibility'
    AND elig.effective_date <= enroll.effective_date
  WHERE enroll.event_type = 'enrollment'
    AND elig.employee_id IS NULL
"
# Expected: 0

# Verify no duplicates
duckdb dbt/simulation.duckdb "
  SELECT employee_id, COUNT(*) AS cnt
  FROM fct_yearly_events
  WHERE event_type = 'eligibility'
  GROUP BY employee_id
  HAVING COUNT(*) > 1
"
# Expected: 0 rows
```

## Run Full Simulation to Validate Multi-Year Behavior

```bash
cd /workspace
planalign simulate 2025-2027 --dry-run   # Preview
planalign simulate 2025-2027              # Full run

# Check multi-year deduplication
duckdb dbt/simulation.duckdb "
  SELECT employee_id, COUNT(DISTINCT simulation_year) AS years_with_event
  FROM fct_yearly_events
  WHERE event_type = 'eligibility'
  GROUP BY employee_id
  HAVING COUNT(DISTINCT simulation_year) > 1
"
# Expected: 0 rows (each employee appears in exactly one year)
```

## Run Python Tests

```bash
cd /workspace
pytest -m fast -k "eligib" -v          # Fast eligibility tests
pytest -m integration -k "eligib" -v   # Integration tests
```
