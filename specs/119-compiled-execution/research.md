# Phase 0 Research: Compiled DAG Execution — #470 Hardening

All decisions are grounded in the checked-in prototype, dbt Core 1.8.8 and DuckDB 1.0.0 available in the repository environment, the Feature 113 invariant framework, and the Feature 116 performance harness. No open technical question remains.

## R1 — Preserve the `DbtRunner.execute_command` seam

**Decision**: Keep `CompiledRunner(DbtRunner)` as a substitutable runner and implement the hardening as an explicit invocation state machine behind `execute_command`.

**Rationale**: Existing stages already funnel their dbt work through this method, preserving workflow, hook, telemetry, error, CLI, batch, API, and Studio behavior without duplicating pipeline logic. The state machine makes `request → preflight → direct transaction or delegation → record` visible and testable.

**Alternatives considered**: Replacing `YearExecutor` or stage executors would duplicate orchestration semantics; a separate side pipeline would create a second behavioral definition.

## R2 — Give every run an isolated dbt workspace and explicit profile

**Decision**: Create a runner-owned `RunArtifactWorkspace`. Generate a run-scoped `profiles.yml` with the resolved absolute DuckDB path and pass unique `--target-path` and `--log-path` values to every in-process dbt invocation.

**Rationale**: The prototype reads `dbt/target`, and its in-process dbt helper never propagates `database_path`. A fallback can therefore target the shared development database and any compile/build/fallback can overwrite cached SQL. dbt 1.8.8 supports explicit target paths. A profile overlay avoids process-global environment mutation and remains safe for independently running scenarios.

**Alternatives considered**: Temporarily changing `DATABASE_PATH` is process-global and race-prone. Locking shared `dbt/target` serializes runs without preventing stale or out-of-band mutation. Subprocess-only dbt restores isolation but loses most startup savings.

## R3 — Parse once per static project context; publish executable bundles atomically

**Decision**: Reuse one dbt-produced manifest within a run while the static project digest matches. Compile selected SQL into a unique staging target, validate it, then atomically rename it into `bundles/<render_context_sha256>/`. Never point dbt at a published bundle.

**Rationale**: Mutable work artifacts are useful for dbt partial parsing, but executable SQL must not change after preflight. Atomic publication prevents partial bundles. Storing SQL plus hashes retains audit/debug value without keeping a database connection open.

**Alternatives considered**: Reading directly from `dbt/target` is corruptible. Keeping only Python strings protects one process but loses restart diagnostics and can increase memory. Marking a shared directory read-only does not isolate concurrent builders.

## R4 — Key bundles by the complete render context

**Decision**: Canonically hash project/package/selector content, dbt/adapter versions, profile and target settings, absolute database destination, exact vars, normalized command/select/exclude/full-refresh options, selected nodes/order, render-relevant environment, dbt volatile render identity, and selected relation-state metadata.

**Rationale**: `is_incremental()` depends on relation existence, and the project also uses `invocation_id`, `run_started_at`, `execute`, and environment-backed project defaults. A year-plus-vars key is insufficient. A commit advances the relation-state epoch; reuse is permitted only when the observed render state remains identical.

**Alternatives considered**: Compile once per year is fast but can freeze the wrong incremental branch after relations appear. Cross-run global reuse cannot prove matching database state. Omitting volatile render inputs changes audit fields.

## R5 — Resolve selectors through dbt and fail closed on invocation options

**Decision**: Deserialize the dbt manifest, construct dbt's dependency graph, parse selection/exclusion with dbt 1.8.8 selector APIs, and consume its single-thread graph queue. Parse the complete command with a supported-option allowlist. A zero-node result delegates to dbt; it never returns direct success.

**Rationale**: The prototype hand matcher supports only simple name/fqn/tag patterns and silently maps unknown semantics to an empty list. dbt owns union, intersection, graph operators, path, tag, named selector, indirect selection, state, result, and exclusion semantics. Unsupported context-dependent methods must be identified rather than guessed.

**Alternatives considered**: A `dbt ls` subprocess is a useful test oracle but repeats startup. Hand parsing has already demonstrated semantic drift. Treating every empty selection as success hides misspellings and unsupported methods.

## R6 — Make preflight complete and side-effect free

**Decision**: Before `BEGIN`, freeze the ordered node plans, compiled SQL bytes/hashes, relations, materializations, strategies, unique keys, schema-change behavior, model hooks, project hooks, and all DDL/DML projections. Return either a supported immutable `InvocationPlan` or typed `KnownUnsupportedSemantics`.

**Rationale**: Fallback is safe only if unsupported behavior is discovered before writes. Precomputing schema and relation decisions also removes branching and filesystem reads from the transaction body.

**Alternatives considered**: Lazy validation per node allows partial writes. Preflighting only command type misses hooks and materialization drift. Dry-running SQL cannot prove side-effect safety.

## R7 — Treat informational `log()` hooks as supported lifecycle records

**Decision**: Recognize pure dbt `log()` hook expressions, record their lifecycle occurrence, and emit no DuckDB statement. Render the repository's known PRAGMA/SET and guarded-delete hooks; classify any unmodeled side effect or Jinja construct as unsupported during preflight.

