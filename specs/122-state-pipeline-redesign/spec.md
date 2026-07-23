# Feature Specification: Normalize the Event & Workforce-State Pipeline (STATE_ACCUMULATION Redesign)

**Feature Branch**: `122-state-pipeline-redesign`
**Created**: 2026-07-22
**Status**: Draft
**Input**: GitHub issue [#482](https://github.com/crzyc98/planwise_navigator/issues/482) — follow-up spun out of Feature 121 (#478, PR #481). Full design: `specs/121-reduce-dbt-invocations/state-pipeline-redesign.md`.

## Overview

Feature 121 reduced production-path pipeline invocations (38 → 30) while preserving byte-identical outputs, but stopped short of collapsing the STATE_ACCUMULATION stage because that stage carries **load-bearing behavior that only looks redundant locally**. Investigation ("Tier C") proved the current results depend on persisted intermediate relations and command boundaries that the dependency graph does not fully describe.

This feature normalizes the event and workforce-state pipeline so that its correctness is expressed by the dependency graph itself rather than by orchestration ordering, hidden dynamic lookups, and command-level refresh exceptions. The durable value is **code health and correctness**: publish each immutable fact exactly once, keep one authoritative relation per state domain, remove orphaned and triplicated computation, and make dependency order machine-verifiable. Reducing the number of pipeline invocations is a *consequence* of this cleanup, not its motivation.

Every change is gated by strict, bidirectional parity with the accepted Feature 121 (A+B) baseline at full production scale (60,040 employees, 2025–2029). No public schema, event semantics, deterministic identifier, event sequence, or duplicate multiplicity may change.

## Clarifications

### Session 2026-07-22

- Q: Does “published exactly once per scenario/plan/year” apply per simulation run attempt? → A: Fresh run database, then rebuild once.
- Q: How should Feature 122 treat Polars? → A: SQL-only; legacy remnants untouched.
- Q: How should a rerun isolate its database? → A: Fresh run-specific database.
- Q: Which run should power scenario-level Studio and API results? → A: Latest success, with running warning.
- Q: How should permitted audit/timestamp differences be defined? → A: Checked-in relation-column allowlist.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe reruns preserve the latest successful results (Priority: P1)

An operator rerunning a scenario needs the new attempt to start from a completely fresh, isolated database without disturbing any prior attempt. While the new attempt is running, every scenario-scoped read must clearly warn that work is in progress, and any result-bearing read must continue using the latest successful result. A failure must leave that successful result selected; a success must replace it atomically.

**Why this priority**: This is a user-facing safety and trust boundary. Without it, a rerun can expose partial results, destroy the only usable result, or make a failed attempt look current. It also provides the isolated execution foundation required for trustworthy pipeline parity validation.

**Independent Test**: Create a successful scenario run, record fingerprints for its database/archive and the shared development database, then start a second run. Verify all scenario reads carry the in-progress warning, result reads remain on the first run within the read-latency target, injected failure retains the second run's partial database without changing the selected result, and a subsequent success atomically switches selection to a third fresh database. Repeat through the managed batch path.

**Acceptance Scenarios**:

1. **Given** any prior run history, **When** a managed single-scenario or batch attempt starts, **Then** it receives a new empty run-specific database and no prior run database, archive, or shared development database is modified.
2. **Given** a latest successful run and a newer run in progress, **When** any scenario-scoped read is requested, **Then** the response contains an explicit in-progress warning; result-bearing reads return the latest successful run and identify both the active and served run where applicable.
3. **Given** an active run, **When** it fails or is cancelled, **Then** its partial database remains associated with failed/cancelled status and the latest-successful selection remains unchanged.
4. **Given** an active run that completes successfully, **When** its authoritative artifacts are durable, **Then** readers switch atomically from the prior successful run to the new successful run and never observe a partial publication.
5. **Given** a representative scenario workload, **When** scenario-scoped reads are measured both with no active run and while a newer run is in progress, **Then** at least 95% complete within two seconds.

---

### User Story 2 - Immutable facts are published exactly once per year (Priority: P2)

An engineer maintaining the simulation pipeline needs each immutable fact table to be produced exactly once per scenario/plan/year, so there is a single source of truth per year and no duplicated or wasted computation. Today `fct_yearly_events` is built twice per year (once during event generation, again at the start of state accumulation), and workforce state is replayed multiple times.

**Why this priority**: This is the foundational pipeline-correctness win after safe run isolation exists. Eliminating duplicate publication removes a whole class of "which build won" ambiguity and is a prerequisite for every later pipeline simplification. It can be delivered while keeping the existing command boundaries.

**Independent Test**: Run a full multi-year simulation on an isolated database. Confirm `fct_yearly_events` and `fct_workforce_snapshot` are each written exactly once per scenario/plan/year (no second build of the event fact inside state accumulation), and confirm every `fct_*`/`dim_*` mart is bidirectionally `EXCEPT ALL`-identical to the accepted A+B baseline after excluding only columns named in the checked-in relation-and-column allowlist.

**Acceptance Scenarios**:

1. **Given** a normalized pipeline, **When** a simulation year runs, **Then** `fct_yearly_events` for that scenario/plan/year is published exactly once and no later stage rebuilds it.
2. **Given** a normalized pipeline, **When** a simulation year runs, **Then** `fct_workforce_snapshot` for that scenario/plan/year is published exactly once.
3. **Given** a full 2025–2029 run at 60,040-employee scale, **When** outputs are compared to the accepted A+B baseline, **Then** all marts match bidirectionally after excluding only columns named in the checked-in relation-and-column allowlist, and event counts match by scenario, plan, year, and event type.
4. **Given** the active SQL event-generation pipeline, **When** current-year event candidates are generated, **Then** no candidate reads the current year's `fct_yearly_events`.

---

### User Story 3 - One authoritative, correctly-scoped workforce-state relation (Priority: P3)

An engineer needs workforce state (employment status, dates, compensation, level, age, tenure, proration) computed in exactly one authoritative relation, correctly scoped by scenario and plan, instead of the current triplication (~1,850 lines across three models) and an orphaned model that hard-codes `default`/`main` and has no consumers.

**Why this priority**: Triplicated, drift-prone workforce logic is the largest code-health liability in the stage and the root cause of the fragile command boundaries. Consolidating it (via a proven shadow accumulator) is the highest-value maintainability improvement, but it depends on facts being published once (P1) first.

**Independent Test**: Build the new shadow workforce-state accumulator alongside the existing pipeline and compare every column, for every simulation year, against the corresponding accepted-snapshot columns. Migrate employer-core and match consumers onto it, then confirm the removed models (the orphaned legacy state model and the current-year scratch snapshot) have no remaining consumers and that parity still holds.

**Acceptance Scenarios**:

1. **Given** a shadow workforce-state accumulator scoped by scenario/plan/employee/year, **When** year N is computed from year N−1 state plus year-N workforce events, **Then** every state column matches the accepted A+B snapshot columns for every simulation year before any consumer is migrated.
2. **Given** the shadow accumulator has passed full-scale parity, **When** employer-core and match calculations are re-pointed to it, **Then** contribution and match outputs remain bidirectionally identical to the baseline.
3. **Given** all consumers are migrated, **When** the orphaned legacy workforce-state model and the current-year scratch snapshot are removed, **Then** no production model references them and full parity is preserved.
4. **Given** the canonical accumulator, **When** its schema is inspected, **Then** it contains only workforce fields (no benefit/account fields) and no hard-coded scenario or plan identifiers.
5. **Given** the enrollment decision projection, **When** a decision year is prepared, **Then** the projection contains only earlier-year inputs, remains disposable/reconstructible, and never becomes authoritative state.
6. **Given** the normalized state domains, **When** their schemas and consumers are inspected, **Then** enrollment and deferral remain separate authoritative accumulators and no all-purpose state relation is introduced.

---

### User Story 4 - Dependency order is machine-verifiable, with clean stage ownership (Priority: P4)

An engineer needs the pipeline's execution order to be expressed entirely by declared model dependencies, so that a future change cannot silently break sequencing. Today some prior-year reads use dynamic relation lookup to bypass graph discovery, stage tags do not express ownership (contribution/match models carry event-generation tags and must be manually excluded), and staged models exist with no consumers.

**Why this priority**: These guardrails are what make the redesign safe and keep it safe. They are lower priority as a *delivered* slice because their value is realized through P1/P2, but the graph-contract tests should exist early to catch regressions during the migration.

**Independent Test**: Add graph-contract tests asserting: no current-year event candidate reads current-year facts; each immutable fact is published once per year; every staged production model has a downstream consumer or is explicitly documented as an audit output; and stage ownership tags are clean. Convert hidden current-year reads and ordering comments to declared dependency edges, and confirm the tests pass on the normalized graph.

**Acceptance Scenarios**:

1. **Given** graph-contract tests, **When** the dependency graph is analyzed, **Then** every current-year ordering relationship is represented by a declared dependency edge (no orchestration-only sequencing, no dynamic lookup used solely to hide a cycle).
2. **Given** cleaned stage ownership, **When** stage selections are evaluated, **Then** event-candidate, event-publication, domain-state, benefit-calculation, and snapshot-publication models each belong to distinct, correctly-tagged stages with no manual exclusions required.
3. **Given** the normalized graph, **When** the staged-model audit runs, **Then** every production stage model either has a consumer or is explicitly documented as an audit output.
4. **Given** prior-year temporal reads, **When** they are inspected, **Then** they occur only through self-referencing accumulators or explicit, documented orchestrator-built projections that read strictly earlier years.
5. **Given** the calibration workflow, **When** the normalized graph is inspected and calibration is run, **Then** it contains no removed model, satisfies dependency closure for every affected shared relation, and preserves accepted calibration outputs and failure behavior.

---

### User Story 5 - STATE_ACCUMULATION runs in one invocation with no refresh exception (Priority: P5)

An operator running simulations needs the STATE_ACCUMULATION stage to execute as a single pipeline invocation per year, with no command-level full-refresh special case, so the execution schedule is simpler, dependency-ordered, and free of hidden transaction semantics — with a modest reduction in launch overhead as a bonus.

**Why this priority**: This is the *outcome* of the preceding cleanup, explicitly the least important goal ("invocation reduction is secondary"). It can only be attempted after the graph is normalized (P1–P3), and must not be used as the mechanism to force the redesign.

**Independent Test**: On the normalized pipeline, run STATE_ACCUMULATION and confirm it completes in exactly one invocation per simulation year with no command-level full-refresh flag, that per-model/stage/year failure attribution is still correct, and that full-scale parity, determinism, stale-rerun, failed-stage, and partial-failure-status suites remain green.

**Acceptance Scenarios**:

1. **Given** the normalized DAG, **When** STATE_ACCUMULATION runs for a year, **Then** it executes in exactly one pipeline invocation and no selected model requires a command-level full-refresh.
2. **Given** a deliberately failing model, **When** the stage runs, **Then** failure is still attributed to the correct model, stage, and year, and partially-present outputs remain associated with failed status.
3. **Given** the consolidated schedule, **When** wall time, CPU, model time, invocation count, and peak memory are measured on both the reference and 60,040-employee Studio workloads, **Then** peak memory is within 10% of the accepted A+B baseline and the before/after schedule and evidence are published.
4. **Given** the final execution schedule, **When** total invocations are reported, **Then** the observed total is recorded as evidence and no fixed whole-run invocation count is used as an acceptance threshold.

---

### Edge Cases

- **First simulation year (no prior year):** the workforce-state accumulator's year N−1 read must resolve correctly for the initial year without a prior-year relation, matching current behavior.
- **Shadow accumulator divergence:** if any state column diverges from the accepted baseline for any year, consumer migration is blocked and the old logic is retained until parity is achieved.
- **Deprecated Polars remnants:** legacy Polars configuration, models, and compatibility artifacts are not part of the active pipeline; this feature must neither restore Polars support nor expand into unrelated cleanup of those remnants.
- **Post-termination integrity (Feature 112):** no employee may receive a forbidden event after their effective termination boundary through any reordering.
- **Census enrollment reconstruction (Feature 107):** census enrollment state must remain reconstructible from census plus immutable facts; the disposable `enrollment_decision_projection` must never become authoritative state.
- **Partial failure / fresh rerun:** a failed or interrupted run retains its run-specific database with outputs clearly associated with failed status. A rerun creates a new empty run-specific database, leaves every prior run database and archive untouched, rebuilds every year from scratch, and publishes each scenario/plan/year partition exactly once within the new run attempt.
- **Reads during execution:** while a new run is in progress, scenario-level API reads return the latest successful run's results with an explicit in-progress warning. A successful run becomes current atomically; a failed or interrupted run leaves the latest-successful selection unchanged.
- **Read-latency regression:** selecting the latest successful run and adding active-run warning context must not push representative scenario reads beyond the two-second 95th-percentile target, whether a run is active or idle.
- **Calibration workflow:** calibration must adopt the normalized shared graph wherever it uses affected relations and must stop selecting removed relations, while its existing output and failure behavior remain compatible. The run-result publication and warning contract applies to managed simulation attempts, not calibration attempts.
- **Unexpected parity difference:** only audit/timestamp columns named in the checked-in relation-and-column allowlist may be excluded from parity comparison; every difference in an unlisted column fails the parity gate.
- **Peak memory regression:** if consolidating the stage into one invocation pushes peak memory above 10% over baseline, the consolidation does not meet its gate.
- **Dev-census false positive:** parity on the small dev census is insufficient; only full 60,040-employee, 2025–2029 parity is authoritative.
- **Apparent redundancy that is load-bearing:** each removed relation or command boundary must be treated as a hypothesis until full-scale parity proves it can be removed.

## Requirements *(mandatory)*

### Functional Requirements

**Event publication**

- **FR-001**: Within each newly created run-specific database, the pipeline MUST publish `fct_yearly_events` exactly once per scenario/plan/year; no later stage may rebuild it.
- **FR-002**: Current-year event candidate models in the active SQL pipeline MUST NOT read the current year's `fct_yearly_events`.
- **FR-003**: A single current-year event relation MUST union and sequence every event candidate before publication.
- **FR-004**: The redesign MUST target the active SQL event-generation pipeline and MUST NOT restore Polars support or require cleanup of unrelated deprecated Polars remnants.
- **FR-005**: The `enrollment_decision_projection` MUST remain a disposable prior-state boundary, rebuilt before event generation and reading only years earlier than the decision year; it MUST never become authoritative state.

**Domain state**

- **FR-006**: The system MUST introduce a canonical workforce-state accumulator scoped by scenario, plan, employee, and simulation year, computing year N from year N−1 state plus year-N workforce events.
- **FR-007**: The canonical workforce-state accumulator MUST own only workforce fields (employment status, dates, compensation, level, age, tenure, proration) and MUST NOT include benefit/account fields.
- **FR-008**: The canonical workforce-state accumulator MUST contain no hard-coded scenario or plan identifiers.
- **FR-009**: The system MUST build the workforce-state accumulator first as a shadow model and prove full-scale, per-year, per-column parity with accepted outputs before migrating any consumer.
- **FR-010**: Enrollment-state and deferral-state MUST remain in their existing domain accumulators; the system MUST NOT create a new all-purpose state table.
- **FR-011**: Employer-core, employee-contribution, and match calculations MUST consume the workforce, enrollment, and deferral accumulators directly (not the current-year scratch snapshot).
- **FR-012**: `fct_workforce_snapshot` MUST be rebuilt as a composition of workforce, enrollment, deferral, contribution, and match state — without replaying workforce events again — and MUST be published exactly once per scenario/plan/year.
- **FR-013**: The orphaned legacy workforce-state model and the current-year scratch snapshot MUST be removed only after no production consumer depends on them and full parity holds.

**Graph and stage ownership**

- **FR-014**: All current-year execution ordering MUST be represented by declared model dependency edges; ordering MUST NOT rely on orchestration-only sequencing, ordering comments, or dynamic relation lookup used solely to hide a cycle.
- **FR-015**: Prior-year temporal reads MUST occur only through self-referencing accumulators or explicit, documented orchestrator-built projections that read strictly earlier years.
- **FR-016**: Event-candidate, event-publication, domain-state, benefit-calculation, and snapshot-publication models MUST each belong to distinct, correctly-scoped stages, with contribution/match models removed from event-generation ownership and no manual stage exclusions required.
- **FR-017**: Every production stage model MUST either have a downstream consumer or be explicitly documented as an audit output.
- **FR-018**: The system MUST include graph-contract tests covering duplicate yearly publication, current-year fact feedback, stage ownership, and staged models with no consumers.

**Execution schedule**

- **FR-019**: After normalization, STATE_ACCUMULATION MUST execute in exactly one pipeline invocation per simulation year.
- **FR-020**: No STATE_ACCUMULATION model may require a command-level full-refresh exception.
- **FR-021**: Per-model, per-stage, and per-year failure attribution MUST remain intact, and partially-present outputs MUST remain associated with the failed or cancelled attempt that produced them.
- **FR-022**: Invocation reduction MUST be delivered as the consequence of the normalized graph, not as the mechanism forcing the redesign; existing command boundaries MUST be preserved until full-census parity is proven for the relevant phase.

**Behavior preservation (cross-cutting gates)**

- **FR-023**: Every `fct_*` and `dim_*` mart MUST have bidirectional `EXCEPT ALL` parity with the accepted A+B baseline. Exclusions MUST be limited to audit/timestamp columns named in a checked-in allowlist keyed by relation and column; every unlisted difference MUST fail parity.
- **FR-024**: Full 60,040-employee, 2025–2029 parity MUST pass after every migration phase; dev-census parity alone is insufficient.
- **FR-025**: Public mart schemas, deterministic event IDs, event sequencing, and duplicate multiplicities MUST remain unchanged; configuration and existing API result schemas MUST remain compatible, with only the explicit active-run warning added to scenario-level reads.
- **FR-026**: Event counts MUST match by scenario, plan, year, and event type.
- **FR-027**: Post-termination integrity MUST remain intact (Feature 112): no forbidden post-termination events are emitted.
- **FR-028**: Census enrollment behavior MUST remain reconstructible from census plus immutable facts (Feature 107).
- **FR-029**: Determinism, multi-year invariant, stale-rerun, failed-stage, and partial-failure-status suites MUST remain green.
- **FR-030**: Peak memory (RSS) MUST remain within 10% of the accepted A+B baseline.
- **FR-031**: All behavioral validation MUST use isolated databases; the shared development database MUST remain byte-unchanged.

**Characterization (guardrail foundation)**

- **FR-032**: Before any change, the system MUST record the accepted A+B configuration, census, code revision, construction signature, and database fingerprints, plus per-year/per-event-type counts, schemas, duplicate multiplicities, and representative state transitions.
- **FR-033**: The expected-behavior definition MUST NOT depend solely on ignored, PII-bearing golden databases; it MUST be captured as durable, checked-in characterization artifacts, including the relation-and-column parity-exclusion allowlist.

**Run isolation and compatibility**

- **FR-034**: Every Studio/API-managed single-scenario and batch attempt MUST execute against a new empty run-specific database and MUST NOT modify any prior run database, prior run archive, or the shared development database.
- **FR-035**: While a managed run is active, every scenario-scoped read MUST include an explicit in-progress warning; result-bearing reads MUST serve the latest successful run. A successful run MUST become current atomically only after its authoritative artifacts are durable, while failure or cancellation MUST leave the latest-successful selection unchanged.
- **FR-036**: At least 95% of representative scenario-scoped reads MUST complete within two seconds both when no run is active and when a newer run is active and the latest successful result is being served.
- **FR-037**: Normal simulation and calibration workflows MUST both use the normalized shared dependency graph wherever they select affected relations; calibration MUST contain no removed model and MUST preserve its accepted outputs and failure behavior. Fresh-run publication and active-run warnings are limited to managed simulation attempts and MUST NOT create a new calibration publication workflow.
- **FR-038**: Automated contract checks MUST prove that `enrollment_decision_projection` reads only earlier years and remains non-authoritative, and that enrollment and deferral remain separate authoritative state domains with no all-purpose replacement.

### Key Entities

- **Immutable event set (`fct_yearly_events`)**: The authoritative, deterministic record of one year's workforce and DC-plan events for a scenario/plan; published exactly once per year and never rebuilt downstream.
- **Canonical workforce-state accumulator**: The single authoritative relation for workforce fields (status, dates, compensation, level, age, tenure, proration), scoped by scenario/plan/employee/year, computed from prior-year state plus current-year workforce events.
- **Enrollment-state accumulator / deferral-state accumulator**: Existing, separate domain-state relations that remain authoritative for their domains; not folded into workforce state.
- **Event candidates**: Models producing proposed current-year events from census, prior-year projections, configuration, and each other; they must not read the current year's published facts.
- **`enrollment_decision_projection`**: A disposable, reconstructible prior-state boundary rebuilt before event generation; never authoritative state.
- **Workforce snapshot (`fct_workforce_snapshot`)**: The point-in-time mart composed from workforce, enrollment, deferral, contribution, and match state; published exactly once per year.
- **Accepted A+B baseline**: The frozen Feature 121 outputs (config, census, fingerprints, per-year/event-type counts) used as the parity reference for every phase.
- **Graph-contract tests**: Automated checks asserting single publication, no current-year fact feedback, clean stage ownership, and no orphaned staged models.
- **Simulation run attempt**: One managed execution with its own status, immutable run-specific database, metadata, provenance, and optional partial output when failed or cancelled.
- **Current successful result**: The single completed run selected for scenario result reads; it changes atomically after success and is independent of the newest attempt's status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `fct_yearly_events` and `fct_workforce_snapshot` are each produced exactly once per scenario/plan/year (verified across a full 2025–2029 run), eliminating the current duplicate yearly build of the event fact.
- **SC-002**: 100% of `fct_*` and `dim_*` marts pass bidirectional `EXCEPT ALL` parity against the accepted A+B baseline at full 60,040-employee scale for years 2025–2029 after every migration phase; only columns in the checked-in relation-and-column allowlist are excluded, and every unlisted difference fails.
- **SC-003**: Event counts match the baseline exactly across every (scenario, plan, year, event type) combination.
- **SC-004**: Workforce-state logic is consolidated from three implementations (~1,850 lines across the legacy state model, the scratch snapshot, and the snapshot mart) into one authoritative accumulator, with the two redundant relations removed once parity holds.
- **SC-005**: 100% of current-year execution-ordering relationships are represented by declared dependency edges; zero current-year event candidates read the current year's event fact; zero staged production models lack a consumer or documented audit designation — all enforced by graph-contract tests.
- **SC-006**: STATE_ACCUMULATION executes in exactly one pipeline invocation per simulation year with zero command-level full-refresh exceptions; the whole-run invocation total is measured and published as evidence rather than enforced as a fixed target.
- **SC-007**: Peak memory (RSS) stays within 10% of the accepted A+B baseline on both the reference and 60,040-employee Studio workloads, with wall time, CPU, model time, and invocation count measured and published in a before/after report.
- **SC-008**: Determinism, multi-year invariant, stale-rerun, failed-stage, partial-failure-status, post-termination-integrity (Feature 112), and census-enrollment-reconstruction (Feature 107) suites remain green, and failure attribution stays correct at the model/stage/year level.
- **SC-009**: Every simulation attempt executes against a newly created run-specific database; prior run databases, prior run archives, and the shared development database remain byte-unchanged throughout that attempt.
- **SC-010**: 100% of scenario-scoped reads during execution include an explicit in-progress warning, and 100% of result-bearing reads use the latest successful run; successful completion switches the current result atomically, while failure or interruption leaves it unchanged.
- **SC-011**: At least 95% of representative scenario-scoped reads complete within two seconds both with no active run and while serving the latest success during a newer active run.
- **SC-012**: The normal simulation and calibration workflows both pass dependency-closure and removed-model checks, and calibration output/failure regression tests remain green.
- **SC-013**: Contract tests explicitly prove earlier-year-only, non-authoritative enrollment projection behavior and continued separation of enrollment and deferral state.

## Assumptions

- The accepted Feature 121 (A+B) outputs are the correct, authoritative baseline; parity against them is the definition of "no behavior change."
- The full production reference workload is 60,040 employees over 2025–2029; the small dev census is used only for fast iteration, never as a parity gate.
- SQL is the only supported event-generation mode. Deprecated Polars compatibility remnants are not active pipeline behavior and remain untouched unless a surgical change is required to prevent them from affecting the active graph.
- "Published once per year" means once per scenario/plan/year partition within a newly created run-specific database. A rerun creates another empty database and rebuilds every year from scratch without modifying prior runs.
- Scenario-level reads resolve to the latest successful run. An active run is exposed only as warning/status context until it completes successfully.
- The fresh-run/latest-success publication contract applies to Studio/API-managed simulation attempts, including managed batch execution; direct caller-managed simulation destinations and calibration runs retain their existing lifecycle contracts.
- Audit/timestamp columns are the only permitted differences from baseline. Each excluded column is named in a checked-in allowlist keyed by relation and column; type- or name-based wildcard exclusion is prohibited.
- The 10% peak-memory ceiling is measured against the accepted A+B baseline under equivalent workloads.
- The scenario-read latency gate uses the existing representative dashboard/result endpoint mix, dataset scale, and workstation conditions; idle and active-run/latest-success conditions are reported separately.
- Existing checked calibration fixtures and regression expectations define accepted calibration output and failure behavior; this feature does not redefine calibration objectives or tolerances.
- Golden PII-bearing databases remain git-ignored; durable expected-behavior definitions are captured as checked-in characterization artifacts instead.

## Dependencies

- **Feature 121 (#478, PR #481)** — provides the accepted A+B baseline and the frozen configuration/census/fingerprints this feature validates against.
- **Feature 112 (Post-Termination Integrity)** — its invariants must continue to hold through any event reordering.
- **Feature 107 (Preserve Census Enrollment)** — census enrollment must stay reconstructible from census plus immutable facts.
- **Feature 113 (Invariants & Determinism)** and existing stale-rerun / failed-stage / partial-failure-status suites — must remain green.
- Isolated-database validation workflow (per project policy) for all behavioral checks.

## Out of Scope / Non-Goals

- This is a **separate architecture feature**, not an expansion of Feature 121; it deliberately performs the workforce/DC SQL redesign that Feature 121's contract prohibited.
- Invocation reduction is **not** the primary objective; it is the byproduct of a clean graph and must never drive removal of a still-load-bearing boundary.
- Do not promote the orphaned `int_employee_state_by_year` in place; build and prove a shadow accumulator first.
- Do not create a new all-purpose/combined state table; workforce, enrollment, and deferral remain separate domains.
- Do not fold benefit/account state into the workforce accumulator.
- No changes to public mart schemas, event semantics, deterministic event IDs/sequences, duplicate multiplicities, configuration, or existing API result schemas; only the backward-compatible active-run warning may be added to scenario-level reads.
- No new user-facing Studio/CLI capabilities beyond the explicit in-progress warning on scenario-level API reads; this remains primarily an internal pipeline architecture change.
- No new calibration run-storage, current-result publication, or active-run warning capability; calibration is in scope only for shared graph compatibility, output parity, and failure behavior.
- No restoration of Polars event generation and no general cleanup of deprecated Polars compatibility remnants.
