# Phase 0 Research: State Pipeline Redesign

## Decision 1: Execute Studio/API attempts directly in immutable run databases

**Decision**: Before launching a Studio/API-managed attempt, create one exclusive `runs/<run_id>/` directory and pass its previously nonexistent `simulation.duckdb` path to the CLI. The run directory owns the database, live WAL, configuration, log, metadata, provenance, and optional exports. A failed or cancelled run retains its partial database in place. Direct CLI runs remain caller-managed through their explicit/default database path.

**Rationale**: Running against `scenarios/<scenario>/simulation.duckdb` and copying after success mutates the database currently powering reads, exposes partial state, and cannot preserve failed output without another copy. A run-local DB provides isolation from the first write and makes rollback equivalent to not changing the published pointer.

**Alternatives considered**:

- Run in the scenario database and copy on success: rejected because it mutates current results during execution and creates lock/copy failure windows.
- Symlink the scenario DB to a run DB: rejected because cleanup, containment, and Windows behavior become fragile.
- Change every direct CLI call to create workspace run directories: rejected as scope expansion; the clarified storage contract applies to Studio/API orchestration, while explicit CLI destinations remain valid isolated databases.

## Decision 2: Separate newest attempt state from the published result

**Decision**: Keep `scenario.json.status` and `last_run_id` as newest-attempt state. Add a versioned scenario-local `current_result.json` containing the successful `run_id` and `promoted_at`. Validate the run ID as a canonical UUID, derive the run DB path rather than storing an arbitrary path, and publish the pointer with a same-directory temporary file, flush/fsync, and `os.replace`.

**Rationale**: Attempt status can be running or failed while the scenario still has valid results. A small atomic pointer provides a single publication commit without changing the public Scenario schema or scanning/timestamp-ordering all run directories on every request.

**Alternatives considered**:

- Add `latest_successful_run_id` only to `scenario.json`: rejected because it couples attempt and publication state in a currently non-atomic whole-file write.
- Scan for the newest completed metadata on every read: rejected because it is non-atomic, slower, and ambiguous under corrupt metadata or timestamp ties.
- Point directly to a path: rejected because path injection and relocation risks are unnecessary; a validated UUID is sufficient.

## Decision 3: Promote only after authoritative outputs are durable

**Decision**: The success order is: simulation exits successfully and DB connections close; completed run metadata and provenance are atomically finalized; the DB is validated as present/readable; non-authoritative exports are attempted; the current-result pointer is atomically replaced; then scenario/registry/telemetry status is finalized. Failure/cancellation writes terminal artifacts in its own run directory and never changes the pointer. Automatic completion-time pruning is removed; deletion is an explicit maintenance operation.

**Rationale**: Current code marks a scenario completed before archive finalization. Reordering makes the pointer the authoritative commit and prevents readers from observing an incomplete result. Automatic pruning conflicts with the requirement that reruns leave prior DBs/archives untouched and can delete the selected success behind newer failures.

**Alternatives considered**:

- Promote before metadata/provenance: rejected because the run would be readable before it is auditable.
- Retain `max_runs` pruning and pin only the current run: rejected for this feature because prior-run immutability is explicit; retention policy can be a later, user-authorized maintenance feature.

## Decision 4: Centralize latest-success reads and use response headers for warnings

**Decision**: Extend `DatabasePathResolver` to resolve `current_result.json`, return the selected `run_id`, and attach active-attempt context. While a scenario is queued/running, DB-backed result reads continue using the selected successful DB. A shared API response layer adds `X-PlanAlign-Run-Warning` and `X-PlanAlign-Active-Run-Id` to every scenario-scoped read, including status/telemetry reads; result-bearing reads also add `X-PlanAlign-Result-Run-Id`. Expose those headers through CORS; the Studio API client emits one deduplicated global banner. Multi-scenario reads aggregate active contexts in a deterministic header value. Non-scenario health/version endpoints are outside this contract.

**Rationale**: The resolver already centralizes database selection for results, analytics, comparison, timeline, vesting, winners/losers, config diff, and NDT. Headers preserve existing response schemas. Reads must be authorized by a published result rather than `scenario.status == completed`, and must never rewrite a running/failed status merely because an older successful DB exists.

**Alternatives considered**:

- Add warning fields to every response model: rejected because it expands many public schemas.
- Return the active partial DB with a warning: rejected because it violates latest-success consistency.
- Fall back silently when a pointer exists but is invalid: rejected; pointer corruption is an integrity error and must fail closed.

## Decision 5: Preserve a bounded legacy read path

**Decision**: If no pointer has ever been published, resolve the legacy scenario DB, then existing workspace/project fallbacks. A malformed pointer, missing completed metadata, or missing pointed-to DB is an integrity failure rather than permission to silently choose another run. Result metadata and year ranges come from the resolved run, not from a potentially edited current scenario config.

