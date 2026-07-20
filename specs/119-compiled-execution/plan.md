# Implementation Plan: Compiled DAG Execution — #470 Hardening

**Branch**: `119-compiled-execution` | **Date**: 2026-07-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/119-compiled-execution/spec.md`

## Summary

Harden the current compiled-execution prototype into a correctness-preserving optimization. Each run receives an isolated dbt workspace and an explicit DuckDB profile. dbt parses the project once per run, resolves selectors with dbt's own graph semantics, and compiles into a staging target for the complete render context. Validated SQL and metadata are atomically published as an immutable bundle that dbt never writes to again.

Before direct execution, a fail-closed preflight freezes the complete invocation plan: selected nodes, order, hooks, materializations, relation state, SQL bytes, and hashes. The runner opens a short-lived connection only after preflight, executes the whole invocation in one DuckDB transaction, and rolls back on every failure. Only typed, known unsupported semantics may delegate to dbt; unclassified compile, SQL, database, or internal errors fail with context instead of being replayed.

The default remains `dbt` until the regression suite and all six ordered gates pass. After #470 completes, #471 is the next strategic investment; #472–#475 remain blocked pending a convincing #471 GO result.

## Technical Context

**Language/Version**: Python >=3.11; SQL/Jinja produced by dbt Core 1.8.8
**Primary Dependencies**: Existing `planalign_orchestrator`, Pydantic v2, dbt Core 1.8.8 programmatic API, dbt DuckDB 1.8.1, DuckDB 1.0.0, Typer/Rich, psutil, pytest 7.4; no new runtime dependency
**Storage**: Explicit per-run DuckDB database; gitignored run-scoped dbt workspaces and immutable compiled bundles under `var/`; existing append-only `run_metadata` startup record plus one append-only terminal execution record keyed by `run_id`
**Testing**: pytest unit, integration, invariant, determinism, parity, and performance harnesses; all behavioral validation uses fresh isolated databases
**Target Platform**: Work-laptop and analytics-server Python environments; sequential dbt execution with `--threads 1` for acceptance
**Project Type**: Python orchestration engine and CLI around an existing dbt/DuckDB simulation
**Performance Goals**: At least 1.8× end-to-end speedup on the approved 60K benchmark, with a 2.0× target; report tiny and development results without weakening correctness gates
**Constraints**: Exact authoritative schema and row-multiset parity; deterministic reruns; actual >=100K completion without memory failure; zero writes to `dbt/simulation.duckdb`; zero unexpected fallbacks; no mutable shared `dbt/target`; no long-lived DuckDB connections
**Scale/Scope**: 150-row tiny fixture, 7,505-row development census, 60,040-row large census, generated 105,070-row memory census, three-year 2025–2027 simulations, and approximately 27 dbt-equivalent invocations per run

## Constitution Check

*GATE: Passed before Phase 0 research. Re-checked after Phase 1 design below.*

| Principle / rule | Design response | Gate |
|---|---|---|
| I. Event sourcing and immutability | Direct execution consumes dbt-produced SQL and must prove exact event/snapshot multiset parity plus deterministic reruns before default enablement. No event semantics change. | PASS |
| II. Modular architecture | Workspace, context/bundle, preflight, transaction execution, delegation, parity, and evidence responsibilities remain separate modules; dependency direction stays inside the runner seam. | PASS |
| III. Test-first development | The six named #470 regressions are written red before implementation changes. Targeted fast tests precede isolated integration and scale gates. | PASS |
| IV. Enterprise transparency | Immutable per-invocation records include mode, reason code, nodes, context digest, rollback outcome, timing, and terminal status. | PASS |
| V. Type-safe configuration and SQL ownership | Engine selection remains Pydantic-validated. dbt remains the sole author of transformation `SELECT` SQL. Materialization identifiers come only from typed manifest relations and one quoting utility. | PASS |
| VI. Performance and scalability | Acceptance includes a real >=100K run with peak RSS evidence; dbt acceptance runs use one thread; default stays opt-in until proof completes. | PASS |
| Database access rules | All paths originate from the explicit runner/database manager; preflight holds no write connection; execution uses one context-managed connection per invocation and closes it before dbt delegation. | PASS |
| dbt development rules | Every dbt operation uses the repository `dbt/` project, explicit `--threads 1`, explicit run-scoped profile, and unique target/log paths. | PASS |

No constitutional violation requires a complexity exception.

## Project Structure

### Documentation (this feature)

```text
specs/119-compiled-execution/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── compiled-bundle.md
│   ├── engine-interface.md
│   └── parity-report.md
├── checklists/
│   └── requirements.md
└── tasks.md                 # regenerated by /speckit-tasks after this plan
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── engine/
│   ├── context.py           # canonical render context and digests
│   ├── workspace.py         # per-run profile, target, log, staging paths
│   ├── plan_cache.py        # dbt manifest reuse and immutable bundle registry
│   ├── preflight.py         # typed invocation parsing and fail-closed planning
│   ├── materialize.py       # frozen node operations; no semantic discovery
│   ├── transaction.py       # invocation BEGIN/COMMIT/ROLLBACK boundary
│   ├── fallback.py          # known-unsupported dbt delegation only
│   └── compiled_runner.py   # DbtRunner-compatible state-machine coordinator
├── tools/
│   └── parity.py            # schema and row-multiset comparison
├── run_execution_metadata.py
├── run_metadata.py
├── run_summary.py
└── factory.py

