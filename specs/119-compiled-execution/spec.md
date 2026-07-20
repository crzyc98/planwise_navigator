# Feature Specification: Compiled DAG Execution

**Feature Branch**: `119-compiled-execution`
**Created**: 2026-07-15
**Updated**: 2026-07-19
**Status**: Draft — #470 hardening required before default enablement
**Input**: User description: "Compile the dbt DAG once, execute compiled SQL directly, and preserve dbt semantics and exact result parity while making repeated simulation years materially faster. Harden the prototype under #470 before enabling it by default."

## Overview

PlanAlign currently pays dbt's parse and startup cost repeatedly during a simulation. This feature introduces a compiled execution mode that prepares a complete invocation plan once for a fully specified render context, then executes the resulting node statements directly for each applicable simulation step. The intended outcome is a substantial reduction in repeated orchestration overhead without weakening correctness, determinism, isolation, auditability, or database safety.

The compiled path is an optimization, not a second semantic definition of the pipeline. It must select the same nodes as dbt, target only the explicitly requested run database, preserve exact row multiplicities, and reproduce required lifecycle behavior. A run may delegate to dbt only when preflight identifies a known unsupported semantic. Failures discovered after compiled writes begin must be rolled back before any permitted delegation; arbitrary execution failures must not be hidden by replaying the invocation through dbt.

The existing implementation is a prototype. GitHub issue #470 is the hardening milestone for making the compiled path trustworthy. The compiled path must remain opt-in until every acceptance gate in this specification passes in the stated order.

## Clarifications

### Session 2026-07-15

- Q: Does the compiled runner need to work with arbitrary third-party dbt packages? → A: No. It must support PlanAlign's committed project; unknown external macros may delegate to dbt and must be reported.
- Q: Must compiled execution reproduce dbt log text exactly? → A: No. It must preserve lifecycle semantics and required side effects; informational `log()` calls alone must not make an invocation unsupported.
- Q: Is concurrent execution of two simulation years required? → A: No. Sequential execution is required, while independently running scenarios must not contaminate each other's compiled artifacts or target databases.

### Session 2026-07-19 — #470 hardening

- Q: What constitutes result parity? → A: Exact table schemas and row multisets, including duplicate multiplicities, for authoritative outputs; physical row order and nondeterministic timestamps are excluded.
- Q: When is fallback permitted? → A: Only when complete preflight identifies a known unsupported selector, hook, materialization, or other explicitly classified semantic before execution begins. If writes have begun, the invocation must roll back before any permitted delegation.
- Q: Can an unsupported selector resolve to an empty invocation and succeed? → A: No. Empty resolution is valid only when dbt itself proves the selector is valid and matches no nodes; otherwise the invocation must be rejected or explicitly delegated.
- Q: When may compiled execution become the default? → A: Only after all ordered acceptance gates pass, including an actual 100K-worker completion and memory run and zero unexpected fallbacks.

### Session 2026-07-19 — Gate 5 outcome and default decision

- Q: Gate 5 measured 0.93× at 60K (105.1s compiled vs 97.9s dbt, after three optimization rounds) against the ≥1.8× bar; Gates 1–4 and 6 passed. How does the feature conclude? → A: **Close as oracle** (maintainer decision). Compiled execution ships **opt-in**; the default remains `dbt`; the flip task is cancelled, not deferred. Gate 5 is recorded failed-with-analysis: the architecture's floor is structural (15/27 invocations delegate to in-process dbt by design; ~21s/run per-year parse+compile required by the SQL-stays-dbt's rule). #470's epic purpose — a trustworthy exact-parity reference oracle for the native-kernel program — is fully achieved, and the Gate 5 data is the motivating evidence for #471.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a Multi-Year Simulation Faster Without Changing Results (Priority: P1)

As an actuary or engineer running a multi-year simulation, I want repeated pipeline invocations to avoid redundant dbt startup and parsing so that the run completes materially faster while producing the same authoritative outputs as the standard dbt path.

