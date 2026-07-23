# Contract: Run Database Lifecycle

## Scope

This contract applies to Studio/API-managed single-scenario and batch simulation attempts. A direct CLI invocation remains responsible for choosing its own explicit isolated `--database` destination. Calibration keeps its existing lifecycle; it must remain compatible with the normalized shared graph but does not gain current-result publication or active-run warnings through this feature.

## Allocation

1. Generate and validate a canonical UUID `run_id`.
2. Exclusively create `workspaces/<workspace>/scenarios/<scenario>/runs/<run_id>/`.
3. Reject path traversal, reuse of an existing run directory, or an existing target database.
4. Persist queued/running attempt metadata and configuration in that run directory.
5. Invoke the simulation with `runs/<run_id>/simulation.duckdb` as both the CLI database argument and effective `DATABASE_PATH`.
6. Never clean, overwrite, attach for writes, or copy from the legacy scenario DB or another run DB.

The database is authoritative for that attempt from its first write. A run archive is therefore a finalized run directory, not a post-success copy of mutable scenario state.

## Successful completion

Publication occurs only in this order:

1. The simulation exits successfully and all database connections close.
2. Completed `run_metadata.json` is atomically finalized.
3. `provenance.json` is atomically finalized.
4. The run DB is confirmed to exist, be readable, and correspond to the run's identity/status evidence.
5. Optional exports are generated; export failure is recorded but cannot substitute for the authoritative DB.
6. A versioned `current_result.json` is written to a same-directory temporary file, flushed/fsynced, and atomically installed with `os.replace`.
7. Attempt status/registry/telemetry is finalized as completed.

Readers can observe the prior complete result or the new complete result, never a partially promoted database.

## Failure and cancellation

- Finalize failed/cancelled metadata and provenance in the attempt directory.
- Retain any partial run DB and associate it only with the terminal failed/cancelled run.
- Do not mutate `current_result.json`.
- Do not change any prior run DB/archive or the shared development DB.
- A rerun allocates a new UUID, directory, and empty database.

## Read resolution

When `current_result.json` exists:

1. Validate its schema version and canonical UUID.
2. Derive the contained run directory.
3. Require terminal completed metadata and a readable DB.
4. Return that DB and run ID.

Any failure is an integrity error. Do not scan another run or fall back to legacy data.

When no pointer has ever existed, use the compatibility order already supported by the resolver: legacy scenario DB, then the existing workspace/project fallback. The first new success creates the pointer and ends implicit selection for that scenario.

## Attempt versus result state

- `scenario.json.status` and `last_run_id` describe the newest attempt.
- `current_result.json.run_id` identifies the served successful result.
- The values intentionally differ while a newer attempt is queued/running or after it fails.
- Result routes must not overwrite attempt status based on the presence of older results.
- Result year ranges and archived configuration come from the selected result run.

## Retention and deletion

Simulation completion performs no automatic pruning. Explicit user-authorized scenario/run deletion may remove run databases under its documented destructive semantics, but it must resolve and report the exact targets. A future retention policy must preserve the current pointer target and requires a separate product decision.

## Invariants

- Every managed attempt uses one fresh database.
- No managed attempt writes to `dbt/simulation.duckdb` or a pre-existing run DB.
- A pointer always names a completed run in the same scenario.
- Failure/cancellation cannot change the selected successful run.
- A successful pointer update is atomic.
- Run IDs, not arbitrary serialized paths, define the target.
- Failed partial state remains auditable and is never served as current results.
