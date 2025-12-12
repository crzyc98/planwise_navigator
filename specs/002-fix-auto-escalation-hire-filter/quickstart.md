# Quickstart: Testing Auto-Escalation Hire Date Filter Fix

## Prerequisites

```bash
# Activate virtual environment
source .venv/bin/activate

# Verify installation
planalign health
```

## Test Scenarios

### Scenario 1: All Employees Eligible (Baseline)

```bash
# Run simulation with hire_date_cutoff: "1900-01-01" (all employees)
PYTHONPATH=. python -m planalign_orchestrator batch --scenarios ae_all_eligible --verbose
```

Expected: All enrolled employees should receive escalation events.

### Scenario 2: New Hires Only

```bash
# Run simulation with hire_date_cutoff: "2026-01-01" (new hires only)
PYTHONPATH=. python -m planalign_orchestrator batch --scenarios ae_new_hires --verbose
```

Expected: Only employees hired on or after 2026-01-01 should receive escalation events.

### Scenario Comparison

```bash
# Run both scenarios
PYTHONPATH=. python -m planalign_orchestrator batch --scenarios ae_all_eligible ae_new_hires --verbose

# Compare escalation event counts
duckdb outputs/batch_*/ae_all_eligible/ae_all_eligible.duckdb "
SELECT COUNT(*) as escalation_count
FROM fct_yearly_events
WHERE event_type = 'deferral_escalation'
"

duckdb outputs/batch_*/ae_new_hires/ae_new_hires.duckdb "
SELECT COUNT(*) as escalation_count
FROM fct_yearly_events
WHERE event_type = 'deferral_escalation'
"
```

Expected: `ae_new_hires` should have significantly fewer escalation events than `ae_all_eligible`.

## Validation Queries

### Check Boundary Condition (Critical)

```sql
-- Verify employees hired ON cutoff date are escalated
SELECT
    e.employee_id,
    w.employee_hire_date,
    e.event_type,
    e.effective_date
FROM fct_yearly_events e
JOIN int_baseline_workforce w ON e.employee_id = w.employee_id
WHERE e.event_type = 'deferral_escalation'
  AND w.employee_hire_date = '2026-01-01'
LIMIT 10;
```

After fix: Should return rows for employees hired on 2026-01-01.

### Check Excluded Employees (Negative Test)

```sql
-- Verify employees hired BEFORE cutoff are NOT escalated
SELECT
    e.employee_id,
    w.employee_hire_date,
    e.event_type
FROM fct_yearly_events e
JOIN int_baseline_workforce w ON e.employee_id = w.employee_id
WHERE e.event_type = 'deferral_escalation'
  AND w.employee_hire_date < '2026-01-01'
LIMIT 10;
```

Expected: Should return 0 rows when using `ae_new_hires` scenario.

## Running Unit Tests

```bash
# Run escalation-related tests
pytest tests/ -k "escalation" -v

# Run fast test suite
pytest -m fast
```

## Verifying the Fix

Before fix:
- Employees hired on 2026-01-01 are NOT escalated (bug)

After fix:
- Employees hired on 2026-01-01 ARE escalated (correct)
- Employees hired before 2026-01-01 are NOT escalated (unchanged)
- Employees hired after 2026-01-01 ARE escalated (unchanged)