planalign_cli/
├── commands/
│   ├── simulate.py
│   └── parity.py
└── main.py

scripts/perf_profile/
├── make_large_census.py
├── profile_config.py
├── run_matrix.py
└── build_report.py

tests/
├── fixtures/
│   ├── invariant_census.csv
│   ├── invariant_config.yaml
│   └── compiled_execution.py
├── unit/engine/
│   ├── test_workspace.py
│   ├── test_context.py
│   ├── test_plan_cache.py
│   ├── test_preflight.py
│   ├── test_materialize.py
│   ├── test_transaction.py
│   └── test_compiled_runner.py
├── integration/
│   ├── test_engine_fallback_smoke.py
│   ├── test_engine_isolation.py
│   ├── test_engine_parity.py
│   ├── test_multi_year_invariants.py
│   └── test_determinism.py
└── invariants/
    └── comparison.py
```

**Structure Decision**: Keep compiled execution behind the existing `DbtRunner.execute_command` seam. Add small engine-internal modules rather than widening pipeline-stage responsibilities. Reuse the existing invariant and performance fixtures, extending their typed artifacts instead of creating a second validation framework.

## Phase 0: Research Decisions

Research is complete in [research.md](research.md). The decisive changes from the prototype are:

1. Never read or write shared `dbt/target`; every dbt invocation receives explicit run-scoped profile, target, and log paths.
2. Separate mutable dbt staging/work artifacts from atomically published immutable bundles.
3. Reuse dbt's manifest and selector implementation; delete the hand-written selector matcher.
4. Treat relation state and dbt volatile render values as part of the render context so `is_incremental()`, `invocation_id`, and similar values cannot become stale.
5. Complete semantic preflight before opening a write transaction.
6. Execute one invocation per DuckDB transaction; roll back before any typed late delegation and never replay arbitrary execution failures.
7. Compare schemas plus row multisets with `EXCEPT ALL`, not set equality.
8. Record final execution evidence in a separate append-only terminal record because the existing `run_metadata` row is written at run start.

## Phase 1: Design

### Execution Lifecycle

```text
DbtRunner-compatible request
  -> canonical InvocationRequest
  -> run-scoped manifest / dbt selector resolution
  -> render-context + relation-state fingerprint
  -> compile in unique staging target
  -> validate and atomically publish immutable bundle
  -> complete preflight
       -> KnownUnsupported: delegate via isolated dbt target
       -> Supported InvocationPlan: open explicit DuckDB connection
            -> apply supported connection hooks
            -> BEGIN
            -> execute frozen node operations in dbt order
            -> COMMIT and close
            -> on error: ROLLBACK and close
                 -> typed KnownUnsupported only: isolated delegation
                 -> every other error: contextual failure
  -> immutable InvocationExecutionRecord
  -> append-only terminal run evidence
