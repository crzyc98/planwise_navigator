# Contract: Eligibility suppression & event behavior

How the override changes what lands in `fct_yearly_events`, and the invariants tests assert.

## Suppression behavior

For any employee with `is_plan_ineligible_override = TRUE` in year Y:

| Event class | Behavior |
|-------------|----------|
| `DC_PLAN_ELIGIBILITY` | **Not emitted** for the suppressed period. `int_eligibility_events` annotates the suppression with `reason='ineligible_override'` and a `source` in `event_details` (FR-009). |
| Auto-enrollment (`int_enrollment_events`) | Not generated — gate `is_eligible AND NOT is_plan_ineligible_override`. |
| Voluntary enrollment (`int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`) | Not generated — same gate. |
| Contributions / Employer match | None — cascade from "never enrolled" (no model changes). |

## Invariants (dbt data tests)

- **`assert_ineligible_no_enrollment`**: zero enrollment/contribution/match events in `fct_yearly_events` for any employee resolved `is_plan_ineligible_override = TRUE`.
- **Default no-op**: with `new_hire_ineligible_pct=0.0`, `new_hire_eligibility_match_census=false`, and no census column, `int_plan_eligibility_override.is_plan_ineligible_override` is `FALSE` for all rows (supports SC-001 byte-for-byte regression).
- **New-hire share** (SC-002): with `new_hire_ineligible_pct=0.10`, the share of each year's `NH_*` cohort with `is_plan_ineligible_override = TRUE` is within ±1pp of 10% on a representative cohort, and reproducible across identical re-runs.
- **Census ineligible** (SC-003): every `EMP_*` with census `eligibility_override = FALSE` has zero enrollment/contribution/match events across all years.
- **Census matching** (SC-004): with `new_hire_eligibility_match_census=true`, the realized new-hire ineligible share tracks `COUNT(eligibility_override=FALSE)/COUNT(*)` over `stg_census_data`; falls back to the dial when the column is absent.

## Optional Python parity

`EligibilityPayload.reason` gains `"ineligible_override"` + optional `source`, matching the dbt `event_details` annotation (non-blocking).