**Rationale**: Existing workspaces remain readable while all new successful runs use the atomic contract. Failing closed after publication prevents invisible rollback to stale data.

## Decision 6: Give event assembly and publication explicit relations

**Decision**: Introduce `int_current_year_events` as the one union/sequence relation over all active SQL event candidates. Make `fct_yearly_events` a thin incremental publisher of that relation and remove it from STATE_ACCUMULATION. Event generation selects candidates plus publication together; dbt `ref` edges order them. Retain the existing partition-scoped replacement behavior and public event schema.

**Rationale**: `fct_yearly_events` is currently tagged into EVENT_GENERATION and explicitly selected again at the start of STATE_ACCUMULATION. A named assembly boundary makes candidate completeness and single publication manifest-verifiable without changing event semantics.

**Alternatives considered**:

- Keep the union embedded in the fact: rejected because graph audits cannot distinguish candidates from publication cleanly.
- Split candidates and publication into separate permanent commands: rejected as the target because it adds a boundary and stale-candidate risk; it is acceptable temporarily during migration.
- Restore or clean up Polars paths: rejected; SQL is the active supported pipeline and unrelated remnants are out of scope.

## Decision 7: Introduce a narrowly scoped workforce accumulator

**Decision**: Add incremental `int_workforce_state_accumulator`, keyed by `(scenario_id, plan_design_id, employee_id, simulation_year)`. It reads its own year N-1 rows plus year-N workforce events and owns identity/scope, birth/hire/termination facts, employment and detailed status, compensation/proration, level, age/tenure/service, bands, and only the scheduling fields required for carry-forward. It excludes enrollment, deferral, eligibility, contributions, match, and account balances.

**Rationale**: The existing `int_employee_state_by_year` is orphaned, hard-codes `default/main`, and mixes benefit state. The scratch snapshot is full-refresh and has only two production consumers. A new shadow relation avoids declaring either flawed implementation authoritative before full-scale proof.

**Alternatives considered**:

- Promote `int_employee_state_by_year`: rejected by the specification and its current scope/domain defects.
- Build an all-purpose state table: rejected because it erases domain ownership and creates new coupling.
- Rewrite all consumers simultaneously: rejected because it makes divergence hard to localize and violates phased parity.

## Decision 8: Represent prior-year dependencies through an orchestrator projection

**Decision**: Before foundation/event generation for year N, rebuild a disposable `workforce_state_projection` from canonical rows strictly earlier than N, analogous to `enrollment_decision_projection`. Declare it as an orchestrator source and migrate the prior-active/summary/by-level helpers away from dynamic `adapter.get_relation` reads of the snapshot fact.

**Rationale**: A static `ref` from current-year event candidates to a self-accumulator creates a manifest cycle even when filtered to N-1. A disposable projection preserves the temporal cut while making the exceptional boundary explicit and testable.

**Alternatives considered**:

- Keep hidden adapter lookups: rejected because current ordering remains absent from the graph.
- Directly `ref` the snapshot or accumulator: rejected because the current-year graph becomes cyclic.
- Generate one dbt node per year: rejected as impractical and inconsistent with the runtime workflow.

## Decision 9: Migrate benefit consumers and compose the final snapshot

**Decision**: After shadow parity, migrate employer eligibility, employee contributions, employer core, and match calculations one at a time to workforce plus the appropriate enrollment/deferral/contribution domain relations. Then rebuild `fct_workforce_snapshot` as a thin composition and remove the orphan and scratch relations only after the manifest confirms zero consumers. Update the separate calibration workflow deliberately.

**Rationale**: Contributions/core currently replay hire, termination, and proration logic, while core/match depend on the scratch relation. Incremental migration localizes parity failures and ensures the public snapshot stops replaying workforce events.

## Decision 10: Make graph ownership and execution contracts executable

**Decision**: Use distinct ownership tags for event candidates, event publication, domain state, benefit calculation, and snapshot publication. Remove contribution/match from inherited event ownership and eliminate manual excludes. Manifest/workflow tests assert candidate ancestry, exactly-once publication, state dependency closure, one command/no full-refresh, allowed temporal escape hatches, unique keys, complete candidate coverage, and that every staged node has a consumer or checked audit-sink designation.

**Rationale**: Folder-inherited tags are additive today, so state models can still carry event ownership. Schedule strings alone also cannot prove which models a tag actually executed; node execution is checked from dbt `run_results.json`.

**Alternatives considered**:

- Continue manual exclusions: rejected because stage ownership remains implicit.
- Test only workflow model lists: rejected because indirect tag selection can execute hidden nodes.
- Ban raw text patterns without compiling production vars: rejected because inactive compatibility branches would create false failures.