**Why this priority**: This is the primary performance value. It is acceptable only if event, state, and workforce outputs remain deterministic and exactly equivalent.

**Independent Test**: Run the same isolated tiny, development, and 60K scenarios through standard dbt execution and compiled execution, then compare schemas and row multisets for all authoritative output tables. Repeat a multi-year compiled run from the same seed and inputs and compare rerun outputs.

**Acceptance Scenarios**:

1. **Given** a valid isolated simulation configuration, **When** it runs through compiled execution, **Then** the selected DAG is prepared once for that complete render context and reused without reparsing for each repeated invocation.
2. **Given** identical seed, configuration, census, and render context, **When** standard and compiled executions complete, **Then** authoritative output schemas and row multisets are equal, including duplicate multiplicities.
3. **Given** a completed compiled run, **When** it is rerun from identical inputs, **Then** deterministic outputs and invariant results are unchanged.
4. **Given** a 100K-worker scenario, **When** compiled execution runs in an isolated database, **Then** it completes without an out-of-memory failure and without using the shared development database.

---

### User Story 2 - Preserve dbt Invocation Semantics and Database Isolation (Priority: P1)

As a pipeline maintainer, I want compiled execution to honor dbt selection, dependency, hook, materialization, target, and transaction semantics so enabling the optimization does not create a subtly different pipeline.

**Why this priority**: A fast path that silently skips work, targets the wrong database, or leaves partial writes is unsafe for event-sourced simulation.

**Independent Test**: Exercise representative model, tag, path, source, exclusion, and dependency selectors; project hooks containing informational logging; explicit isolated database overrides; partial-write failures; forced rebuilds; and permitted delegation. Verify node selection, lifecycle side effects, atomicity, artifact isolation, and target database contents.

**Acceptance Scenarios**:

1. **Given** a supported selector, **When** preflight completes, **Then** compiled execution resolves exactly the node set and dependency order dbt would resolve.
2. **Given** an unknown or unsupported selector, **When** preflight cannot prove its semantics, **Then** the invocation never reports successful completion with zero nodes.
3. **Given** project hooks that contain supported lifecycle actions plus informational `log()` calls, **When** preflight evaluates them, **Then** logging alone does not force the invocation to delegate.
4. **Given** an explicit isolated database path, **When** either compiled execution or an allowed in-process dbt delegation runs, **Then** every operation targets that path and the shared development database remains unchanged.
5. **Given** a compiled invocation that fails after a write, **When** the failure is handled, **Then** all writes from that invocation are rolled back before the error is reported or any allowed delegation begins.
6. **Given** cached compiled SQL for a run, **When** a delegated invocation or build operation occurs, **Then** that operation cannot overwrite or mutate the cached compiled bundle.

---

### User Story 3 - Understand Every Delegation and Parity Failure (Priority: P2)

As a developer or operator, I want each compiled invocation to report what ran, what delegated, why it delegated, and whether parity passed so I can trust the fast path and diagnose unsupported semantics without reading source code.

**Why this priority**: The optimization cannot be defaulted safely if unexpected delegation hides defects or performance regressions.

**Independent Test**: Run a supported scenario and confirm zero unexpected delegations; force each known unsupported semantic and confirm the reason, node set, execution mode, and timing are recorded; inject a duplicate-row mismatch and confirm parity fails.

**Acceptance Scenarios**:

1. **Given** a fully supported invocation, **When** it completes, **Then** the run summary records direct execution, selected nodes, timing, and zero delegation.
2. **Given** a known unsupported semantic found during preflight, **When** the invocation delegates, **Then** the summary records a stable reason code and the affected invocation or nodes.
3. **Given** an unclassified compiled execution error, **When** it occurs, **Then** the run fails with node and statement context instead of replaying through dbt.
4. **Given** baseline and candidate tables with the same distinct rows but different duplicate counts, **When** parity is checked, **Then** the comparison fails and reports the multiplicity mismatch.

### Edge Cases

