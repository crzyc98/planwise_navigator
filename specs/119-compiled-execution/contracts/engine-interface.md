# Contract: Compiled Execution Engine

This contract covers the runner seam, invocation state machine, delegation policy, configuration, and provenance behavior.

## 1. Runner substitutability

`CompiledRunner` remains usable everywhere a `DbtRunner` is accepted.

```text
execute_command(
  command_args,
  *,
  description,
  simulation_year,
  dbt_vars,
  threads,
  stream_output,
  on_line,
  retry,
  max_attempts,
  log_performance,
) -> DbtResult
```

- Signature and `DbtResult` fields remain compatible.
- Inherited `run_model` and `run_models` continue to funnel into `execute_command`.
- `working_dir`, `db_manager`, `threads`, `executable`, and `database_path` retain their existing meaning.
- Direct execution synthesizes bounded node/lifecycle output for current consumers; it does not promise byte-identical dbt log text.
- Existing entry points remain unchanged unless the caller selects the compiled engine.

## 2. State machine

```text
RECEIVED
  -> PREFLIGHTING
       -> UNSUPPORTED -> DELEGATING -> SUCCEEDED | FAILED
       -> PLANNED -> EXECUTING
            -> COMMITTED -> SUCCEEDED
            -> ROLLED_BACK -> FAILED
            -> ROLLED_BACK_UNSUPPORTED -> DELEGATING -> SUCCEEDED | FAILED
```

Invalid transitions are engine errors. In particular:

- `EXECUTING -> DELEGATING` without a completed rollback is forbidden.
- Generic failure cannot transition to `DELEGATING`.
- `SUCCEEDED` direct execution requires at least one dbt-resolved node.
- Every terminal state emits one immutable invocation record.

## 3. Explicit dbt invocation arguments

Every programmatic dbt call includes:

```text
--project-dir <repo>/dbt
--profiles-dir <run-workspace>/profile
--target-path <unique-mutable-target>
--log-path <unique-log-path>
--threads 1
```

The generated profile's selected DuckDB target contains the normalized absolute `CompiledRunner.database_path`. Before invocation, the engine asserts it equals `db_manager.db_path`. Ambient `DATABASE_PATH` must not determine the target.

Published bundle paths are never passed as `--target-path`.

## 4. Direct eligibility

An invocation is directly executable only when preflight proves all of the following:

- The complete command/options were parsed with no unconsumed token.
- The command is an eligible `run` invocation with required simulation context.
- dbt resolved a non-empty supported model selection and order.
- The published bundle matches the full render context and target relation state.
- Every executable node has present, hash-valid compiled SQL.
- Every resource, materialization, incremental strategy, schema-change action, pre-hook, post-hook, and project hook is supported.
- The explicit database/profile identity matches the runner target.
- Every DDL/DML operation and projection has been frozen before `BEGIN`.

Failure to prove a condition is never interpreted as direct success.

## 5. Delegation policy

Only `KnownUnsupportedSemantics` authorizes in-process dbt delegation. Stable reason-code families are:

- `command` / `full_refresh`
- `option`
- `selector_context` / `empty_selection`
- `resource_type`
- `materialization` / `incremental_strategy`
- `hook`
- `schema_change`

A known unsupported result found during preflight delegates before a transaction. A defensive typed occurrence after `BEGIN` must roll back and close first, then delegates and increments `unexpected_fallback_count` because preflight failed to detect it.

The following never delegate: dbt compilation failure, malformed project artifacts, bundle hash mismatch, DuckDB SQL/catalog/lock/integrity failure, transaction failure, or unclassified internal exception.

## 6. Transaction contract

For a supported invocation:

1. Open the explicit target connection after preflight.
2. Apply frozen connection-local project settings.
3. Execute `BEGIN`.
4. Run node pre-hooks, materialization operations, and node post-hooks in frozen dbt order.
5. Execute `COMMIT` only after all operations succeed.
6. On any exception, execute `ROLLBACK`, record its outcome, close the connection, then apply the delegation policy.

No write connection remains cached between invocations or while dbt compiles/delegates.

## 7. Hook behavior

- Pure `{{ log(...) }}` project hooks are supported informational lifecycle records and emit no SQL.
- Supported PRAGMA/SET start hooks are applied to the direct connection before `BEGIN`.
- Supported model pre/post SQL hooks execute inside the invocation transaction.
- Project end informational hooks are recorded after commit.
- Any unproven hook behavior is a preflight `hook` delegation, not a runtime guess.

## 8. Config and CLI

```yaml
optimization:
  execution_engine: dbt   # dbt | compiled
```

```bash
planalign simulate 2025-2027 --engine compiled
planalign simulate 2025-2027 --engine dbt
```

- Config is Pydantic validated.
- CLI override wins for that run.
- Batch, Studio, and API use the effective scenario configuration through the existing factory.
- Default remains `dbt` until all ordered acceptance gates pass.

## 9. Observability and provenance

Each invocation record exposes:

- run ID, sequence, year, and stage;
- direct or delegated mode and stable reason;
- context and bundle digests;
- planned, attempted, and completed node IDs;
- elapsed time and target identity digest;
- commit/rollback outcome;
- bounded node/phase/statement error context.

Run completion appends one terminal execution record keyed by `run_id`. The existing startup `run_metadata` row is never updated. A normal supported matrix must aggregate to `unexpected_fallback_count = 0`.
