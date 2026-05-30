# Implementation Plan: DC Plan Eligibility Audit Trail

**Branch**: `086-dc-eligibility-events` | **Date**: 2026-05-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/086-dc-eligibility-events/spec.md`

---

## Summary

Close the structural gap in the event sourcing audit trail by implementing the missing `DC_PLAN_ELIGIBILITY` event pipeline. The event type, macro, and priority slot all exist in the codebase; the three missing pieces are a dbt SQL model (`int_eligibility_events.sql`), a Python generator wrapper (`eligibility.py`), and a UNION entry in `fct_yearly_events.sql`. A data quality test enforces the prerequisite chain (eligibility → enrollment) on every simulation run.

---

## Technical Context

**Language/Version**: Python 3.11, SQL (dbt-core 1.8.8)
**Primary Dependencies**: dbt-duckdb 1.8.1, DuckDB 1.0.0, Pydantic v2
**Storage**: `dbt/simulation.duckdb` (incremental model, self-referencing for prior-year deduplication)
**Testing**: pytest (fast + integration marks), dbt data tests (singular SQL + schema)
**Target Platform**: Linux server (on-premises)
**Project Type**: Data pipeline / event sourcing
**Performance Goals**: No new NFRs — eligibility model follows same incremental pattern as existing event models
**Constraints**: Single-threaded dbt (`--threads 1`); no `fct_*` reads in `int_*` models; cognitive complexity ≤ 15
**Scale/Scope**: One new dbt model, one new Python generator, two constant additions, one UNION entry, one dbt test

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | New incremental model writes immutable eligibility events to `fct_yearly_events` |
| II. Modular Architecture | ✅ PASS | One focused model (`int_eligibility_events.sql` ~60 lines), one generator (`eligibility.py` ~70 lines) |
| III. Test-First Development | ✅ PASS | dbt schema tests + singular prerequisite chain test + pytest unit test planned |
| IV. Enterprise Transparency | ✅ PASS | Closes existing audit gap; `fct_workforce_snapshot` already queries eligibility events |
| V. Type-Safe Configuration | ✅ PASS | Generator uses `EVENT_ELIGIBILITY` constant; model uses `{{ ref() }}` and `{{ var() }}` |
| VI. Performance & Scalability | ✅ PASS | Incremental `delete+insert`; filtered by `simulation_year`; `int_workforce_pre_enrollment` is already materialized |

No violations. Complexity Tracking table not required.

---

## Project Structure

### Documentation (this feature)

```text
specs/086-dc-eligibility-events/
├── plan.md              ← this file
├── research.md          ← Phase 0 findings
├── data-model.md        ← entity definitions and column schema
├── quickstart.md        ← dev verification commands
├── contracts/
│   └── int_eligibility_events.md   ← column contract + prerequisite chain
└── tasks.md             ← Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
# New files
dbt/models/intermediate/events/int_eligibility_events.sql
planalign_orchestrator/generators/eligibility.py
dbt/tests/data_quality/test_enrollment_requires_prior_eligibility.sql

# Modified files
config/constants.py                                  ← add EVENT_ELIGIBILITY constant
dbt/macros/constants.sql                             ← add cat_eligibility() + update event_category_from_type
dbt/models/marts/fct_yearly_events.sql               ← add UNION ALL for int_eligibility_events
dbt/models/intermediate/events/schema.yml            ← add int_eligibility_events entry
planalign_orchestrator/generators/__init__.py        ← register EligibilityEventGenerator
```

---

## Implementation Design

### 1. `config/constants.py` — Add constant

```python
EVENT_ELIGIBILITY = "eligibility"   # Add after EVENT_ENROLLMENT on line 72
```

### 2. `dbt/macros/constants.sql` — Two additions

**New macro** (after `evt_eligibility()` definition):
```sql
{% macro cat_eligibility() %}'eligibility'{% endmacro %}
```

**Update `event_category_from_type` CASE** — add before the `ELSE 'other'`:
```sql
WHEN {{ col }} = {{ evt_eligibility() }} THEN {{ cat_eligibility() }}
```

### 3. `dbt/models/intermediate/events/int_eligibility_events.sql` — New model

Core logic outline (full implementation in tasks):

```sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['employee_id', 'simulation_year'],
  pre_hook=["{% if is_incremental() %}DELETE FROM {{ this }}
    WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"],
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}

WITH newly_eligible AS (
  SELECT ped.*
  FROM {{ ref('int_plan_eligibility_determination') }} ped
  WHERE ped.simulation_year = {{ simulation_year }}
    AND ped.is_plan_eligible = true
    {% if simulation_year != start_year %}
    -- Year 2+: exclude employees who already received an eligibility event
    AND ped.employee_id NOT IN (
      SELECT DISTINCT employee_id
      FROM {{ this }}
      WHERE simulation_year < {{ simulation_year }}
    )
    {% endif %}
)

SELECT
  employee_id,
  employee_ssn,
  {{ evt_eligibility() }} AS event_type,
  {{ simulation_year }} AS simulation_year,
  eligibility_effective_date AS effective_date,
  'DC plan eligibility achieved (waiting_period=' || waiting_period_days ||
    ' days, min_age=' || minimum_age || ')' AS event_details,
  NULL::DECIMAL(10,2) AS compensation_amount,
  NULL::DECIMAL(10,2) AS previous_compensation,
  NULL::DECIMAL(5,4) AS employee_deferral_rate,
  NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
  current_age AS employee_age,
  current_tenure AS employee_tenure,
  level_id,
  age_band,
  tenure_band,
  1.0 AS event_probability,
  {{ cat_eligibility() }} AS event_category