## Decision 11: Freeze one A+B baseline and harden parity before migration

**Decision**: Regenerate a clean baseline from revision `c6ad648` or a verified equivalent and freeze its baseline ID, code/dirty-tree, normalized config, census, seed, construction, DB, horizon, and schedule fingerprints. Commit only an aggregate `baseline-characterization.json`; keep the PII-bearing DB/input evidence ignored. Extend validation to compare exact relation schemas before bidirectional `EXCEPT ALL`, fail one-sided absence, record both-absent marts explicitly, and preserve duplicate multiplicity. Add a frozen-baseline mode rather than using the existing moving-HEAD comparison after every phase.

**Rationale**: The existing helper compares only shared columns and can pass schema loss or one-sided absence. Existing local A+B evidence was collected while the patch was uncommitted, so its reported revision is not an authoritative baseline identity. A baseline that advances with each phase cannot define behavioral preservation.

**Alternatives considered**:

- Commit a golden DuckDB: rejected because it is PII-bearing, binary, and unreviewable.
- Compare only logical hashes: rejected because exact SQL multiset differences are more diagnosable and avoid hash/version ambiguity.
- Rebuild baseline from current HEAD for each phase: rejected because expected behavior would drift.

## Decision 12: Use an explicit relation-column exclusion contract

**Decision**: Check in `contracts/parity-exclusions.yaml` with exact relation, column, and reason entries. Unknown/duplicate entries fail. A listed column is excluded only when its relation is built; an unlisted difference always fails. The mart inventory comes from `dbt ls --select marts --resource-type model` and every model receives a compared or explicitly-not-built status.

**Rationale**: The existing global `created_at`/`snapshot_created_at` exclusion silently ignores same-named columns anywhere. Relation ownership makes each exception reviewable.

**Alternatives considered**:

- Exclude by column name or timestamp type: rejected because it masks regressions.
- Compare only the three currently built facts: rejected because the contract must account for every mart selected by the project path, including intentionally absent workflow-specific marts.

## Decision 13: Gate every phase at production scale and reserve replicated performance decisions for the final phase

**Decision**: Every migration phase runs one complete 60,040-employee 2025–2029 candidate against the same frozen DB and records exact parity, event counts, duplicates, schema, shared/prior-run fingerprints, invocation schedule, node execution, and directional RSS. The baseline and final consolidated pipeline each receive at least three warm repetitions for both reference and Studio workloads; their medians decide the 10% RSS gate. Existing determinism, multi-year, stale-rerun, failed-stage, Feature 107, and Feature 112 suites remain required.

**Rationale**: Full-scale semantic parity is required after every change, while replicated RSS campaigns at every intermediate step would add large cost without improving the final acceptance decision. Per-phase measurements still expose spikes early.

**Alternatives considered**:

- Use the small dev census as a migration gate: rejected by the accepted Tier C evidence and the feature specification.
- Use one final parity run only: rejected because it cannot identify which migration introduced drift.
- Decide final RSS from one run: rejected because workstation measurements need warm repetition and median comparison.

## Decision 14: Treat managed run isolation as the first user-facing increment

**Decision**: Make fresh run databases, latest-success reads, active-run warnings, failed partial-run retention, and atomic success promotion the first P1 user story rather than hiding them in cross-cutting pipeline requirements.

**Rationale**: These behaviors are independently demonstrable to operators, materially affect trust in reruns, and must exist before pipeline changes can be validated safely. They form a coherent deliverable even if event/state normalization stops later.

**Alternatives considered**:

- Keep run isolation only as foundational plumbing: rejected because it obscures user value and makes its independent acceptance/latency gates easy to miss.
- Fold it into event publication: rejected because safe rerun behavior is useful and testable without changing any dbt model.

## Decision 15: Preserve scenario-read latency under result indirection

**Decision**: Measure representative scenario-scoped reads separately while idle and while serving the latest success during a newer active run; require at least 95% to finish within two seconds in both conditions.

**Rationale**: Pointer validation and warning aggregation add work to every scenario read. Functional correctness alone would allow a user-visible dashboard regression that violates the existing product performance target.

## Decision 16: Bound calibration and make domain protections explicit

**Decision**: Calibration must use the normalized shared graph wherever it selects affected relations, contain no removed model, and preserve its output/failure behavior. It does not gain the managed-simulation current-result lifecycle. Add direct contracts for the earlier-year-only, non-authoritative enrollment projection and for separate enrollment/deferral authoritative state.

**Rationale**: Calibration has a real workflow dependency on the models being removed, but expanding run publication to calibration would be a separate product feature. Explicit FR-005/FR-010 tests keep two important domain boundaries from being inferred only through broad parity.