```

### Run Workspace and Explicit Targeting

- A `RunArtifactWorkspace` is created when `CompiledRunner` is constructed. Its root is `var/compiled_execution/<run_id>/` unless an existing run archive supplies a scoped artifact directory.
- The workspace writes a run-specific `profiles.yml` whose selected DuckDB output contains the resolved absolute `database_path`; no process-global `DATABASE_PATH` mutation is used.
- Every programmatic dbt call receives `--project-dir`, the run profile via `--profiles-dir`, a unique `--target-path`, a unique `--log-path`, and `--threads 1`.
- Mutable compile/delegation targets are unique siblings. Published bundles live under `bundles/<render_context_sha256>/` and are never supplied to dbt as a target.
- Failed staging targets may be retained for diagnostics; successful mutable targets follow the existing runtime-artifact retention policy. Everything remains gitignored and must not include census rows or secrets.

### Context Identity and Bundle Publication

- The canonical render-context digest covers project content, packages/lock/selectors, dbt and adapter versions, profile/target/schema settings, the absolute database destination, canonical vars, command/select/exclude/full-refresh flags, selected node IDs/order, render-relevant environment inputs, dbt volatile render identity, and the selected relations' existence/type/schema fingerprint.
- A run-level parsed manifest may be reused while its static project-context digest is unchanged. Executable SQL is reused only for an identical full render context.
- Because `is_incremental()` observes database state, each committed invocation advances a relation-state epoch. Reuse after a write requires an identical observed relation-state fingerprint; otherwise a new bundle is compiled.
- Compilation writes to a unique staging target. Publication requires a valid manifest, compiled SQL for every executable node, frozen node metadata, and matching content hashes. An atomic same-filesystem rename publishes the bundle. Existing published content is reused only after hash verification.
- SQL bytes are loaded into the frozen `InvocationPlan` and hash-checked against the bundle. Execution never re-reads a mutable target.

### Complete Invocation Preflight

- Parse the entire dbt-equivalent request with a typed, fail-closed option model. Unknown commands, flags, selector methods, or resource semantics become a typed `KnownUnsupportedSemantics` result; no token is silently ignored.
- Resolve selection and dependency order from the dbt 1.8.8 manifest/graph selector APIs. A zero-node result never becomes a compiled success; it delegates to dbt so dbt owns the no-node policy.
- Freeze all selected model metadata: relation, materialization, incremental strategy, unique key, `on_schema_change`, compiled SQL, pre-hooks, post-hooks, and dependency order.
- Classify project and model hooks before execution. Pure `log()` expressions are supported lifecycle records with no SQL statement. Supported PRAGMA/SET hooks and the repository's guarded-delete hook idiom are rendered and frozen. Any other side effect or Jinja construct delegates before writes.
- Inspect current target relation metadata read-only and precompute every DDL/DML operation, column projection, schema-change decision, and incremental branch. Missing artifacts or unclassified conditions fail; known unsupported semantics delegate.
- Verify the workspace profile resolves to the runner's explicit database and the bundle/context hashes still match immediately before returning a supported plan.

### Transaction and Fallback Policy

- Preflight does not hold a write connection. Direct execution obtains a context-managed connection, applies connection-local settings, starts `BEGIN`, executes every frozen operation, commits, and closes.
- Any exception rolls back the invocation before the connection is released. The execution record includes whether rollback was attempted and completed.
- `KnownUnsupportedSemantics` discovered during normal preflight delegates without opening a transaction. A defensive typed late occurrence rolls back first, records an unexpected late-preflight defect, then may delegate. The production acceptance matrix must contain zero such occurrences.
- Compile errors, SQL errors, lock errors, catalog errors, integrity errors, hash mismatches, and internal errors do not delegate. They fail with run, year, stage, invocation, node, lifecycle phase, and bounded statement context.
- Each dbt delegation uses a fresh mutable target within the same run workspace and the same explicit database profile. It cannot mutate a published bundle.

### Materialization Boundary

- dbt remains the sole author of transformation SQL. The engine supplies only the surrounding adapter-equivalent operations for the repository's supported `view`, `table`, `incremental append`, and `incremental delete+insert` shapes.
- Relation identifiers originate from typed manifest fields and pass through one quoting helper. No model/table identifier comes from unvalidated command text.
- Ephemeral nodes remain compile-time dependencies and are not separately materialized.
- Schema-change behavior is decided during preflight. A required behavior not proven equivalent to dbt delegates before writes.
- Node pre-hooks and post-hooks execute in dbt order inside the invocation transaction. Project connection hooks execute before `BEGIN`; informational end hooks record after commit.

### Parity, Provenance, and Evidence

- Parity first compares ordered schema metadata, including exempt audit-column presence and types. Value comparison excludes only the documented timestamp values and uses symmetric `EXCEPT ALL`.
- Multiplicity diagnostics group projected rows with side counters and report baseline count, candidate count, and delta for bounded samples. This catches equal-total-count duplicate swaps that ordinary `EXCEPT` misses.
- Keep `run_metadata` as the append-only startup/drift record. Add an append-only terminal execution record keyed by the authoritative `run_id`; never update the startup row.
- Per-invocation records capture direct/delegated mode, stable reason, context/bundle digest, planned/attempted/completed nodes, target identity, timing, rollback, outcome, and bounded error context.
- Extend the performance artifact schema with campaign ID, engine, configuration/census fingerprints, fallback totals, peak process-tree RSS, and unique output paths. Paired baseline/candidate repetitions must not overwrite one another.

## Ordered Delivery and Acceptance

Implementation follows test-first slices; the default flip is excluded from every earlier slice.

1. Write the six #470 regression tests and confirm they fail for the expected prototype defects.
2. Implement isolated workspaces, explicit profiles, canonical contexts, immutable bundle publication, and corruption tests.
3. Implement dbt-backed selector planning and complete preflight, including log-only hooks and zero-node protection.
4. Implement transaction execution, rollback, narrow typed delegation, and contextual failure records.
5. Implement exact multiset parity, append-only terminal evidence, and engine-aware performance/memory artifacts.
6. Prove the gates strictly in this order:
   1. Tiny isolated exact parity.
   2. Multi-year invariants, determinism, and identical-input rerun parity.
   3. Development and 60K exact parity.
   4. Actual >=100K completion with peak RSS evidence.
   5. Paired tiny/development/60K performance, including compilation, preflight, and delegation costs.
   6. Zero unexpected fallbacks across the supported matrix.
7. Only after gates 1–6 pass, change the compiled default and rerun tiny parity plus the explicit `dbt` compatibility smoke.
8. Close #470, then begin #471. Do not start #472–#475 unless #471 demonstrates a convincing native-kernel speedup and receives GO.

## Post-Design Constitution Re-check

The Phase 1 design still passes every pre-research gate. In particular, it removes the prototype's long-lived connection, makes rollback and event parity mandatory, retains dbt-authored transformations, requires the real 100K proof, and prevents default enablement from preceding evidence. No complexity exception is introduced.
