# Contract: Participation Label Lineage

**Component**: `dbt/models/marts/fct_workforce_snapshot.sql` — `participation_status_detail` derivation (participating branch)
**Inputs**: `int_deferral_rate_state_accumulator dsa` (participation signal), `int_enrollment_state_accumulator esa` (lineage), joined per `(employee_id, simulation_year)`

## Label derivation (participating employees: `COALESCE(dsa.current_deferral_rate, 0) > 0`)

| # | Enrollment state (`esa`) | Label |
|---|---|---|
| 1 | `enrollment_method = 'auto'` | `participating - auto enrollment` (unchanged) |
| 2 | `enrollment_method = 'voluntary'` | `participating - voluntary enrollment` (unchanged) |
| 3 | `enrollment_method IS NULL` **and** `enrollment_source = 'baseline'` | `participating - census enrollment` (tightened: baseline source now required) |
| 4 | `enrollment_method IS NULL` **and** `enrollment_source LIKE 'event_%'` | `participating - voluntary enrollment` (event-sourced enrollment with unrecorded method takes the existing voluntary fallback; previously mislabeled as census) |
| 5 | `enrollment_method IS NULL` otherwise (no `esa` row at all, `enrollment_source = 'none'`, or NULL) | `participating - unknown source` (new — reserved for participation with no enrollment lineage; the issue #419 contamination signature) |
| 6 | Any other `enrollment_method` value | `participating - voluntary enrollment` (unchanged fallback) |

Not-participating branch: unchanged.

## Invariant (dbt data test `dbt/tests/test_participation_label_lineage.sql`)

For every simulated year: zero rows in `fct_workforce_snapshot` where `participation_status_detail = 'participating - census enrollment'` and the matching `int_enrollment_state_accumulator` row does not have `enrollment_source = 'baseline'` (or has no matching row).

## Consumer notes

- `participation_status` (high-level `participating`/`not_participating`) is **not** changed by this feature; row counts per status are stable — only the detail string for previously-mislabeled rows changes.
- Any downstream consumer bucketing on the exact string `'participating - census enrollment'` will now see those anomalous rows under `'participating - unknown source'`; this is the intended surfacing of a defect, not a regression. Implementation must grep Studio/analytics consumers of `participation_status_detail` literals and extend enumerations where the new value needs display support.
- In a healthy post-#419/#418 database, `'participating - unknown source'` should be empty; its presence is a diagnostic signal of state contamination.
