# Contract: Invariant Catalog

The suite's externally observable contract is the set of named invariants and their failure semantics. Downstream consumers: CI (pass/fail + diagnostics), future edge-config matrix (#438) and ensemble (#441) work importing the catalog.

## General contract

- An invariant **passes** iff its `violation_sql` returns zero rows against a fully built simulation DB.
- An invariant is **not evaluated** if the simulation itself failed (FR-014); the suite then reports the simulation error and skips (with reason) all invariant tests.
- Failure output MUST contain: invariant name, description, guarded issue (if any), violation count, and ≤ `sample_limit` violating rows including `employee_id` and `simulation_year` where applicable.
- Empty event populations satisfy invariants vacuously (no promotions ⇒ promotion-related clauses pass).

## Catalog (v1)

| # | Name | Definition (violation condition) | FR | Guards |
|---|---|---|---|---|
| 1 | `event-uniqueness` | Any `event_id` appearing more than once in `fct_yearly_events` across all years | FR-003 | — |
| 2 | `enrollment-no-duplicate` | An employee with two enrollment events not separated by an opt-out/unenrollment event | FR-004 | — |
| 3 | `enrollment-census-persistence` | An employee enrolled at census (baseline `is_enrolled_at_census` / census deferral > 0) who appears non-enrolled in any later year's snapshot with no opt-out event explaining it | FR-004 | #418 |
| 4 | `continuity-headcount` | Year Y ending active headcount ≠ year Y+1 starting active headcount (per the snapshot's status definitions) | FR-005 | #419 |
| 5 | `continuity-no-zombie` | An employee active in year Y with a termination event in year < Y and no intervening rehire event | FR-005 | — |
| 6 | `snapshot-explained-by-events` | A snapshot row whose enrollment status or deferral rate differs from the value derived by replaying that employee's events (and census baseline) through year Y | FR-006 | #419 |
| 7 | `snapshot-no-foreign-rows` | Snapshot or event rows with `simulation_year` outside the run's configured range, or scenario/plan ids other than the run's | FR-006 | #419 |
| 8 | `growth-exactness` | Any year where actual ending headcount differs from the E077 solver's expected value under its documented rounding rule | FR-007 | — |
| 9 | `deferral-explained-changes` | An employee whose deferral rate differs between consecutive years with no explaining event (enrollment, escalation, opt-out, rate change) in between | FR-008 | — |
| 10 | `deferral-cap-respected` | Any deferral rate above the configured auto-escalation cap where escalation events contributed to it | FR-008 | — |
| 11 | `deferral-optout-not-escalated` | An `auto_escalation_opt_out = true` census employee receiving an escalation event | FR-008 | — |

Implementation MAY split a family into additional numbered checks; names are append-only (renames are breaking for CI history and forbidden without a note in this file).

## Determinism comparison contract

- **Inputs**: two DBs built from byte-identical config + seed, same census parquet, same code.
- **Compared tables**: `fct_yearly_events`, `fct_workforce_snapshot`.
- **Method**: per table — (1) row counts equal; (2) symmetric `EXCEPT` over the non-exempt column projection is empty. Together with `event-uniqueness`, this is row-for-row equality.
- **Exempt fields** (initial; additions require a written justification here):

| Table | Column | Justification |
|---|---|---|
| fct_yearly_events | created_at | Build-time `CURRENT_TIMESTAMP` (fct_yearly_events.sql:430); wall-clock bookkeeping, not simulation state |
| fct_workforce_snapshot | (snapshot build-timestamp column, exact name confirmed at implementation) | Same wall-clock rationale |
| run_metadata (whole table) | — | Records run timestamps/fingerprints by design (feature 109) |

- `event_id` is NOT exempt. If runs produce differing ids, that is a bug (or requires an argued exemption added to this table in the same PR).
- **Failure output**: table name, both row counts, diff count, ≤20 differing rows ordered by (simulation_year, employee_id, event_sequence/event_type).