- A forced full refresh invalidates any compiled plan or materialization assumption that depends on the previous invocation mode.
- A build invocation includes tests and other resource types; unsupported resource semantics are identified during preflight rather than discovered after writes begin.
- An informational `log()` call in a project hook is supported independently of the hook's meaningful database side effects.
- An unsupported or malformed selector cannot be interpreted as a successful zero-node invocation.
- A fallback, build, or concurrent scenario run cannot mutate another run's cached compiled SQL or manifest artifacts.
- A schema change, configuration change, macro change, dbt version change, adapter change, selector change, variable change, or target change invalidates reuse through the complete render-context identity.
- A database lock or statement error after a write causes an invocation rollback and a contextual failure; it is not treated as an unsupported semantic.
- Seeds and other non-model resources continue to use dbt unless their semantics are explicitly supported and parity-proven.
- Duplicate output rows are compared as a multiset, not collapsed by set comparison.
- Repeated known delegations are visible as a fallback storm and fail the zero-unexpected-fallback gate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer an opt-in compiled execution mode while preserving standard dbt execution as the default until every acceptance gate passes.
- **FR-002**: The system MUST construct a complete invocation plan from dbt-produced project metadata for the exact project, profile, target, adapter, dbt version, command, selector, exclusion, variables, configuration, and database destination used by the run.
- **FR-003**: The system MUST resolve supported selectors and dependency order with dbt-equivalent semantics; it MUST NOT treat an unrecognized or unproven selector as a successful empty invocation.
- **FR-004**: A compiled bundle MUST be immutable after publication, isolated per run, and reusable only when its full render-context identity matches the invocation.
- **FR-005**: Direct execution MUST preserve supported pre-hook, model materialization, post-hook, test, and lifecycle side effects in dbt order. Informational logging alone MUST NOT make an otherwise supported invocation fall back.
- **FR-006**: Each direct statement failure MUST identify the invocation, node, lifecycle phase, and statement context needed to diagnose it.
- **FR-007**: Delegation to dbt MUST occur only for explicitly classified unsupported semantics discovered during complete preflight. Arbitrary execution or database errors MUST fail rather than trigger automatic replay.
- **FR-008**: Each compiled invocation MUST be atomic: on failure, all database writes from that invocation MUST be rolled back before error propagation or any allowed delegation.
- **FR-009**: Both direct execution and delegated in-process dbt execution MUST use the explicit isolated database supplied for the run and MUST NOT write to `dbt/simulation.duckdb` during validation.
- **FR-010**: Delegated dbt operations, builds, and concurrent runs MUST NOT mutate a published compiled bundle or change the SQL subsequently executed from that bundle.
- **FR-011**: A parity comparator MUST detect schema differences, missing or extra rows, changed values, and different duplicate multiplicities while excluding only documented nondeterministic fields.
- **FR-012**: The system MUST emit structured per-invocation execution records containing execution mode, selected nodes, stable fallback reason when applicable, elapsed time, affected row counts where available, and outcome.
- **FR-013**: Run-level provenance MUST record final compiled invocation count, delegated invocation count, unexpected delegation count, reason summaries, and parity status without weakening append-only audit semantics.
- **FR-014**: Existing CLI, batch, Studio, API, export, validation, and provenance behavior MUST remain compatible unless a caller explicitly opts into compiled execution.
- **FR-015**: The system MUST complete an actual isolated 100K-worker scenario without an out-of-memory failure before compiled execution is eligible to become the default.
- **FR-016**: Performance measurements MUST include all compilation, preflight, direct execution, and delegation costs and MUST use the same inputs, environment, and isolated-database conditions for baseline and candidate runs.
- **FR-017**: Default enablement MUST occur only after the ordered acceptance gates pass: tiny isolated parity; multi-year determinism and rerun parity; development and 60K parity; 100K memory and completion; tiny, development, and large performance; and zero unexpected fallbacks.

### Key Entities

