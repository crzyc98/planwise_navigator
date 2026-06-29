# Phase 1 Data Model: New-Hire Eligibility Rate + Census Eligibility Override

No new tables. The feature adds one nullable census column, one new intermediate model, and one boolean attribute that threads through existing models. Below are the data shapes, fields, validation rules, and lifecycle.

## Configuration entities (Pydantic — `planalign_orchestrator/config/workforce.py`)

### `EligibilitySettings` (extended)

| Field | Type | Default | Validation | dbt var |
|-------|------|---------|-----------|---------|
| `waiting_period_days` | `Optional[int]` | `None` | (existing) | `eligibility_waiting_days` |
| `new_hire_ineligible_pct` | `float` | `0.0` | `ge=0.0, le=1.0` (FR-001/FR-011) | `new_hire_ineligible_pct` |
| `new_hire_eligibility_match_census` | `bool` | `False` | — | `new_hire_eligibility_match_census` |

**Validation rules**:
- Out-of-range `new_hire_ineligible_pct` → Pydantic `ValidationError` at config load with an actionable message (FR-011).
- Both fields optional in YAML; absence → defaults → no-op (FR-013).

## Staging entity (`stg_census_data`)

### New optional column: `eligibility_override`

| Attribute | Value |
|-----------|-------|
| Type | `BOOLEAN` (nullable) |
| Semantics | `TRUE` = eligible, `FALSE` = ineligible, `NULL` = unspecified (default eligible) |
| Source | Optional column in census parquet; absent → schema-scaffold supplies `NULL::BOOLEAN` |
| Coercion | `TRY_CAST(... AS BOOLEAN)`; unrecognized value → `NULL` → eligible (FR-012, Decision 5) |
| Pattern precedent | `auto_escalation_opt_out` (#316) — same WHERE-false scaffold + COALESCE block |

**Validation rules** (`schema.yml`):
- `accepted_values`: `[true, false]` on the post-coalesce value (NULL excluded), documenting the recognized states.
- A data test / import warning surfaces rows whose raw value failed to cast (non-fatal).

## Derived entity (new model: `int_plan_eligibility_override`)

Resolves the override **once** per employee per year. One row per `(employee_id, simulation_year)`.

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | VARCHAR | Census (`EMP_*`) or new hire (`NH_*`) |
| `simulation_year` | INTEGER | Year being resolved |
| `is_plan_ineligible_override` | BOOLEAN | `TRUE` → suppress participation this year |
| `override_source` | VARCHAR | `'census'` \| `'new_hire_dial'` \| `'census_match'` (audit) |

**Resolution logic**:
- **Census employees (`EMP_*`)**: `is_plan_ineligible_override = (eligibility_override = FALSE)` read directly from `stg_census_data` (Decision 2). `NULL`/`TRUE` → not overridden-ineligible.
- **New hires (`NH_*`)**: `is_plan_ineligible_override = HASH(employee_id || '_eligibility_' || simulation_year) ... < effective_rate` (Decision 3).
- **Effective rate**:
  - `new_hire_eligibility_match_census = false` → `effective_rate = new_hire_ineligible_pct` (the dial).
  - `new_hire_eligibility_match_census = true` and census carries the column → `effective_rate = COUNT(eligibility_override = FALSE) / COUNT(*)` over all `stg_census_data` rows (Decision 4); else fall back to the dial.
- **Precedence (FR-006)**: census employees governed by their explicit value; the dial governs only new hires — populations are disjoint by ID prefix, so no conflict.

**Build order**: `stg_census_data` → `int_plan_eligibility_override` → (`int_enrollment_events`, `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, `int_eligibility_events`).

## Gate integration (existing models, behavior change only)

| Model | Change |
|-------|--------|
| `int_enrollment_events` | Auto-enrollment eligible flag becomes `is_eligible AND NOT is_plan_ineligible_override` |
| `int_voluntary_enrollment_decision` | Same gate on the eligible-employees CTE |
| `int_proactive_voluntary_enrollment` | Same gate |
| `int_eligibility_events` | Suppress `DC_PLAN_ELIGIBILITY` emission when `is_plan_ineligible_override`; annotate `reason='ineligible_override'` + `source` in `event_details` (FR-009) |

No changes to contribution/match models — suppression cascades from "never enrolled" (Decision 6).

## Event-layer entity (optional parity — `config/events/dc_plan.py`)

`EligibilityPayload.reason`: add literal `"ineligible_override"`; add optional `source: Optional[str]`. Mirrors the dbt `event_details` annotation. Non-blocking (Decision 8).

## Lifecycle / state notes

- `is_plan_ineligible_override` is **static across years** for census employees (same census value every year, read from staging) and **per-cohort deterministic** for new hires (hash includes the hire/sim year). An ineligible employee is suppressed for the whole horizon they remain ineligible (Assumptions). No ineligible→eligible transition is modeled beyond what normal eligibility rules already produce.
- Contributions/match already recorded in a prior eligible year are not unwound (Out of Scope).