**Rationale**: The committed project has log-only start/end hooks. Logging is not a database semantic and must not force universal fallback. Ignoring all hooks would lose required side effects; attempting to execute rendered log output as SQL is incorrect.

**Alternatives considered**: Adding a permissive Jinja environment risks silently changing macro behavior. Delegating every invocation containing `log()` defeats the feature. Reproducing dbt log text byte-for-byte is unnecessary.

## R8 — Execute exactly one transaction per direct invocation

**Decision**: After preflight, open a short-lived explicit DuckDB connection, apply connection settings, execute `BEGIN`, run all frozen node operations and hooks, then `COMMIT`. On every exception, `ROLLBACK` and close before further handling.

**Rationale**: DuckDB 1.0.0 transactions roll back DDL and DML used by the repository's materializations. Invocation atomicity prevents the prototype's drop/delete/insert changes from leaking into a dbt replay. Short-lived connections satisfy repository connection discipline.

**Alternatives considered**: Per-node transactions expose a partially updated DAG. Savepoints complicate materialization parity. A persistent plan-cache connection conflicts with dbt and violates the constitution's long-operation rule.

## R9 — Delegate only typed known-unsupported semantics

**Decision**: Normal delegation happens only from preflight for stable codes such as unsupported command, option, selector context, resource, materialization, hook, or schema-change behavior. A defensive typed late occurrence rolls back first and is recorded as an unexpected preflight defect. Generic compile, SQL, database, hash, or internal errors fail without replay.

**Rationale**: Catch-all fallback can hide engine defects and re-execute after partial mutation. Typed classification makes every degradation auditable and makes zero unexpected fallback a structural gate.

**Alternatives considered**: Retrying all exceptions through dbt prioritizes apparent completion over correctness. Per-node fallback mixes executors within one atomic unit. Disabling fallback entirely would make known unsupported but valid dbt operations unusable.

## R10 — Keep dbt-authored transformation SQL; freeze adapter-equivalent wrappers

**Decision**: Support only the repository-proven `view`, `table`, incremental `append`, and incremental `delete+insert` shapes. dbt supplies compiled transformation SQL; preflight freezes the surrounding operations using typed manifest relations and centralized identifier quoting.

**Rationale**: This retains dbt as the semantic author while removing repeated runner overhead. Unknown strategies, hooks, resources, or unproven schema synchronization delegate before writes.

**Alternatives considered**: Calling dbt materialization macros per node recreates dbt execution overhead. Reauthoring SELECT logic breaks parity. Supporting every adapter materialization is outside the committed project scope.

## R11 — Compare schemas and row multisets, not sets

**Decision**: Compare ordered schema metadata first, then use symmetric `EXCEPT ALL` over non-exempt values. Diagnose divergences with grouped side counts per distinct row and bounded samples.

**Rationale**: Ordinary `EXCEPT` collapses duplicates. Equal total counts can still hide moved multiplicities, for example baseline `(x,x,y)` versus candidate `(x,y,y)`. DuckDB 1.0.0 supports `EXCEPT ALL`, which remains database-native and memory efficient.

**Alternatives considered**: Row count plus ordinary `EXCEPT` false-passes. Fetching and sorting entire tables in Python is memory-heavy at 100K. Checksums alone produce poor diagnostics and can hide collisions.

## R12 — Add a terminal append-only execution record

**Decision**: Keep the Feature 109 `run_metadata` row as the startup/drift record. Append a separate terminal execution record keyed by the authoritative `run_id`, plus immutable per-invocation records in runtime provenance.

**Rationale**: Final direct/delegated/fallback counts are not known when `run_metadata` is inserted. Updating that row would violate append-only semantics; inserting a second indistinguishable startup row would corrupt drift-history meaning.

**Alternatives considered**: Updating `run_metadata` is not append-only. Logging alone is difficult to query and cannot reliably prove the zero-fallback gate. Adding nullable terminal columns to the startup row still requires mutation.

## R13 — Extend the existing performance harness with paired engine evidence

**Decision**: Add campaign and engine dimensions to artifact names, paired dbt/compiled repetitions, exact census/config fingerprints, fallback counts, and recursive process-tree peak RSS. Generate 105,070 rows with factor 14 for the 100K gate.

**Rationale**: The existing `large` artifact is 60,040 rows, not 100K. Current sample names would overwrite baseline evidence when the second engine runs, and current samples lack memory/fallback fields. All compilation, preflight, and delegation cost must remain inside total wall time.

**Alternatives considered**: Calling 60K “100K-class” violates the constitution. Reusing historical baselines introduces environment drift. Measuring only direct SQL hides compilation and fallback costs.

## R14 — Preserve strict gate ordering and strategic sequencing

**Decision**: Prove tiny parity; multi-year invariants/determinism/rerun; development and 60K parity; actual 100K completion/memory; paired performance; and zero unexpected fallback, in that order. Flip the default only afterward. Begin #471 only after #470 completes; keep #472–#475 blocked until #471 GO.

**Rationale**: Later scale or speed evidence cannot compensate for an earlier correctness failure. The native-kernel spike is valuable only after the current execution contract is stable enough to provide an oracle and benchmark.

**Alternatives considered**: Flipping early increases blast radius. Starting the native program before #470 leaves no trustworthy parity oracle. Running all gates concurrently wastes expensive large runs when tiny correctness is still failing.
