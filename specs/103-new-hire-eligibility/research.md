# Phase 0 Research: New-Hire Eligibility Rate + Census Eligibility Override

All Technical Context unknowns were resolvable from the existing codebase and the two `/speckit.clarify` answers. No open `NEEDS CLARIFICATION` remain.

## Decision 1 — Single resolution model vs. inline expressions

**Decision**: Introduce one intermediate model `int_plan_eligibility_override` that resolves `is_plan_ineligible_override` per `(employee_id, simulation_year)` for both populations, and have the three enrollment/decision models plus `int_eligibility_events` join to it.

**Rationale**: The spec/issue mandate "resolve once, gate everywhere." Centralizing prevents drift between the auto, voluntary, and proactive paths and gives a single tested surface. Matches Constitution Principle II (single responsibility, no reverse deps).

**Alternatives considered**:
- *Inline the hash + census join in each of the 4 models* — rejected: duplicated logic across 4 files, high drift risk, harder to test.
- *A macro only (no model)* — viable for the hash, but the census-observed rate (census-matching) needs an aggregate over `stg_census_data`; a model materializes that cleanly. A thin macro `resolve_plan_ineligible_override` MAY still wrap the hash expression for readability and is listed as optional.

## Decision 2 — Source the static census flag directly from `stg_census_data`

**Decision**: For census employees (`EMP_*`), read `eligibility_override` straight from `stg_census_data`, **not** through `int_employee_compensation_by_year`.

**Rationale**: `int_employee_compensation_by_year`'s Year-2+ path is rebuilt from the prior-year **snapshot**, which does not carry arbitrary census attributes; routing through it would lose the flag after Year 1. The #316 `auto_escalation_opt_out` work hit and solved exactly this by reading the static attribute from staging. This satisfies FR-010 (consistent multi-year classification).

**Alternatives considered**: Plumb through `int_employee_compensation_by_year` — rejected (multi-year-incorrect, per #316 precedent).

## Decision 3 — Deterministic new-hire selection

**Decision**: Mark a new hire ineligible when
`ABS(MOD(HASH(employee_id || '_eligibility_' || simulation_year), 1000000)) / 1000000.0 < effective_ineligible_rate`.

**Rationale**: Hash-based selection is stable across re-runs with the same seed (Principle I reproducibility, FR-002, SC-002 reproducibility). The `'_eligibility_'` salt avoids collision with other hash-based decisions keyed on `employee_id`. Per-year salt is intentional: the new-hire cohort differs each year, so each cohort is independently sampled to the target share.

**Alternatives considered**: Random draw seeded globally — rejected (harder to reason about per-cohort share and reproducibility across partial re-runs). Top-N by hash — rejected (needs a cohort-wide window; the threshold form is simpler and converges to the target share for realistic cohort sizes, matching the ±1pp tolerance in SC-002).

## Decision 4 — Census-matching denominator (from clarify)

**Decision**: When `new_hire_eligibility_match_census = true` and the census carries `eligibility_override`, the effective new-hire ineligible rate = `COUNT(eligibility_override = FALSE) / COUNT(*)` over **all** `stg_census_data` rows (blank/NULL counted as eligible). Computed in SQL inside `int_plan_eligibility_override` (depends on a table, not a scalar config value). Falls back to `new_hire_ineligible_pct` when the column is absent/all-NULL (yielding 0% observed → falls back to dial).

**Rationale**: Clarify session answer. Total-headcount denominator is the population-representative rate the sponsor sees. Computing in SQL keeps it census-data-driven and reproducible.

**Alternatives considered**: Denominator = only explicitly-classified employees — rejected by the user during clarification.

## Decision 5 — Invalid census value handling (from clarify)

**Decision**: An unrecognized value in the census eligibility column is **non-fatal**: surface a warning, treat the value as unspecified (eligible by default), proceed. Implement via `TRY_CAST(... AS BOOLEAN)` + `COALESCE(..., NULL→eligible)` semantics in `stg_census_data` (invalid → NULL → eligible), plus an import-layer warning consistent with existing census field warnings.

**Rationale**: Clarify session answer; matches the project's lenient census-import posture (`#350` soft-validation, `055-census-field-warnings`). `TRY_CAST` naturally coerces garbage to NULL.

**Alternatives considered**: Reject the row / reject the whole file — rejected by the user during clarification.

## Decision 6 — Suppression cascades; no contribution/match changes

**Decision**: Gate only enrollment eligibility and the `DC_PLAN_ELIGIBILITY` event. Do **not** touch contribution or match models.

**Rationale**: An employee who never enrolls produces no deferral, hence no contribution and no match — the suppression cascades for free. The issue explicitly notes "(No contribution/match changes needed — they cascade from 'never enrolled')." Minimizes blast radius and regression surface (FR-013/SC-001).

## Decision 7 — Backward compatibility / regression safety

**Decision**: All new vars default to the no-op value (`new_hire_ineligible_pct=0.0`, `new_hire_eligibility_match_census=false`, census column absent → NULL → eligible). The `int_plan_eligibility_override` model yields `is_plan_ineligible_override = FALSE` for everyone under defaults, and `NOT FALSE` leaves the existing gate unchanged.

**Rationale**: FR-013 / SC-001 require byte-for-byte identical default output. A double-run regression test on an isolated DB validates this.

## Decision 8 — Optional Python event-layer parity

**Decision**: Extend `EligibilityPayload.reason` enum in `config/events/dc_plan.py` with `"ineligible_override"` and an optional `source`, for parity with the dbt `event_details`. Optional / non-blocking.

**Rationale**: Keeps the Python event model aligned with what dbt annotates; low cost, improves transparency (Principle IV). Not required for the dbt-only pipeline path to function.
