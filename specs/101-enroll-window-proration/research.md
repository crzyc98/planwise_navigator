# Phase 0 Research: Same-Year Enroll → Opt-Out Window Proration

All Technical Context items are known from the codebase; research focused on the design unknowns behind FR-001/002/004 and the spec's documented assumption.

## R1 — Confirm the root cause

**Decision**: The $0 defect is in `int_employee_contributions.sql`'s `deferral_rates` CTE.

**Findings**: `deferral_rates` selects the **latest** rate per employee (`ROW_NUMBER() OVER (... ORDER BY simulation_year DESC)`, `rn = 1`) from `int_deferral_rate_state_accumulator`. For a same-year enroll→opt-out employee the accumulator's `current_year_opt_outs` CTE sets the rate to **0**. The contribution is then `prorated_annual_compensation * 0 = $0` (lines ~226, ~239). Year-end status is independently correct (feature 095). Confirms the spec exactly.

## R2 — Where does the active-window deferral rate come from? (the key unknown)

**Decision**: Parse it from the **enrollment event** in `fct_yearly_events` (`event_details` carries `"<X>% deferral"`).

**Rationale**: `int_deferral_rate_state_accumulator.current_year_new_enrollments` already does exactly this:
`CAST(REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) AS DECIMAL(6,4)) / 100.0` (fallback `0.06`). So the window rate is fully recoverable independent of the year-end 0. `int_employee_contributions` may read `fct_yearly_events` directly (sanctioned `int_*`→`fct_yearly_events` exception, and it already reads `int_hiring_events`/`int_termination_events`).

**Alternatives considered**:
- *Read the pre-opt-out value from the deferral accumulator.* Rejected: the accumulator only exposes the final (0) state; reconstructing the pre-opt-out rate there is more work than parsing the event.

## R3 — Window boundaries

**Decision**: `active_enrollment_days = `intersection of [enrollment_effective_date, opt_out_effective_date] with the employment window [year-start-or-hire, termination-or-year-end]`, clamped to ≥ 0.

**Findings**: Enrollment date = `evt_enrollment()` event `effective_date`; opt-out date = `evt_enrollment_change()` event with `event_details LIKE '%opt-out%'` `effective_date` (both already identified in the accumulator). Employment window already computed in `int_employee_contributions` (hire/termination proration). `GREATEST(0, ...)` guards degenerate/out-of-order windows (FR-007). Same-day enroll/opt-out → 0–1 day, never negative.

## R4 — How to credit without corrupting compensation reporting (overrides spec Assumption-A)

**Decision**: Keep `prorated_annual_compensation` = **employment-window** comp (unchanged). Apply the enrollment-window proration to a **separate contribution base** and the **effective deferral rate**:
- `effective_annual_deferral_rate` = window rate (R2) for enroll→opt-out employees (was 0).
- `total_contribution_base_compensation` = `prorated_annual_compensation × (active_enrollment_days / employed_days)` for enroll→opt-out employees; otherwise `= prorated_annual_compensation` (unchanged).
- `annual_contribution_amount` = `total_contribution_base_compensation × effective_annual_deferral_rate` (then IRS-capped, as today).

**Rationale**: `prorated_annual_compensation` has **15+ downstream consumers** (`fct_workforce_snapshot`, `fct_compensation_growth`, `int_employer_core_contributions`, many `dq_*`). The spec's Assumption-A (scale that column by the enrolled fraction) would understate **compensation** for opt-out employees everywhere — corrupting comp-growth and core-contribution metrics. The spec explicitly invited revisiting this in planning. Scaling only the contribution base confines the change to contributions/match and preserves comp semantics. Non-opt-out employees see `base == comp`, i.e., **no change** (FR-006).

**Alternatives considered**:
- *Assumption-A: scale `prorated_annual_compensation`.* Rejected — corrupts comp reporting (above).
- *Blended effective rate on full comp.* Rejected — it would break the employer-match tier logic, which keys off the actual deferral rate.

## R5 — Employer match follows automatically (FR-004)

**Decision**: Point the match model at the window-adjusted base.

**Findings**: `int_employee_match_calculations` consumes `ec.prorated_annual_compensation AS eligible_compensation` and `ec.effective_annual_deferral_rate AS deferral_rate`. Change `eligible_compensation` to source `ec.total_contribution_base_compensation`. For non-opt-out employees the two are equal (no change); for enroll→opt-out employees match now computes `window_rate × active-window comp` across all match modes — internally consistent with the credited contribution.

## R6 — The data-quality guard must be created (not just enforced)

**Decision**: Create `dbt/tests/assert_same_year_enroll_optout_window.sql`, register at `warn`, then flip to `error` once US1/US2 land.

**Findings**: Feature 095 **deferred** its Phase 6 (tasks T017–T020); the planned guard file was never created. The spec's wording ("move from advisory to enforcing") assumes it exists — it does not. Guard asserts, for same-year enroll→opt-out employees: year-end `participation_status = 'not_participating'` AND `current_deferral_rate = 0` AND active-window `annual_contribution_amount > 0`.

## R7 — Validation strategy

**Decision**: Validate in **isolated** DBs (never the shared `dbt/simulation.duckdb`), full multi-year, with a config that produces voluntary enrollments and same-year opt-outs (non-zero opt-out rates + voluntary enrollment). Identify an employee with both events in one year and assert non-zero windowed contribution + match and year-end not-participating. Detailed recipe in quickstart.md.

## Open items for implementation

- Confirm whether multiple enroll/opt-out cycles in one year occur in practice; the CTE should sum active sub-windows (FR edge case) but the common case is a single window. Implement single-window first, guard covers the invariant.
- Confirm the snapshot's year-end participation/deferral fields derive from the accumulator (not from `effective_annual_deferral_rate`), so setting the window rate here cannot regress year-end status (FR-005). Verify during implementation.
