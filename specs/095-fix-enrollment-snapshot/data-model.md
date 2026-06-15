# Phase 1 Data Model: Enrollment State & Deferral Accumulation

**Date**: 2026-06-15 | **Branch**: `095-fix-enrollment-snapshot`

No database schema changes are introduced. This document records the **semantics** of the existing entities the fix touches, the state-transition rules that must hold, and the validation rules derived from the spec's functional requirements.

## Entities (existing)

### `int_deferral_rate_state_accumulator` (incremental, grain: employee_id × simulation_year)

Source of truth for an employee's deferral rate and enrollment flag within a year. Subsequent years read prior-year rows via `{{ this }}`.

Relevant fields:

| Field | Type | Meaning | Affected by fix |
|-------|------|---------|-----------------|
| `employee_id` | VARCHAR | Employee | — |
| `simulation_year` | INT | Year | — |
| `current_deferral_rate` | DECIMAL(5,4) | Active deferral rate for the year | Indirectly (employee now retained) |
| `is_enrolled_flag` | BOOLEAN | Whether employee is enrolled this year | **Yes — precedence corrected** |
| `original_deferral_rate` | DECIMAL(5,4) | First enrollment rate before escalations | — |
| `employee_enrollment_date` | DATE | Enrollment date (new or carried) | — |
| `rate_source` | VARCHAR | Audit: `enrollment_event` / `carried_forward` / `opt_out` / … | Must stay accurate |

**Inputs (CTEs) referenced by the fix**:
- `ps` = `previous_year_state` (prior-year row from `{{ this }}`)
- `ne` = `current_year_new_enrollments` (this year's enrollment events from `fct_yearly_events`, `event_type IN ('enrollment','benefit_enrollment')`)
- `oo` = `current_year_opt_outs`
- `ce` = `current_year_escalations`, `mr` = `current_year_match_response`

### `fct_workforce_snapshot` (consumer)

Derives, per employee-year:
- `current_deferral_rate` ← `dsa.current_deferral_rate` (COALESCE 0.00)
- `participation_status` ← `dsa.current_deferral_rate > 0 ? 'participating' : 'not_participating'`
- `participation_status_detail` ← uses `esa.enrollment_method` (`auto` / `voluntary` / census)

### `int_employee_contributions` → `int_employee_match_calculations` → `fct_employer_match_events` (downstream)

Read `current_deferral_rate` from the deferral accumulator; once the accumulator retains the employee, contributions and match populate automatically.

## State transitions (enrollment flag, subsequent years)

The corrected precedence for `is_enrolled_flag` in year N (N > start_year):

| Prior-year `ps.is_enrolled_flag` | New enrollment `ne` this year | Opt-out `oo` this year | Resulting `is_enrolled_flag` | Notes |
|----------------------------------|-------------------------------|------------------------|------------------------------|-------|
| any | — | present | `false` | Opt-out wins (FR-008 year-end) |
| any | present | — | `true` | **New enrollment overrides stale prior state (the fix)** |
| `true` | — | — | `true` | Carry forward enrolled (FR-007) |
| `false` | — | — | `false` | Remains unenrolled |
| NULL (no prior row) | present | — | `true` | New hire / first-time enrollee |
| NULL (no prior row) | — | — | `false` | Not enrolled |

**Pre-fix defect row**: prior `false` + new enrollment present + no opt-out → produced `false` (employee dropped). **Post-fix**: produces `true`.

## Validation rules (from Functional Requirements)

| Rule | Source FR | Enforced by |
|------|-----------|-------------|
| Voluntary enrollee (no opt-out) → `is_enrolled_flag = true` and `current_deferral_rate` = event rate | FR-001, FR-002 | Accumulator fix + dbt test |
| Voluntary enrollee → snapshot `participation_status = 'participating'`, `current_deferral_rate > 0` | FR-001, FR-003 | dbt test `dq_voluntary_enrollment_snapshot` |
| Voluntary enrollee under non-zero match formula → employer match > 0 | FR-004 | Downstream propagation; spot-check in quickstart |
| Status, deferral, match mutually consistent | FR-005 | dbt test (rate>0 ⇔ participating) |
| Voluntary not systematically excluded vs auto | FR-006 | Reconciliation counts by category |
| Prior-year enrollment persists until change/opt-out | FR-007 | Carry-forward path unchanged; multi-year test |
| Same-year enroll + opt-out → year-end not participating, no stale rate | FR-008 (status) | Opt-out precedence (Phase A) |
| Same-year enroll + opt-out → credited for active window | FR-008 (proration) | **Phase C (deferred)** |
| Snapshot participating count reconciles to voluntary events net of opt-outs | FR-009 | dbt test |
| Build fails on any unreconciled voluntary enrollee | FR-010 | dbt test severity = error |

## Invariants that must not regress

- Accumulator remains incremental (`delete+insert` by year); never `--full-refresh` mid-simulation.
- Output schema (column set/types) unchanged — downstream models and existing tests keep working.
- Determinism: identical seed + config → identical accumulator output.
- First-year behavior (all workforce employees present, E096) unchanged.
- Auto-enrollment, proactive, and year-over-year categories continue to reconcile (no collateral change).
