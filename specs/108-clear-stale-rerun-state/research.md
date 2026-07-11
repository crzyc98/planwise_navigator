# Research: Clear Stale Prior-Run State on Scenario Re-Run

**Feature**: 108-clear-stale-rerun-state | **Date**: 2026-07-10

All Technical Context entries were resolvable by direct code inspection; no external research required. Findings below are grounded in the current `main` (post-#420 merge).

## R1. What feature 107 actually changed vs. what issue #419 needs

**Finding**: Feature 107's cleanup change was narrow: it flipped the *default value of `clear_mode`* from `'all'` to `'year'` (`state_manager.py:153`, `:224`) — but both `maybe_clear_year_data` and `maybe_full_reset` still return early when `setup` is absent or `setup.clear_tables` is falsy (`state_manager.py:148-151`, `:221-223`). Studio-created scenario configs carry no `setup` block, so on the Studio re-run path **neither method does anything**. The only unconditional cleanup is `clear_year_fact_rows` (`pipeline_orchestrator.py:558`), which covers exactly `fct_yearly_events`, `fct_workforce_snapshot`, `fct_employer_match_events` — not `int_deferral_rate_state_accumulator`.

**Decision**: Root cause #3 of the issue is still open. This feature closes it by making the year-scoped purge the default behavior of `maybe_clear_year_data`.

## R2. Why delete+insert cannot fix this on its own

**Finding**: `int_deferral_rate_state_accumulator` is incremental with `delete+insert` keyed on `(employee_id, simulation_year)` (plus scenario keys). Its year-2+ SELECT only emits rows for enrolled/newly-enrolled employees (~line 512), so a re-run with AE off produces **no rows at all** for never-enrolled employees — and `delete+insert` only deletes keys present in the new insert set. Prior-run rows for absent keys survive verbatim (confirmed: 1,582 stale 2027 rows with `created_at = 2026-07-04` after the 2026-07-10 re-run). Worse, the year-3 build reads year-2 prior state including the stale rows and re-emits them as `carried_forward` rows with *fresh* timestamps, laundering the contamination.

**Decision**: The purge must be an orchestrator-level year-scoped `DELETE` executed before each year builds, independent of which keys the dbt model regenerates. A dbt-side `pre_hook` per model was rejected: ~60 incremental models would each need auditing and the hook runs per-model rather than per-year-per-run, and models not selected in a given run would still never fire their hook.

**Alternative rejected**: Widening the accumulator's year-2+ WHERE clause to emit "not enrolled" rows for every employee would fix this one table but (a) bloats every year's state by the full population, (b) leaves every other sparse incremental table with the same latent bug, and (c) changes model semantics reviewed under E023/E036.

## R3. Default-on purge semantics (FR-001/FR-002/FR-003)

**Decision**: In `maybe_clear_year_data`:

| `setup` / `clear_tables` / `clear_mode` | New behavior |
|---|---|
| `setup` absent or not a dict | **Purge year** (default patterns) — *changed (was: no-op)* |
| `clear_tables` unset (key absent) | **Purge year** — *changed (was: no-op)* |
| `clear_tables: false` (explicit) | No-op (documented opt-out) — unchanged for explicit false |
| `clear_tables: true, clear_mode: 'year'` (or unset mode) | Purge year — unchanged |
| `clear_tables: true, clear_mode: 'all'` | Skip year-level (one-time full reset via `maybe_full_reset`) — unchanged |

`maybe_full_reset` keeps requiring explicit `clear_tables: true` + `clear_mode: 'all'` — a destructive full wipe must never become a default.

**Rationale**: "unset ≠ false." The purge is exactly what `clear_tables: true` users already run; making it the default matches the spec's safe-by-default requirement and the one-DB-per-scenario invariant, and requires zero Studio/API/config changes. The purge is idempotent, scenario/plan-scoped via the existing `_year_scope` helper (falls back to `'default'` IDs consistently with dbt's `var('scenario_id', 'default')`), tolerates missing tables (existence check in `_delete_year_rows`), and is a no-op on fresh databases (FR-006).

