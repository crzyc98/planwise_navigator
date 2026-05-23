# Research: DC Plan Eligibility Audit Trail (086)

**Date**: 2026-05-20
**Branch**: `086-dc-eligibility-events`
**Status**: All NEEDS CLARIFICATION resolved

---

## Finding 1: Correct Source Model

**Decision**: Use `int_plan_eligibility_determination.sql` as the primary source for eligibility event generation — not the older `int_eligibility_determination.sql`.

**Rationale**: `int_plan_eligibility_determination.sql` is the authoritative plan participation eligibility model. It:
- Reads from `int_workforce_pre_enrollment` (covers both census employees and new hires)
- Combines BOTH gates: age requirement (`meets_age_requirement`) and waiting period/tenure (`meets_tenure_requirement`)
- Produces `is_plan_eligible` (boolean AND of both gates) — satisfying spec requirement Q5
- Provides `eligibility_effective_date` computed as `GREATEST(hire_date + waiting_period_days, age_threshold_date)`
- Is explicitly documented as "separate from employer contribution eligibility"

The older `int_eligibility_determination.sql` reads from `int_baseline_workforce` only and lacks the age gate. `int_plan_eligibility_determination.sql` is more complete and is the model already referenced by enrollment logic.

**Alternatives considered**: `int_eligibility_determination.sql` (older, baseline-only, missing age gate), `int_employer_eligibility.sql` (employer contribution eligibility — a different concept from plan participation eligibility).

---

## Finding 2: `eligibility_effective_date` Satisfies FR-005

**Decision**: Use `eligibility_effective_date` from `int_plan_eligibility_determination` as the event's `effective_date`.

**Rationale**: The field is computed as:
```sql
GREATEST(
  employee_hire_date + INTERVAL (waiting_period_days) DAY,
  MAKE_DATE(simulation_year - current_age + minimum_age, 1, 1)
)
```
This properly reflects "the latest date at which all eligibility gates are satisfied." When `minimum_age = 21` and `waiting_period_days = 0`, this reduces to the hire date (immediately eligible). When the waiting period is the binding constraint, this equals `hire_date + waiting_period_days` exactly as specified in FR-005.

The January 1 approximation for the age threshold date is acceptable — employee birth dates are not individually tracked; age is stored as current_age integer.

**Alternative considered**: Using `plan_eligibility_date` (pure `hire_date + waiting_period_days`) — rejected because it ignores the age gate, which could generate eligibility events for employees who are eligible by tenure but underage.

---

## Finding 3: Prior-Year De-duplication via Self-Reference

**Decision**: Use the incremental table's self-reference (`{{ this }}`) for prior-year de-duplication — the same pattern used by `int_enrollment_events.sql`.

**Rationale**: The constraint in CLAUDE.md prohibits reading from `fct_*` tables in `int_*` models. Since `int_eligibility_events` will be an incremental model, it can reference its own prior-year materialized data via `{{ this }}` without circular dependencies:
- Year 1 (`simulation_year == start_year`): Generate events for ALL `is_plan_eligible = true` employees (no prior data exists)
- Year 2+: Anti-join against `{{ this }}` to exclude employees who already received an eligibility event in any prior simulation year

**Alternative considered**: Creating a dedicated `int_eligibility_state_accumulator` — rejected as unnecessary complexity; the self-reference pattern is already proven in `int_enrollment_events.sql`.

---

## Finding 4: Infrastructure Already Expects Eligibility Events

**Decision**: No changes to `fct_workforce_snapshot.sql` or `int_workforce_snapshot_optimized.sql` are needed to support eligibility events.

**Rationale**: Both models already contain code anticipating `event_type = 'eligibility'` events:
- `fct_workforce_snapshot.sql` lines 467, 472: queries for eligibility events from `fct_yearly_events`
- `int_workforce_snapshot_optimized.sql` lines 104, 112, 145, 148, 157: eligibility event handling and `has_eligibility_event` flag

These downstream models were built expecting eligibility events that were never generated. This confirms the feature simply completes an existing design intent.

---

## Finding 5: Missing Python Constant

**Decision**: Add `EVENT_ELIGIBILITY = "eligibility"` to `config/constants.py`.

**Rationale**: All other event generators use a constant from `config/constants.py` (e.g., `EVENT_HIRE = "hire"`, `EVENT_ENROLLMENT = "enrollment"`). The `evt_eligibility()` dbt macro already returns `'eligibility'` but there is no corresponding Python constant. The new `EligibilityEventGenerator` must follow the same pattern.

---

## Finding 6: event_category_from_type Macro Gap

**Decision**: Update `event_category_from_type` macro in `dbt/macros/constants.sql` to map `'eligibility'` → `cat_benefits()`.

**Rationale**: The current macro has no case for `'eligibility'`, so eligibility events would be categorized as `'other'`. The `int_workforce_snapshot_optimized.sql` model filters on `event_category = 'eligibility'` at line 145 — this means the snapshot would fail to pick up eligibility events even after they're generated, because the category would be `'other'`.

The correct category is `'benefits'` (same as enrollment events) since eligibility is a prerequisite for DC plan benefits participation.

**Note**: `int_workforce_snapshot_optimized.sql` uses a literal string `'eligibility'` as a category value at line 145, not the `cat_benefits()` macro. If the intent is for eligibility to have its own category string `'eligibility'`, a new `cat_eligibility()` macro should be added. This is a design decision for implementation — defaulting to adding `cat_eligibility() = 'eligibility'` to match the existing snapshot queries.

---

## Finding 7: Execution Order Gap Available

**Decision**: Use `execution_order = 25` for `EligibilityEventGenerator`.

**Rationale**: Existing execution orders:
- 10: Termination
- 20: Hire
- **25: Eligibility (new)** — runs after hire events create new employees, before any compensation or enrollment events
- 30: Promotion
- 40: Merit
- 50: Enrollment

Priority 25 ensures hire events are fully materialized before eligibility is evaluated, and eligibility events are fully materialized before enrollment runs. This matches the event priority order defined in `dbt/macros/constants.sql` (hire=2, eligibility=3, enrollment=4).

---

## Finding 8: dbt Test Pattern

**Decision**: Add `dbt/tests/data_quality/test_enrollment_requires_prior_eligibility.sql` as a singular data test.

**Rationale**: Existing enrollment tests (`test_enrollment_architecture.sql`, `test_enrollment_continuity.sql`) follow the singular SQL test pattern that returns rows only when a violation is found. The new test queries for enrollment events that lack a preceding eligibility event for the same employee in the same year and returns any violating rows. A non-empty result set causes the test to fail.

---

## Summary: No NEEDS CLARIFICATION Remaining

| Question | Resolution |
|----------|-----------|
| Effective date grain | `eligibility_effective_date` from `int_plan_eligibility_determination` |
| Census employee scope | All employees via `int_plan_eligibility_determination` (reads `int_workforce_pre_enrollment`) |
| Eligible-not-enrolled | Events generated for all eligible employees regardless of enrollment |
| Payload richness | Fact only — no per-criterion breakdown |
| Combined eligibility gate | `is_plan_eligible` = `meets_age_requirement AND meets_tenure_requirement` |
| Prior-year dedup | Self-reference via `{{ this }}` in incremental model |
| Event category | New `cat_eligibility()` macro returning `'eligibility'` to match snapshot queries |
| Python constant | Add `EVENT_ELIGIBILITY = "eligibility"` |
| Execution order | 25 (between hire=20 and promotion=30) |
