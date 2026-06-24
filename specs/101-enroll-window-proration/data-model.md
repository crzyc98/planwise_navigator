# Phase 1 Data Model: Same-Year Enroll → Opt-Out Window Proration

No new tables or event types. This feature adds derived columns to `int_employee_contributions` and changes one source reference in `int_employee_match_calculations`.

## Derived entity: Active-Enrollment Window (per employee-year)

Computed inside `int_employee_contributions` from `fct_yearly_events` for the current `simulation_year`.

| Field | Source / Rule |
|-------|---------------|
| `enrollment_effective_date` | `effective_date` of the `evt_enrollment()` event this year |
| `opt_out_effective_date` | `effective_date` of the `evt_enrollment_change()` event with `event_details LIKE '%opt-out%'` this year |
| `enrollment_window_deferral_rate` | `REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) / 100.0` from the enrollment event (fallback `0.06`, matching the deferral accumulator) |
| `is_same_year_enroll_optout` | both an enrollment and an opt-out event exist this year **and** year-end enrollment status is not-participating |
| `active_enrollment_days` | `GREATEST(0, DATEDIFF('day', window_start, window_end) + 1)` where `window_start/end` = the enrollment/opt-out window **intersected** with the employment window |
| `employed_days` | days in the employment window already used for `prorated_annual_compensation` |

## Changed/added columns on `int_employee_contributions`

| Column | Before | After |
|--------|--------|-------|
| `prorated_annual_compensation` | employment-window comp | **unchanged** (preserves comp reporting for 15+ consumers) |
| `effective_annual_deferral_rate` | latest (year-end) rate → `0` for opt-outs | `enrollment_window_deferral_rate` for `is_same_year_enroll_optout`; else unchanged |
| `total_contribution_base_compensation` | `= prorated_annual_compensation` | `prorated_annual_compensation × (active_enrollment_days / employed_days)` for `is_same_year_enroll_optout`; else `= prorated_annual_compensation` |
| `annual_contribution_amount` | `prorated_annual_compensation × year-end_rate` (IRS-capped) | `total_contribution_base_compensation × effective_annual_deferral_rate` (IRS-capped) |
| `active_enrollment_days` *(new, audit)* | — | days credited (0 for non-opt-out / full-year) |
| `contribution_window_category` *(new, audit)* | — | `'enroll_optout_window'` \| `'full_year'` \| `'partial_year'` (termination) |

**Validation rules**
- `total_contribution_base_compensation ≤ prorated_annual_compensation` always (enrolled ≤ employed days). (FR-002/003)
- `annual_contribution_amount ≥ 0`; never negative for degenerate windows. (FR-007)
- For `is_same_year_enroll_optout`: `annual_contribution_amount > 0` when `active_enrollment_days > 0` and rate > 0. (FR-001, SC-001)
- For non-opt-out employees: all columns identical to current behavior. (FR-006, SC-005)

## Changed reference: `int_employee_match_calculations`

| Consumed field | Before | After |
|----------------|--------|-------|
| `eligible_compensation` | `ec.prorated_annual_compensation` | `ec.total_contribution_base_compensation` |
| `deferral_rate` | `ec.effective_annual_deferral_rate` | unchanged (now carries the window rate for opt-outs) |

Effect: match = `window_rate`-driven tiers × active-window comp for opt-out employees; **unchanged** for everyone else (the two comp columns are equal). (FR-004, SC-004)

## Unchanged: Year-End Participation Snapshot

`fct_workforce_snapshot` year-end `participation_status` / `current_deferral_rate` continue to derive from `int_enrollment_state_accumulator` (latest-event-wins, feature 095) — **not** from `effective_annual_deferral_rate`. Setting the window rate in the contribution model therefore cannot regress year-end status. (FR-005, SC-003) — to be re-verified during implementation (research R-open).

## Guard (new): `assert_same_year_enroll_optout_window.sql`

Asserts, per same-year enroll→opt-out employee-year: year-end `participation_status='not_participating'` AND `current_deferral_rate=0` AND `annual_contribution_amount > 0`. Severity `warn` initially → `error` once implemented. (FR-008, SC-006)
