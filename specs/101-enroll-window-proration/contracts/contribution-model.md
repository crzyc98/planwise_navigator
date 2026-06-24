# Contract: `int_employee_contributions` Output (consumed by match + snapshot)

The contribution model's output columns are the integration seam. This contract pins the semantics so the match model, snapshot, and DQ models stay consistent.

## Grain
One row per `(employee_id, simulation_year)` (unchanged; `delete+insert` on that key).

## Column contract (relevant subset)

| Column | Type | Semantics | Consumers |
|--------|------|-----------|-----------|
| `prorated_annual_compensation` | DECIMAL | Employment-window compensation. **Unchanged by this feature.** | snapshot, comp-growth, core-contrib, many `dq_*` |
| `total_contribution_base_compensation` | DECIMAL | Compensation base the deferral rate is applied to. Equals `prorated_annual_compensation` except for same-year enroll→opt-out, where it is scaled by `active_enrollment_days / employed_days`. | match (`eligible_compensation`), contribution audit |
| `effective_annual_deferral_rate` | DECIMAL | Rate applied to the base. For enroll→opt-out = the enrollment-event window rate; else the existing rate. | match (`deferral_rate`), reporting |
| `annual_contribution_amount` | DECIMAL | `LEAST(total_contribution_base_compensation × effective_annual_deferral_rate, IRS limit)`. | match (`annual_deferrals`), balances, cost |
| `active_enrollment_days` | INTEGER | Days credited for the active window (0 when not an enroll→opt-out case). Audit. | guard, audit |
| `contribution_window_category` | VARCHAR | `'enroll_optout_window' \| 'full_year' \| 'partial_year'`. Audit. | guard, audit |

## Invariants (testable)

1. `0 ≤ total_contribution_base_compensation ≤ prorated_annual_compensation`.
2. `annual_contribution_amount ≥ 0` for all rows, including degenerate windows.
3. Non-opt-out rows: `total_contribution_base_compensation = prorated_annual_compensation` (byte-equal behavior to pre-change).
4. Enroll→opt-out rows with `active_enrollment_days > 0` and window rate `> 0`: `annual_contribution_amount > 0`.
5. IRS 402(g) capping still applies after windowing (no row exceeds its age-based limit).

## Match consumption contract

`int_employee_match_calculations` MUST source `eligible_compensation` from `total_contribution_base_compensation` (not `prorated_annual_compensation`). All match modes (deferral_based, graded_by_service, tenure_based, tenure_graded, points_based) then compute on the active-window base for opt-out employees and are unchanged otherwise.

## Year-end status contract (unchanged)

`fct_workforce_snapshot` year-end `participation_status` / `current_deferral_rate` derive from `int_enrollment_state_accumulator`, independent of `effective_annual_deferral_rate`. This feature MUST NOT alter that path (feature-095 behavior preserved).
