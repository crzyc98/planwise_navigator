# Contract: Data-Quality Tests for Voluntary Enrollment Reconciliation

**Date**: 2026-06-15 | **Branch**: `095-fix-enrollment-snapshot`

This project's external "interface" for a data-correctness fix is its **dbt test surface**: assertions that run in `dbt build` / `dbt test` and gate the pipeline. These contracts define the tests that MUST exist and pass after the fix (and MUST fail before it).

## Contract 1 — Voluntary enrollees appear as participating (FR-001, FR-003, FR-010)

**Test model**: `dq_voluntary_enrollment_snapshot` (new, `models/marts/data_quality/`), registered with a dbt test that fails when the model returns rows.

**Definition** (returns offending rows = failure):

```text
For each (employee_id, simulation_year) where fct_yearly_events has an enrollment event
with event_category IN ('voluntary_enrollment','proactive_voluntary','year_over_year_voluntary')
AND the employee has NO opt-out (enrollment_change … 'opt-out') with a later/equal effective_date in that year:
  FAIL the row if the matching fct_workforce_snapshot record for that (employee_id, simulation_year)
  has participation_status <> 'participating' OR current_deferral_rate <= 0 OR is missing.
```

**Severity**: `error` (fails the build — FR-010).

**Pre-fix expectation**: returns the 60 rows for 2026 (59 voluntary_enrollment + 1 year_over_year_voluntary). **Post-fix expectation**: returns 0 rows.

## Contract 2 — Snapshot deferral rate equals enrollment-event rate (FR-002, FR-005)

**Assertion**: For each voluntary enrollee (no same-year opt-out), `fct_workforce_snapshot.current_deferral_rate` equals the `employee_deferral_rate` of their latest voluntary enrollment event for that year (within DECIMAL(5,4) tolerance), except where a same-year escalation/match-response legitimately adjusted it.

**Form**: a `dbt test` (singular SQL test or a column test on the dq model) returning rows where the rates diverge without a recorded escalation/match-response/opt-out reason. Severity `error`.

## Contract 3 — Participation/deferral consistency (FR-005)

**Assertion**: In `fct_workforce_snapshot`, `participation_status = 'participating'` ⇔ `current_deferral_rate > 0`. No record may be `participating` with rate 0, or `not_participating` with rate > 0.

**Form**: singular dbt test over `fct_workforce_snapshot`. Severity `error`.

## Contract 4 — Cross-category reconciliation (FR-006, FR-009)

**Assertion**: For each `simulation_year`, the count of snapshot participants attributable to each enrollment category reconciles to the count of that category's enrollment events net of opt-outs, with zero unexplained discrepancy. Voluntary categories must reconcile to the same standard as `auto_enrollment`.

**Form**: a reconciliation query (may live in the dq model or a singular test) asserting `enrollment_events_net_of_optouts - snapshot_participants = 0` per category-year. Severity `error` for voluntary categories.

## Contract 5 — Multi-year persistence (FR-007)

**Assertion**: An employee enrolled (voluntarily) in year Y with no subsequent opt-out/unenroll event remains `participating` with a non-zero deferral rate in every snapshot year > Y up to the run horizon.

**Form**: integration assertion (pytest over a built multi-year DB, or a dbt test joining consecutive years). Severity `error`.

## Non-contract (explicitly out of scope here)

- **FR-008 prorated active-window contribution** is **not** asserted by these contracts; it is Phase C. A placeholder test may be added but marked `warn` (or skipped) until Phase C is implemented, so as not to block the core fix.

## Execution

```bash
cd dbt
# Build accumulator + snapshot chain for the affected years, then run the new tests
dbt build --select int_deferral_rate_state_accumulator+ --threads 1
dbt test  --select dq_voluntary_enrollment_snapshot fct_workforce_snapshot --threads 1
```

Tests MUST be demonstrated **failing on the current DB** before the model change and **passing after** it.
