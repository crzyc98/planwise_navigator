# fct_workforce_snapshot TransactionContext Conflict (DuckDB/dbt)

- Date: 2025-08-26
- Status: RESOLVED - Testing confirms mitigation successful

## Summary
Intermittent DuckDB TransactionContext errors during `fct_workforce_snapshot` builds:

- Error text (typical):
  - "Runtime error in model fct_workforce_snapshot: TransactionContext Error: Failed to commit: attempting to modify table fct_workforce_snapshot but another transaction has altered this table"

## Environment
- Engine: DuckDB 1.0.0
- Adapter: dbt-duckdb 1.8.1, dbt-core 1.8.x
- Orchestrator: Navigator (`navigator_orchestrator`)

## Reproduction
1) Prior state (before fix):
   - `dbt` executed with multiple threads (default 4 in some entry points).
   - `fct_workforce_snapshot` used an in-model `pre_hook` to `DELETE` the current year rows.
2) Run either:
   - Orchestrator multi-year or single-year pipeline; or
   - `dbt run --select fct_yearly_events int_workforce_snapshot_optimized int_employee_contributions fct_workforce_snapshot`.

## Expected
- Snapshot rebuilds cleanly without transaction conflicts.

## Observed
- Intermittent commit failure with TransactionContext error referencing concurrent alteration of `fct_workforce_snapshot`.

## Root Cause Analysis
- The `fct_workforce_snapshot` model performed a `DELETE` via a `pre_hook` immediately before the incremental `delete+insert` materialization and index creation.
- In DuckDB, this sequence can race with other catalog/data changes within the same dbt transaction. Even brief, concurrent connections (or dbt’s own index creation) can surface "another transaction has altered this table" during commit.
- Multi-threaded dbt exacerbates timing issues by allowing parallel model work/connections.

## Resolution Implemented
- Enforced single-threaded dbt execution by default across orchestrator entry points:
  - `navigator_orchestrator/dbt_runner.py`: default threads set to 1
  - `navigator_orchestrator/factory.py`: builder default threads set to 1
  - `navigator_orchestrator/cli.py`: CLI default threads set to 1
- Removed in-model year DELETE `pre_hook` from `dbt/models/marts/fct_workforce_snapshot.sql` to eliminate intra-transaction DDL/DML races.
- Moved year-scoped cleanup into the orchestrator before any snapshot build or targeted rebuild that includes `fct_workforce_snapshot`:
  - `navigator_orchestrator/pipeline.py` executes `DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?` prior to running the model.

## Impact
- Preserves idempotent year rebuilds and avoids DuckDB commit conflicts.
- Keeps event→state lineage intact; no logic changes to snapshot beyond moving cleanup timing.

## Validation Steps
- Targeted stage run (single year):
  - `cd dbt`
  - `dbt run --threads 1 --select fct_yearly_events int_workforce_snapshot_optimized int_employee_contributions fct_workforce_snapshot --vars '{"simulation_year": 2025}'`
- Orchestrator run:
  - `python -m navigator_orchestrator.cli run --config config/simulation_config.yaml --threads 1`
- Sanity query:
  - `duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2025"`

## Follow-ups (Optional Hardening)
- [ ] Move snapshot index creation to a post-build macro (run-operation) to further decouple DDL from inserts.
- [ ] Ensure all read-only sanity checks avoid holding open transactions while dbt is running.
- [ ] Document DuckDB pre-hook guidance in CLAUDE.md: avoid write pre-hooks on incremental models.

## Files Changed (already applied)
- `dbt/models/marts/fct_workforce_snapshot.sql` (removed pre_hook)
- `navigator_orchestrator/pipeline.py` (pre-run year delete for snapshot and targeted rebuilds)
- `navigator_orchestrator/dbt_runner.py` (threads=1 default)
- `navigator_orchestrator/factory.py` (threads=1 default)
- `navigator_orchestrator/cli.py` (threads=1 default)

## Notes
- If conflicts ever recur, verify no external process holds a connection to `dbt/simulation.duckdb` during builds (e.g., IDEs, dashboards).
