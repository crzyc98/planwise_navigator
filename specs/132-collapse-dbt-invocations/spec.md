# Feature Specification: Collapse Remaining Per-Year Transformation Invocations

**Feature Branch**: `132-collapse-dbt-invocations`
**Created**: 2026-08-02
**Status**: Draft
**Input**: User description: "Reduce remaining per-year dbt invocations: startup is now 43.2s of a 91.5s run" (issue #519)

## Overview

A five-year, 60,040-employee Studio-config simulation currently takes **102.7 seconds** (the median of 18 prior 20-command runs). A fresh three-run campaign for this feature measured 103.576s, confirming that historical cohort. The originating issue's 91.5s headline is unreproducible on this machine and its stated components (27.7 + 43.2 + 16.1) sum to 87.0s rather than 91.5s.

Startup cost is flat — roughly 2–4 seconds per command — regardless of how much work that command performs. It cannot be optimized down; it can only be paid fewer times. This feature reduces the number of commands the orchestrator issues per run, without changing what any of them compute.

The prize is bounded by two measured invocation-reduction cohorts: 38 → 30 commands saved 11.7s (1.46s per command) and 30 → 20 saved 17.5s (1.75s per command). The realistic value of removing six more commands is therefore about **10 seconds**, while SQL and orchestration work remain untouched.

### Why this is dangerous work

Feature 121's Tier C established that command boundaries in this pipeline can be **load-bearing**: regrouping which models share a command changed simulation results even though every table was built and populated correctly. Worse, Tier C **passed parity at 7,500 employees and broke at 60,000**. Any change here is presumed unsafe until proven otherwise at full scale.

## Clarifications

### Session 2026-08-02

- Q: Should the parity gate cover only the three tables named in the originating issue, or all marts? → A: All marts — reuse Feature 121's established contract verbatim (every `fct_*`/`dim_*` enumerated rather than hardcoded, plus its determinism re-run check)
- Q: Is the wall-time target a whole-feature gate, given that a reverted Story 2 is a likely and acceptable outcome? → A: Per-step — Story 1 must deliver ≥3s and Story 2 ≥6s, derived from observed 1.46–1.75s savings per removed command; the feature succeeds if every kept step met its bar and every reverted or abandoned step was recorded
- Q: Is the "20 → 12 commands" target reachable, given that differing rebuild semantics cannot be collapsed together? → A: No — relax to 14 or fewer, derived from the full-rebuild floor. The count target follows the correctness constraint, never the reverse
- Q: Does the 60k parity gate run in CI or locally? → A: Local pre-merge, with the parity output committed as a reviewable artifact under the feature directory. The gate runs twice in this feature's lifetime and does not justify permanent CI cost

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst waits less for the first simulation year (Priority: P1)

An analyst starts a five-year simulation from Studio or the CLI. Today the first year alone spends eight process launches to perform about three seconds of real work — including building one foundational model twice in two adjacent commands. The analyst experiences several seconds of apparent stalling before any simulation year visibly progresses.

After this story, the first year's one-time setup work is issued as materially fewer commands, and the run reaches its first year of simulated results noticeably sooner.

**Why this priority**: Highest ratio of overhead to work in the entire run, and it is *one-time setup* rather than per-year simulation semantics — so the blast radius on simulation correctness is the smallest of the available targets. It is the right place to prove the approach before touching per-year behavior.

**Independent Test**: Run a five-year 60k simulation before and after the change on the same revision and configuration. Confirm the first-year command count drops, total wall time drops, and every output table is row-for-row identical.

**Acceptance Scenarios**:

1. **Given** a fresh isolated database and a 60k Studio-shaped configuration, **When** a five-year simulation runs, **Then** the number of transformation commands issued for the first simulation year is fewer than the current eight.
2. **Given** the same configuration run before and after the change, **When** results are compared row-by-row in both directions, **Then** every mart table is identical apart from audit-timestamp and per-run provenance fields.
3. **Given** the collapsed first-year setup, **When** a model that requires a full rebuild is part of the setup work, **Then** it is still fully rebuilt — collapsing commands never silently downgrades a full rebuild to an incremental one.
4. **Given** a first simulation year, **When** setup completes, **Then** no model has been built more than once.

---

### User Story 2 - Analyst waits less for every subsequent year (Priority: P2)

For simulation years two onward, the orchestrator issues three commands per year. The first of those is the worst ratio in the entire run: roughly four seconds of startup to perform 0.7 seconds of work — paid four times across a five-year run. The remaining two commands already amortize their startup well and are deliberately out of scope.

After this story, later years issue two commands instead of three.

**Why this priority**: Its empirical ceiling is only ~6–7s, and it touches per-year simulation semantics, which is precisely where Feature 121's Tier C failed. It follows a proven, measured Story 1 and may be abandoned when that value does not justify the correctness risk.

**Independent Test**: Run a five-year 60k simulation and count commands per later year; confirm two, confirm wall-time reduction, confirm bidirectional row-level parity.

**Acceptance Scenarios**:

1. **Given** a five-year simulation, **When** any year after the first executes, **Then** exactly two transformation commands are issued for that year.
2. **Given** the merged later-year command, **When** results are compared against the pre-change run, **Then** every mart table is row-for-row identical in both directions at 60k scale.
3. **Given** the merged command, **When** a stage's validation rules and telemetry are inspected, **Then** they still execute and still report per-stage, even though the underlying commands were combined.
4. **Given** a merged command, **When** any model within it fails, **Then** the failure is still attributed to a recognizable stage and simulation year in the error output.

---

### User Story 3 - Engineer can tell whether each step was worth it (Priority: P3)

The honest ceiling for this work is modest, and the two steps have different risk profiles. An engineer needs a recorded, comparable measurement after each step — not a single measurement at the end — so the sequence can be stopped when the remaining gain no longer justifies the correctness risk.

**Why this priority**: Enables the "re-measure rather than pursue blind" discipline, but delivers no speedup on its own. It is a decision aid layered on top of Stories 1 and 2.

**Independent Test**: After each step, produce a recorded measurement showing command count, total wall time, and the startup/execution/orchestration split, comparable against the immediately preceding recorded state.

**Acceptance Scenarios**:

1. **Given** a completed step, **When** its measurement is recorded, **Then** it reports command count, total wall time, and the three-way time split against the same workload as the prior recording.
2. **Given** a step whose measured gain is negligible, **When** the record is reviewed, **Then** it carries a documented decision to keep, revert, or stop the sequence.

---

### Edge Cases

- **A collapsed command mixes models with different rebuild requirements.** A full-rebuild instruction applies to an entire command, not to individual models within it. Models needing a full rebuild therefore cannot be naively merged with models that must remain incremental — this constraint sets a hard floor on how far commands can collapse, and it is why the first simulation year is currently split more finely than later years.
- **Ordering within a merged command.** When two previously separate commands become one, execution order is resolved from the declared dependency graph rather than from the orchestrator's stage sequence. Any model whose correctness depends on the orchestrator's ordering — rather than on a declared dependency — will silently change behavior. This is the exact failure mode Tier C exhibited.
- **A merge looks correct at small scale.** Tier C passed parity at 7,500 employees and failed at 60,000. Small-scale parity is treated as non-evidence.
- **Setup work that is not a model build.** The run's setup includes non-model steps (loading reference data, preparing registries, refreshing cached lookup tables). These cannot always be folded into a model-building command, and any that cannot must remain separate rather than being forced.
- **Stage-scoped validation after a merge.** Validation rules and telemetry are currently attached to stage boundaries. Collapsing the commands behind two stages must not silently drop the validation attached to either.
- **Failure attribution after a merge.** A failure inside a merged command must still be traceable to a stage and year, or diagnosis regresses.
- **Runs that are not five years or not 60k.** Single-year runs, calibration runs, and small-census runs must all still work; the change alters command grouping, not run shape.

## Requirements *(mandatory)*

### Functional Requirements

#### Invocation reduction

- **FR-001**: The system MUST issue fewer transformation commands for the first simulation year than the current eight, while performing the same setup work.
- **FR-002**: The system MUST NOT build any model more than once within a single simulation year.
- **FR-003**: The system MUST issue exactly two transformation commands per simulation year after the first (down from three).
- **FR-004**: The system MUST leave the event-generation and state-accumulation commands' internal composition unchanged; they already amortize startup acceptably and are out of scope.
- **FR-005**: The system MUST preserve full-rebuild semantics for every model that requires them — a model fully rebuilt today MUST still be fully rebuilt after regrouping.

#### Correctness gate (mandatory, applies to every change under this feature)

- **FR-006**: Every regrouping change MUST clear a row-level difference check in **both directions** (before-minus-after and after-minus-before) across **every mart table**, comparing duplicate multiplicities as well as distinct rows. This reuses the gate established for Feature 121 rather than defining a new one.
- **FR-007**: The compared mart set MUST be **enumerated from the project at run time**, not hardcoded in the harness, so a newly added mart is covered automatically and cannot be silently omitted. Coverage of the full mart set is itself a pass condition.
- **FR-008**: The parity check MUST be run at **60,000-employee scale**, over the **full five-year horizon** rather than a single year. Parity at smaller scales or shorter horizons MUST NOT be accepted as sufficient evidence.
- **FR-009**: The parity check MUST exclude only non-deterministic audit fields: record-creation, snapshot-creation, and cache-build timestamps, and the per-run provenance tables (whose timestamps and correlation identifiers differ by construction). All other columns MUST match exactly.
- **FR-010**: The parity comparison MUST be a self-baselined A/B on the same code revision and configuration — one run before the change and one after — so the gate does not depend on a historical recorded baseline being current.
- **FR-011**: The candidate MUST also pass a **determinism re-run**: two candidate runs with the same seed and configuration MUST themselves compare clean, so a passing A/B cannot be an artifact of coincidental run-to-run variation.
- **FR-012**: A regrouping change that fails the parity gate MUST be abandoned or reverted, not adjusted until it passes at a smaller scale or against a narrower table set.
- **FR-013**: The parity gate MUST be run locally before merge rather than in continuous integration, and its full output — per-mart counts in both directions, the enumerated mart set, and the determinism re-run result — MUST be committed as an artifact under the feature directory so a reviewer can inspect the evidence rather than take the result on trust.

#### Observability and diagnosis

- **FR-014**: Stage-level validation rules MUST continue to execute after commands are merged, even when a stage no longer issues a command of its own.
- **FR-015**: Per-stage telemetry and progress reporting MUST continue to be emitted, so a merged command does not present to the user as a single opaque step.
- **FR-016**: A failure within a merged command MUST remain attributable to a simulation year and a recognizable stage.
- **FR-017**: The system MUST record the finalized command schedule for a run, so command count is verifiable after the fact rather than inferred from logs.

#### Measurement

- **FR-018**: Each step MUST be measured on the same reference workload (five years, 60,040 employees, Studio-shaped configuration) as the step before it.
- **FR-019**: Each measurement MUST report command count, total wall time, and the split between startup, analytical execution, and orchestration time.
- **FR-020**: Timing claims MUST be based on a median of at least three runs, not a single sample.

### Key Entities

- **Command schedule**: The ordered set of transformation commands a run issues, with the year and stage each belongs to. The primary object this feature reduces, and the artifact against which command-count requirements are verified.
- **Reference workload**: The fixed measurement subject — five simulation years, 60,040 employees, Studio-shaped configuration — held constant so successive measurements are comparable.
- **Parity result**: The outcome of the bidirectional, duplicate-preserving row-level comparison across every mart table at 60k scale over five years, plus the determinism re-run. The gate every change must clear.
- **Step record**: The recorded measurement plus keep/revert/stop decision for one step in the sequence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Success is judged **per step**, not as a single combined target. Each step is independently kept or reverted, so a partial outcome — Story 1 kept, Story 2 reverted on parity grounds — is an expected and successful result, not a failed feature.

#### Per-step bars

- **SC-001**: **Story 1**, if kept, reduces reference-workload wall time by at least **3 seconds** against the freshly captured pre-change campaign (median of three runs).
- **SC-002**: **Story 2**, if kept, reduces reference-workload wall time by at least a further **6 seconds**, measured against the state after Story 1 (median of three runs).
- **SC-003**: A step that does not clear its bar is **reverted**, and the feature is still considered successful provided the reversion is recorded with its measurement.

#### Feature-level

- **SC-004**: Every kept step cleared its bar, and every reverted or abandoned step has a recorded measurement and an explicit decision. This is the feature's completion condition.
- **SC-005**: Simulation results are **unchanged**: zero differing rows in either direction across **every** mart table at 60k scale over the full five-year horizon, excluding audit-timestamp and per-run provenance fields. This applies to each kept step and is not subject to any per-step tradeoff.
- **SC-006**: Total transformation commands for the reference five-year run drops from **20 to 14 or fewer** if both steps are kept, or to **18 or fewer** if only Story 1 is kept. This target is derived from the full-rebuild floor described in Assumptions, not chosen independently of it.
- **SC-007**: The measured wall-time reduction is at least **9 seconds** if both stories are kept, or at least **3 seconds** if only Story 1 is kept. The `dbt wall − model execution` residual is reported for diagnosis but is not treated as removable startup cost.
- **SC-008**: No simulation year builds any model more than once.
- **SC-009**: Diagnostic quality is preserved: an induced failure in any merged command is still reported with its simulation year and stage.

## Assumptions

- **Self-baselined parity removes the dependency on a current recorded baseline.** The originating issue notes a dependency on a companion baseline question. This spec assumes parity is established by running the same revision and configuration before and after the change, which makes the gate valid regardless of whether any previously recorded baseline is stale. The companion baseline work is useful context but not a blocker.
- **The accepted historical starting point is 102.7s**, the median of 18 prior 20-command runs. The feature's fresh 103.576s median confirms it. The issue's 91.5s figure is rejected as unreproducible and internally inconsistent.
- **The full-rebuild constraint sets a hard floor of roughly 3–4 first-year setup commands.** Rebuild instructions apply per command, not per model, so the first year's setup cannot collapse below the number of distinct rebuild groups it contains (currently a reference-data load, two separate full-rebuild groups, and the incremental remainder). Total command count is bounded by this floor, which is why `SC-006` targets 14 rather than a lower number. If planning finds a way to honor `FR-005` with fewer groups, the target can tighten.
- **Non-model setup steps may remain separate commands.** Reference-data loading and cached-lookup refresh use a different command form than model building; where they cannot be folded without changing rebuild semantics, they stay as they are, and the reduction target is met from the model-building commands.
- **The two well-amortized later-year commands are out of scope.** Event generation and state accumulation already spend most of their wall time on real work; merging them further is not pursued.
- **Steps ship independently.** Story 1 can merge and release without Story 2. If Story 2 fails its parity gate, Story 1's gain is retained.
- **A step that misses its bar is reverted.** If a step's median-of-three falls short of its per-step target (`SC-001`, `SC-002`), it is reverted rather than kept, since every regrouping carries residual correctness risk that a marginal gain does not pay for.
- **All measurement and parity runs use isolated per-run databases.** The shared development database is never built into for this work.
- **The 60,000-employee census is generated, not stored.** The largest census in the repository is ~7,500 records; the reference workload is produced by scaling it up. The gate therefore depends on that generation step being reproducible and on the same generated census being used for both sides of every A/B.
- **Orchestration and analytical execution time are explicitly out of scope** and are tracked separately. Historical component estimates are not used as performance bars.

## Out of Scope

- Reducing SQL execution or compilation time.
- Reducing orchestration time outside the transformation tool.
- Replacing the transformation tool, adopting a long-lived server process, or any compiled-execution approach.
- Changing what any model computes, any model's schema, or any simulation semantics.
- Changing run shape (year counts, scenario counts, parallelism).
