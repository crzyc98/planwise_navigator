# Feature Specification: Unify Orchestrator Construction Across Entry Points

**Feature Branch**: `120-unify-orchestrator-construction`
**Created**: 2026-07-20
**Status**: Draft
**Input**: Work on issue #477 — "Unify orchestrator construction across CLI, Studio, batch, tests, and profiling"

## Overview

Today a simulation can be started from several entry points — the `simulate` command, the batch scenario runner, the Studio web interface (which shells out to the command line), the parity/profiling tooling, and the test suites. These entry points do **not** all construct the simulation engine the same way: they install different database managers, different startup/initialization behavior, different runner setup, and different work schedules. One path silently runs extra initialization work; another reads a configuration option that a third path ignores entirely.

The practical consequences already observed: a performance gate was measured against a path no real user runs; a "product optimization" turned out to be behavior only the internal tooling path exhibits; and a configuration option meant to change execution behavior is honored by only one bypassed path. This is a correctness-of-measurement and behavior-consistency problem, not a missing flag.

This feature establishes **one canonical way to construct a simulation run**, and requires every entry point to use it, so that the same validated configuration produces the same behavior — and the same results — no matter how the run is launched.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Same configuration, same result from any entry point (Priority: P1)

An analyst runs a scenario from the `simulate` command; a teammate runs the identical scenario configuration through the batch runner; another runs it from the Studio web interface. All three must produce the same simulation — identical authoritative event and workforce-snapshot outputs — because the underlying run was constructed identically.

**Why this priority**: This is the core value and the root cause of the reported problems. If the same configuration constructs differently per entry point, every downstream guarantee (reproducibility, audit parity, measurement validity) is unsound. Delivering just this slice makes the platform trustworthy across its entry points.

**Independent Test**: Take one validated scenario configuration and one census in isolated databases. Run it through the command-line, batch, and Studio paths. Compare the authoritative event and snapshot tables. Success = exact multiset equality over the documented authoritative columns, excluding only execution-time audit timestamps.

**Acceptance Scenarios**:

1. **Given** one validated configuration and census, **When** the run is launched from the command line and independently from the batch runner into isolated databases, **Then** the authoritative event and snapshot outputs are exactly equivalent.
2. **Given** the same configuration, **When** the run is launched from Studio, **Then** it produces the same outputs as the command-line run for that configuration.
3. **Given** the same validated configuration, **When** construction is inspected at each product entry point (CLI, batch, Studio), **Then** the construction signature is identical — same runner behavior, thread policy, initialization policy, installed startup steps, and work schedule — with database and project compared **semantically** (same isolation policy and target/overlay relationship), not by literal path.

---

### User Story 2 - Construction is observable, so measurement describes production (Priority: P2)

A performance or data-quality engineer needs the profiling harness and the parity tooling to exercise the **same** construction that real users run, and needs each run to record which construction path it used and what work schedule it executed — so that benchmark and parity results describe production, not an internal-only path.