FROM newly_eligible
```

**Critical constraint**: `eligibility_effective_date` in `int_plan_eligibility_determination` is NULL when `is_plan_eligible = false`. The WHERE clause `is_plan_eligible = true` ensures no NULLs in `effective_date`.

### 4. `fct_yearly_events.sql` — Add UNION ALL

Insert after the `int_hiring_events` block and before `int_termination_events`, maintaining event priority order (hire=2, eligibility=3):

```sql
UNION ALL

SELECT
  '{{ sid }}' AS scenario_id,
  '{{ pid }}' AS plan_design_id,
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  event_details,
  compensation_amount,
  previous_compensation,
  employee_deferral_rate,
  prev_employee_deferral_rate,
  employee_age,
  employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  event_category
FROM {{ ref('int_eligibility_events') }}
WHERE simulation_year = {{ simulation_year }}
```

### 5. `planalign_orchestrator/generators/eligibility.py` — New generator

```python
from config.constants import EVENT_ELIGIBILITY
from planalign_orchestrator.generators.base import EventContext, EventGenerator, ValidationResult
from planalign_orchestrator.generators.registry import EventRegistry

@EventRegistry.register(EVENT_ELIGIBILITY)
class EligibilityEventGenerator(EventGenerator):
    event_type = EVENT_ELIGIBILITY
    execution_order = 25   # After hire (20), before promotion (30) and enrollment (50)
    requires_hazard = False
    supports_sql = True
    dbt_models = ["int_plan_eligibility_determination", "int_eligibility_events"]

    def generate_events(self, context):
        return []   # Delegated to dbt

    def validate_event(self, event):
        errors = []
        if event.payload.event_type != EVENT_ELIGIBILITY:
            errors.append(f"Expected '{EVENT_ELIGIBILITY}', got '{event.payload.event_type}'")
        if not hasattr(event.payload, 'eligibility_date') or event.payload.eligibility_date is None:
            errors.append("eligibility_date is required")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

### 6. `planalign_orchestrator/generators/__init__.py` — Register generator

```python
from planalign_orchestrator.generators.eligibility import EligibilityEventGenerator
```
Add to `__all__` list and import block alongside `EnrollmentEventGenerator`.

### 7. `dbt/tests/data_quality/test_enrollment_requires_prior_eligibility.sql` — Prerequisite chain test

```sql
-- Returns rows when an enrolled employee has no prior eligibility event in the same year
-- A non-empty result fails the test
SELECT
  enroll.employee_id,
  enroll.simulation_year,
  enroll.effective_date AS enrollment_date
FROM {{ ref('fct_yearly_events') }} enroll
LEFT JOIN {{ ref('fct_yearly_events') }} elig
  ON enroll.employee_id = elig.employee_id
  AND enroll.simulation_year = elig.simulation_year
  AND elig.event_type = {{ evt_eligibility() }}
  AND elig.effective_date <= enroll.effective_date
WHERE enroll.event_type = {{ evt_enrollment() }}
  AND elig.employee_id IS NULL
```

### 8. `dbt/models/intermediate/events/schema.yml` — Add entry

Add `int_eligibility_events` with:
- `unique_combination_of_columns`: `[employee_id, simulation_year]`
- `not_null` on `employee_id`, `event_type`, `effective_date`, `simulation_year`
- `accepted_values` on `event_type: ['eligibility']`
- `accepted_values` on `event_category: ['eligibility']`

---

## Execution Order / Build Sequence

1. `config/constants.py` — add constant (no dependencies)
2. `dbt/macros/constants.sql` — add macro + update CASE (no dependencies)
3. `int_eligibility_events.sql` — new model (depends on `int_plan_eligibility_determination`)
4. `events/schema.yml` — tests for new model
5. `fct_yearly_events.sql` — add UNION (depends on new model existing)
6. `generators/eligibility.py` — new generator (depends on constant)
7. `generators/__init__.py` — register generator
8. `test_enrollment_requires_prior_eligibility.sql` — test (depends on `fct_yearly_events` having eligibility events)

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source model | `int_plan_eligibility_determination` | Covers age + waiting period; reads `int_workforce_pre_enrollment` (all employees) |
| Deduplication | Self-reference `{{ this }}` in incremental model | No new accumulator needed; same pattern as `int_enrollment_events` |
| Effective date | `eligibility_effective_date` (GREATEST of both gates) | Properly handles the case where age is the binding constraint, not waiting period |
| Event category | New `cat_eligibility() = 'eligibility'` | Matches existing `int_workforce_snapshot_optimized.sql` literal string filter |
| UNION position | After hire, before terminations | Matches event priority order (hire=2, eligibility=3, enrollment=4) |
| Python execution_order | 25 | Gap between hire (20) and promotion (30); eligibility must precede enrollment (50) |
| Employer eligibility gate | Not separately joined | `int_plan_eligibility_determination.is_plan_eligible` combines age + tenure; `int_employer_eligibility` is contribution-specific |

---

## Post-Design Constitution Re-Check

All six principles still pass after design phase. No new architectural complexity introduced. The implementation extends the existing event sourcing pattern to an event type that was already stubbed out in macros, priorities, and downstream snapshot queries.