- **Render Context**: The complete set of project, version, adapter, target, command, selector, variable, configuration, and destination inputs that determine dbt rendering and node selection.
- **Compiled Bundle**: An immutable, run-isolated manifest plus executable node statements, dependencies, hook statements, materialization metadata, and identity derived from one render context.
- **Invocation Plan**: The ordered, preflight-validated nodes and lifecycle operations for a single dbt-equivalent invocation.
- **Execution Record**: The mode, selected nodes, timings, row counts, failure context, and stable fallback reason for one invocation.
- **Parity Report**: Exact schema and row-multiset comparison results for authoritative outputs, including duplicate-count differences.
- **Run Provenance**: Append-only metadata describing the input identity, bundle identity, execution totals, fallback totals, parity result, and final run status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: End-to-end compiled execution is at least 1.8× faster than standard dbt execution on the repository's approved large benchmark, with a 2.0× target, when measured under equivalent isolated conditions and including every compilation and delegation cost.
- **SC-002**: Tiny, development, and 60K baseline-versus-compiled comparisons have identical authoritative schemas and row multisets, including duplicate multiplicities, except for explicitly documented nondeterministic fields.
- **SC-003**: Multi-year invariant suites pass, and repeated runs from identical inputs produce identical deterministic outputs.
- **SC-004**: Regression tests prove that informational project `log()` hooks do not force universal delegation, unsupported selectors cannot succeed with zero nodes, in-process dbt uses the explicit isolated database, partial writes roll back, fallback/build operations do not corrupt cached compiled SQL, and duplicate multiplicity differences fail parity.
- **SC-005**: An actual isolated 100K-worker run completes without an out-of-memory failure and records its peak-memory evidence.
- **SC-006**: Supported tiny, development, and large benchmark runs complete with zero unexpected fallbacks; any expected fallback is classified, counted, and attributable from the run summary.
- **SC-007**: Forced known-unsupported cases delegate safely before writes and produce the same authoritative outputs as the corresponding standard dbt invocation.
- **SC-008**: The shared development database is unchanged by every acceptance and performance run.
- **SC-009**: A maintainer can identify the execution mode, selected nodes, failure or fallback reason, and parity outcome for a run from structured records without inspecting implementation code.
- **SC-010**: Compiled execution remains opt-in until SC-001 through SC-009 pass in the FR-017 gate order; the default is flipped only afterward.

## Acceptance Gate Order

The gates are deliberately sequential. Evidence from a later gate does not waive an earlier failure.

1. Tiny isolated baseline-versus-compiled exact parity.
2. Multi-year determinism, invariants, and identical-input rerun parity.
3. Development and 60K exact parity.
4. Actual 100K-worker memory and completion proof.
5. Tiny, development, and large end-to-end performance proof, including fallback overhead.
6. Zero unexpected fallbacks across the supported acceptance matrix.
7. Only after gates 1–6 pass, enable compiled execution by default with standard dbt retained as an explicit compatibility mode.

## Assumptions

- Compilation cost is amortized across repeated invocations only when the full render context is identical.
- DuckDB remains the execution backend for Feature 119; replacing dbt, DuckDB, or SQL is a separate architectural program.
- Required compilation and benchmark tools are already present in the repository's supported environment; no new runtime dependency is assumed.
- Authoritative outputs are compared as unordered row multisets unless an output contract explicitly defines ordering.
- Timestamps or run identifiers may differ only where they are documented as nondeterministic and excluded symmetrically from parity.

## Out of Scope

- Supporting arbitrary third-party dbt packages or macros beyond PlanAlign's committed project.
- Replacing dbt's compile and metadata production responsibilities within Feature 119.
- Parallel execution of multiple simulation years within one scenario.
- Altering public mart schemas, event semantics, probability models, or plan rules.
- The native-kernel experiment in #471. It begins only after #470 is complete and is the next strategic investment.
- The broader native execution work in #472–#475. Those issues remain blocked until #471 demonstrates a convincing speedup and receives a GO decision.