**Why this priority**: The corrected run-cost baseline (issue #455) exists precisely because a prior campaign measured a non-production path. Making construction observable and forcing the tooling onto the canonical path prevents that class of invalid measurement from recurring, and is a prerequisite for the follow-on work-schedule reduction.

**Independent Test**: Run a production-path simulation and confirm its diagnostics record a construction signature (runner behavior, database location, project location, thread policy, startup/initialization policy) and the executed work schedule. Run the profiling harness and confirm it reports the same construction signature as the command-line run for the same configuration.

**Acceptance Scenarios**:

1. **Given** a completed production-path run, **When** its run diagnostics are read, **Then** they contain the construction signature and the executed work schedule.
2. **Given** the profiling harness and the parity tooling, **When** they run a configuration, **Then** they report the same construction signature the command-line path reports for that configuration.

---

### User Story 3 - One explicit fresh-database initialization contract (Priority: P2)

An operator runs a scenario against a brand-new, empty database. Initialization either fully succeeds or fails loudly with a clear reason. A critical initialization failure can never be silently swallowed, leaving a half-initialized database that then produces wrong results.

**Why this priority**: One current construction path installs a self-healing initializer whose critical failure on a fresh database is silently absorbed (tracked as issue #467). Unifying construction must not spread that hazard; it must replace it with a single, explicit, fail-loud contract.

**Independent Test**: Launch a run against a fresh, empty database under a forced initialization failure. Success = the run aborts with a clear, attributable error and does not proceed to produce outputs; under normal conditions a fresh database initializes and completes.

**Acceptance Scenarios**:

1. **Given** a fresh empty database and a forced critical initialization failure, **When** a run is launched, **Then** it aborts with a clear error and produces no simulation outputs.
2. **Given** a fresh empty database under normal conditions, **When** a run is launched from any entry point, **Then** initialization completes and the run proceeds identically to a run on a pre-initialized database.

---

### User Story 4 - No configuration option is silently ignored (Priority: P3)

An operator sets a configuration option intended to change execution behavior. The system either honors it end-to-end through the entry point they used, or rejects it during validation with a clear message. It is never accepted and silently ignored.

**Why this priority**: An execution-selection option is currently honored only by a bypassed internal path, so setting it through a real entry point does nothing and gives no feedback. Prevents a whole class of "I set it but nothing changed" confusion and mis-attributed results.

**Independent Test**: Set an unsupported or not-yet-wired execution option in a configuration and launch a run through a real entry point. Success = the run is rejected at validation with a clear message naming the option; supported options take effect identically across entry points.

**Acceptance Scenarios**:

1. **Given** a configuration with an unsupported execution option, **When** a run is launched from any real entry point, **Then** validation rejects it with a clear message rather than accepting and ignoring it.
2. **Given** a configuration with only supported options, **When** launched from different entry points, **Then** the resolved behavior is identical.

---

### Edge Cases

- **Scenario-specific project overlays**: A scenario that supplies its own isolated project location must still route through the canonical construction and keep that overlay in effect.
- **Isolated per-scenario databases**: Batch and Studio each run in their own isolated database; unifying construction must preserve one-database-per-scenario isolation and must never write to the shared development database during a run.
- **Legacy/alternate command entry**: Any additional or legacy command entry that constructs a run directly must be migrated or removed so it cannot diverge again.
- **Test adapters**: Test suites that construct runs with lightweight or mocked dependencies must obtain them through the canonical seam with explicit overrides, not by reproducing construction independently.
- **Fresh vs. pre-initialized database**: The observable behavior and outputs must be identical whether the target database was empty or already initialized.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single canonical way to construct a simulation run that fixes the database manager, runner behavior, registries, validators, startup/initialization policy, thread policy, and any optional execution capability.
- **FR-002**: The `simulate` command, the batch scenario runner, the Studio-launched run, the parity tooling, the invariant/determinism tests, and the performance profiling harness MUST all construct runs through this one canonical seam.
- **FR-003**: For a given validated configuration, every entry point MUST resolve an equivalent construction — same runner behavior, effective run variables, thread policy, startup/initialization policy, and work schedule. Database and project equality is defined **semantically** (same isolation policy and same target/overlay relationship), NOT by literal path: isolated runs necessarily use different database paths, and a scenario may supply its own project overlay.
- **FR-004**: Minimal and Studio-realistic multi-year runs, executed in isolated databases through any two entry points for the same configuration, MUST produce exactly equivalent authoritative event and workforce-snapshot outputs (identical row multisets, excluding execution-time audit timestamps).
- **FR-005**: The construction signature (runner behavior, database location, project location, thread policy, startup/initialization policy, and installed startup steps) MUST be observable in a run's diagnostics.
- **FR-006**: A run's executed work schedule MUST be recordable so it can be compared across entry points and over time.
- **FR-007**: Fresh-database initialization MUST have exactly one explicit failure contract; a critical initialization failure MUST always surface and abort the run, and MUST NOT be silently absorbed.
- **FR-008**: A supported configuration option MUST take effect identically regardless of entry point; an unsupported or not-yet-reachable execution option MUST be rejected during validation with a clear message rather than silently ignored.
- **FR-009**: Once entry points are migrated, duplicate/independent construction paths MUST be removed so a divergent path cannot re-emerge.
- **FR-010**: Studio MAY remain a subprocess of the command-line path; if it does, its launched command MUST reach the same canonical construction.
- **FR-011**: Construction MUST preserve isolated per-scenario database behavior and scenario-specific project overlays.
- **FR-012**: During validation of this feature, the shared development database MUST remain byte-identical (unchanged) before and after.
- **FR-013**: Project documentation MUST name the canonical construction seam and remove conflicting claims about entry points and execution options.
- **FR-014**: A production-path integration test MUST record the construction signature and the executed work schedule and assert they match the canonical expectation.
- **FR-015**: When Studio launches a run as a subprocess of the command line, the recorded entry point MUST still identify the run as Studio-originated; attribution MUST survive the API→CLI boundary.
- **FR-016**: The construction signature MUST be recorded at run start; the **executed** work schedule and final invocation count MUST be recorded at run completion in the existing append-only `run_execution_metadata` record (they do not exist at start). Schema evolution MUST preserve Feature 119's required terminal-execution fields and historical rows in pre-existing scenario databases.

### Key Entities *(include if feature involves data)*

- **Canonical construction**: The single, authoritative description of how a simulation run is assembled — the runner behavior, database location, project location, thread policy, startup/initialization policy, registries, validators, and any optional execution capability — that every entry point resolves from a validated configuration.
- **Construction signature**: An observable, comparable record of the resolved construction for a given run (runner behavior, database location, project location, thread policy, startup/initialization policy, installed startup steps). Used to prove two entry points constructed identically.
- **Initialization contract**: The single, explicit rule for how a fresh/empty database is prepared and how initialization failure is reported — success proceeds, critical failure aborts loudly, nothing is silently absorbed.
- **Work schedule**: The ordered set of build/execution steps a run performs, recorded per run so it can be compared across entry points and tracked as later work reduces it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of distinct simulation-run construction paths in the product and its tooling is reduced to **one** canonical seam (from the current three-or-more), verified by inspection and by removal of the duplicate paths.
- **SC-002**: For a fixed validated configuration, the recorded construction signature is **identical** across the `simulate` command, the batch runner, Studio, the parity tooling, the invariant tests, and the profiling harness.
- **SC-003**: Minimal and Studio-realistic multi-year isolated runs launched through two different entry points for the same configuration differ in **zero** rows of the authoritative event and workforce-snapshot outputs, compared as **exact multiset equality over an explicit column list** (all columns except the `created_at`/`snapshot_created_at` audit stamps), order-insensitive.
- **SC-004**: **Zero** supported configuration options are silently unreachable: every supported option either takes effect identically across entry points or is rejected at validation with a clear message.
- **SC-005**: **100%** of critical fresh-database initialization failures surface and abort the run; none are silently absorbed (the class of failure behind issue #467 is eliminated).
- **SC-006**: The shared development database is **byte-identical** before and after the feature's validation runs (all validation uses isolated databases).
- **SC-007**: A production-path integration test exists and passes that records and asserts the construction signature and work schedule.
- **SC-008**: Documentation names exactly one canonical construction seam, and a repository-wide audit (docs, README/CLAUDE guidance, CLI help text, feature specs) finds **no** remaining claim of an entry point or execution option the code does not honor.
- **SC-009**: An isolated **100,000-employee** multi-year run completes without memory errors at the single-threaded default; on the same machine and workload, the median completion time and peak RSS across three repetitions increase by no more than **10%** from the pre-change measurements.
- **SC-010**: **100%** of Studio-launched runs are identified as Studio-originated, while direct command-line runs are identified as command-line-originated; attribution remains correct across the Studio-to-command boundary.

## Assumptions

- **Canonical behavior of record is the current production path.** The behavior real users run today via the `simulate` command (and therefore Studio) is treated as the reference for the canonical seam; other paths converge onto it rather than the reverse.
- **No implicit self-healing initialization on any standard entry point.** The production path today does not install the self-healing initializer, and the run's own seed/setup already prepares a fresh database. CLI, Studio, batch, parity, invariant, and performance entry points therefore resolve to `NONE`. If fresh-batch validation exposes a missing setup step, that setup is repaired in the canonical pipeline rather than preserving an entry-point-specific initialization policy. Self-healing, if retained, is an explicit diagnostic/repair capability with a loud failure contract.
- **The alternative compiled execution engine is out of scope and remains paused.** No execution engine other than the standard one is present on the main line; the execution-option contract for this feature is "reject unsupported values at validation," not "wire a new engine." If a future engine is revived, the canonical seam is the single place it would attach.
- **Studio remains a subprocess of the command-line path.** No in-process execution-model change is required for Studio; only that its launched command reaches the canonical seam.
- **All validation happens in isolated databases**, per the project's isolated-database rule; the shared development database is never built into during validation.
- **Existing authoritative outputs and audit stamps are unchanged.** This feature changes how a run is assembled, not what a correct run computes; behavioral outputs (events, snapshots, and their behavioral date fields) must be unaffected.
- **The performance/invocation baseline is provisional.** The corrected #455 wrapper campaign recorded ~132s and 38 wrapped invocations at 60,040 employees / 5 years, while a retained real Studio dbt log recorded ~174s and 62 dbt command invocations for a similar run. The two count different things (the harness wraps `DbtRunner.execute_command`; the Studio log counts every dbt subprocess, including calls made outside that method). The **authoritative production work schedule and its invocation count are established by the work-schedule-capture work in this feature** (User Story 2); until then, any baseline number is provisional and MUST NOT be asserted as an acceptance threshold. Reconciling 38 vs 62 is itself an output of the schedule capture.

## Dependencies

- Builds directly on the corrected production-path profiling (issue #455 / merged), whose harness now records a construction signal and can compare paths.
- Must resolve the fresh-database initialization hazard tracked as issue #467 as part of the single initialization contract.
- Precedes the production-path work-schedule reduction (issue #478), which optimizes the one canonical schedule this feature establishes.
- Supersedes the assumption in the paused compiled-engine program that internal-path results automatically describe the command-line/Studio behavior.
