# Error Troubleshooting

## Enrollment decision projection

Before every event-generation year, PlanAlign rebuilds the disposable
`enrollment_decision_projection` from `int_baseline_workforce` and prior,
scenario/plan-scoped `fct_yearly_events`. This is the only supported source of
post-census enrollment history for enrollment decision models.

Full simulations and comp-only calibration both create the empty source
relation before dbt runs, repairing its schema when necessary. The full
orchestrator replaces it atomically before event generation. If an older
PlanAlign release reports that the relation is missing during calibration,
upgrade and retry; do not manually create or edit the relation.

If a later year fails dependency validation, the prior year's accumulator state
is absent or incomplete. Rerun the simulation from its configured start year,
or restore the prior successful state; do not bypass the error by treating the
employee as unenrolled.

## Safe reruns

Year-scoped cleanup is the default: before each simulated year rebuilds, all
of that year's rows are purged from `int_*`/`fct_*` tables (scoped to the
active scenario and plan design), even when the config has no `setup` block.
This prevents stale prior-run rows from surviving a re-run — sparse
accumulators such as `int_deferral_rate_state_accumulator` emit no rows for
never-enrolled employees, so `delete+insert` alone cannot remove a prior run's
rows for those keys (issue #419's phantom "census enrollment" participants).

- To opt out (e.g., a harness that seeds tables in lieu of dbt builds), set
  `setup.clear_tables: false` explicitly. Unset does NOT mean disabled.
- `setup.clear_mode: all` clears configured tables once before a new
  simulation run and requires explicit `clear_tables: true`. It does not
  authorize a later-year full refresh.
- Re-running a shorter year range leaves the prior run's later years in
  place; the run logs a warning naming those years. For a clean slate, use
  `setup.clear_tables: true` with `setup.clear_mode: 'all'`.

If a snapshot shows participants labeled `participating - unknown source`,
the deferral state claims participation that the enrollment state history
cannot explain — usually stale prior-run state. Re-run the scenario; the
default purge produces clean results.

## Config drift ("CONFIG DRIFT DETECTED" warning)

Every run stamps its effective-config fingerprint, random seed, and year range
into an append-only `run_metadata` table inside the target database. At run
start the engine compares against the most recent record and warns — without
blocking — when the database was last written under a different configuration
or seed, since existing results may then be mixed-generation.

- The warning names what drifted: configuration (fingerprint short-hashes),
  random seed (old → new values), or both.
- Remedies: re-run into a fresh or isolated database (`planalign batch
  --clean` or `--database <new>.duckdb`), or do a clean rerun with
  `setup.clear_tables: true` and `setup.clear_mode: all` (which downgrades the
  message to informational — a full reset makes mixed generations impossible).
- Calibration runs record with `run_type='calibration'` and log
  informationally; diverging comp levers and stale DC tables are inherent to
  calibration.
- Databases created before this feature simply have no history yet; their
  next run records one (no warning, no migration).

Audit a database's provenance directly:

```sql
SELECT run_timestamp, run_type, substr(config_fingerprint, 1, 12) AS fingerprint,
       random_seed, start_year, end_year, full_reset
FROM run_metadata
ORDER BY run_timestamp DESC;
```

Two different fingerprints in the history mean the database has held
mixed-generation results at some point.

## Audit trace

To audit an employee, compare the census row, prior `fct_yearly_events`, the
projection's `latest_event_*` provenance and `current_deferral_rate`, the
accumulator, and the workforce snapshot in chronological order. The projection
must only contain facts from years before its `decision_year` and must match
the active scenario and plan design.
