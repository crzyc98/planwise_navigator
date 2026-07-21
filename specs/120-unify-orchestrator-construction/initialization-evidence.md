# Fresh-database initialization evidence

## Contract

Normal CLI, batch, and Studio construction uses `InitializationPolicy.NONE`.
The pipeline's seed, staging, and start-year preparation is authoritative.
`SELF_HEALING` is an explicit diagnostic policy executed before optional hooks;
any failed step raises `InitializationError` and aborts.

## Validation

- Forced failure was exercised through both `cli.simulate` and `batch`
  attribution. Each run raised before workflow execution, included a
  correlation ID, `pre_simulation` failed-step context, missing-table data and
  resolution guidance, and produced zero authoritative fact tables.
- A fresh CLI-attributed `NONE` run and an explicitly pre-initialized,
  batch-attributed `SELF_HEALING` run used the deterministic invariant census,
  seed, config, year, and separate isolated DuckDB files.
- `fct_yearly_events` and `fct_workforce_snapshot` matched in both directions
  with `EXCEPT ALL` over explicit columns; only their documented build-time
  timestamp columns were excluded.
- Optional hook error isolation remains covered independently.

The gate exposed and repaired three stale assumptions in the diagnostic path:
the enrollment projection must exist before staging, foundation selection must
include upstream DAG dependencies (`+tag:FOUNDATION`), and the IRS seed is named
`config_irs_limits`. These repairs do not add initialization work to the normal
`NONE` product path.

This closes the swallowed-critical-initialization concern tracked by #467: no
self-healing initializer is registered with `HookManager`, whose contract is to
isolate optional extension failures.