**Safety analysis**:
- *Temporal accumulators*: purging year N before building year N never touches year N−1, which is what accumulators read (`{{ this }} WHERE simulation_year = N-1`). Safe.
- *Mid-range runs*: a run starting at year Y > scenario start legitimately reads year Y−1 state; the purge only deletes years being simulated. Years `< start_year` are never touched.
- *Orphaned models*: tables with a `simulation_year` column that no longer feed the pipeline get their year rows deleted and not rebuilt — already true for `clear_tables: true` users; harmless (orphans are dead data by definition).
- *`enrollment_decision_projection`* (feature 107): rebuilt atomically per year by the orchestrator with its own scoped delete; unaffected whether or not the pattern list catches it.

## R4. Out-of-range stale years (shorter re-run edge case)

**Finding**: Re-running 2026–2028 after a 2026–2030 run leaves stale 2029–2030 rows that per-year purging never visits; exports reading the whole DB would include them.

**Decision**: Detect and **warn** at run start (rows for this scenario with `simulation_year > end_year` in the critical fact tables), recommending `clear_tables: true, clear_mode: 'all'` for a clean slate. Do **not** auto-delete: deleting data outside the requested range is destructive and a user may be intentionally re-running an early year segment. Deleting years `< start_year` is strictly forbidden (breaks legitimate prior-year-state consumption). This mirrors the project's established preference for warnings over destructive/automatic cross-boundary cleanup.

## R5. Participation label lineage (FR-007/FR-008)

**Finding**: `fct_workforce_snapshot.sql` LEFT JOINs `int_enrollment_state_accumulator esa` directly (line 805), so `esa.enrollment_source` is available at the label site (lines 707-715). The accumulator sets `enrollment_source = 'baseline'` for census enrollments and *deliberately* leaves `enrollment_method` NULL for them ("Census enrollments are pre-existing, not simulation decisions", accumulator line ~160). The current fallback `enrollment_method IS NULL → 'participating - census enrollment'` therefore mislabels two cases: (a) contaminated rows where the employee has **no** esa enrollment at all (`esa` row missing or `enrollment_source = 'none'`), and (b) any future NULL-method anomaly.

**Decision**: Gate the census label on `esa.enrollment_source = 'baseline'` (carried-forward baseline state keeps `previous_enrollment_source`, so multi-year census participants retain `'baseline'`). Unexplained positive deferral falls to a new distinct label `'participating - unknown source'`. Add dbt data test `test_participation_label_lineage.sql`: zero rows where `participation_status_detail = 'participating - census enrollment'` and the accumulator does not show a baseline-source enrollment.

**Downstream check** (T012 findings): two consumers of `participation_status_detail` exist. `planalign_api/services/analytics_service.py:199-202` buckets with ILIKE patterns (`%auto%`, `%voluntary%`, `%census%`) — `'participating - unknown source'` intentionally matches none of them and is excluded from the census bucket (correct; totals use `is_enrolled_flag` and are unaffected). `planalign_orchestrator/reports/multi_year_reporter.py:167-172` enumerates exact strings — extended with an `unknown_source` column so anomalous rows are visible in the breakdown report. No Studio frontend or other consumer references the literals.

## R6. Regression & validation strategy (FR-009, SC-001..SC-005)

**Decision** (three layers, consistent with the isolated-DB rule):
1. **Unit** (`test_cleanup_scoping.py`): default-on purge with absent `setup`; explicit `clear_tables: false` opt-out; stale accumulator row (key not regenerated) deleted by the year purge; fresh/missing-table no-op; scenario/plan scoping preserved (existing tests updated — notably `test_omitted_clear_mode_defaults_to_year_scoped_cleanup` gains a sibling for fully-absent setup).
2. **Integration** (`test_stale_rerun_purge.py`): seed an isolated DuckDB with a prior-"run" shape — accumulator rows across years with old `created_at`, snapshot rows labeled census-enrollment without baseline lineage — execute the orchestrator's per-year cleanup path for each simulated year, and assert zero surviving pre-run rows and correct year/scenario scoping (mirrors the issue's validation recipe without the cost of two full simulations).
3. **Manual/quickstart**: full AE-on → AE-off re-run of the same isolated scenario DB (`planalign simulate` twice with edited config), asserting `MIN(created_at)` ≥ second-run start in `int_deferral_rate_state_accumulator` and zero phantom participants — the literal validation from issue #419.
