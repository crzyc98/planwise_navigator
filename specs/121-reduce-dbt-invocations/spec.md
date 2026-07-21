# Feature Specification: Reduce Production-Path dbt Invocations — Batch the Five-Year Studio Run Schedule

**Feature Branch**: `121-reduce-dbt-invocations`
**Created**: 2026-07-21
**Status**: Draft
**Input**: User description: "https://github.com/crzyc98/planwise_navigator/issues/478"

## Overview

This is a **run-cost optimization** of the canonical production simulation path, not a change to what a simulation produces. The measured evidence (from the run-cost profile, issue #455 / PR #464) is unambiguous: on the real Studio → API → `planalign simulate` path, a 2025–2029 run over ~60,000 employees spends **174.47s** of wall time issuing **62 dbt invocations**, yet no individual model exceeds ~0.93s and the DC-plan model curves are modest. The dominant fixed cost is therefore **repeated invocation/process/parse/orchestration overhead**, not SQL computation.

The goal is to cut that fixed overhead by **batching dependency-compatible model selections** and **eliminating no-op or redundant invocations**, taking the five-year invocation count from **62 to 32 or fewer**, while preserving exactly: simulation results, event ordering, transaction boundaries, determinism, model-level diagnostics, and the one-database-per-scenario isolation rule.

This is deliberately scoped **away** from SQL tuning: the profile showed per-model execution is already cheap, so DC-plan or workforce SQL MUST NOT be touched unless production-path timing names a specific slow node. The optimization is a schedule-consolidation problem, and its ship decision turns on an evidence gate — a ≥20% median warm wall-time improvement; if the full consolidation misses that bar, the measured evidence goes to the maintainer for an explicit ship / no-ship call rather than an automatic outcome.

**Hypothesis under test**: consolidating the invocation schedule reclaims a large share of the fixed overhead with zero change to outputs, because the overhead is per-invocation, not per-model.

## Clarifications

### Session 2026-07-21

- Q: If the ≥20% warm wall-time improvement is not met for the full consolidation, what ships? → A: Do not auto-decide — stop and escalate to the maintainer, presenting the measured before/after evidence, and obtain an explicit ship / no-ship decision at that point (recorded in the ship decision record).
- Q: Which output tables must byte-match (identical row multisets) between baseline and candidate to prove no behavioral change? → A: Every `fct_*` and `dim_*` mart table.
- Q: What peak-RSS increase counts as a "material" regression that disqualifies a consolidation? → A: More than 10% over the baseline peak RSS.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Faster Studio simulation with identical results (Priority: P1)

An analyst launches a five-year simulation from Studio using a realistic plan-design config over a full-size census. The run completes materially faster than before, and every number in the resulting workforce snapshot, event stream, and match/contribution output is exactly what the prior version produced for the same config and seed.

**Why this priority**: the entire point of the feature is faster runs on the path analysts actually use, with no behavioral change. If results shift at all, the optimization is a regression regardless of speed; if speed doesn't improve, there is nothing to ship.

**Independent Test**: run the same Studio-shaped config and seed against an isolated database before and after the change; confirm the after-run's authoritative outputs match the before-run's row-for-row (modulo documented audit-timestamp fields) and that warm median wall time is lower.

**Acceptance Scenarios**:

1. **Given** a Studio-realistic five-year config and fixed seed, **When** the simulation is run before and after the change against isolated databases, **Then** every `fct_*` and `dim_*` mart table matches exactly in schema and row multiset (including duplicate multiplicities), except for documented audit-timestamp fields.
2. **Given** three warm repetitions of the same run each way, **When** their wall times are compared, **Then** the median-of-three warm wall time after the change is at least 20% lower than before.
3. **Given** the same config run twice after the change, **When** the two output sets are compared, **Then** they are identical (determinism preserved).

---

### User Story 2 - Consolidated invocation schedule with preserved pipeline semantics (Priority: P2)

The maintainer inspects the sequence of orchestration invocations a five-year production run issues and finds it has been consolidated from 62 to 32 or fewer, with repeated single-model setup/hazard calls batched, zero-node and ephemeral-only calls removed, and the standalone parameter-resolution call folded into a compatible selection — all without reordering the accumulator → events → snapshot build sequence or crossing a required transaction boundary.

**Why this priority**: the invocation-count reduction is the mechanism that produces the P1 speedup, and it is only safe if the consolidations respect dbt dependency order and the pipeline's transaction/event-ordering guarantees. It is P2 because it is verifiable independently of the timing outcome.

**Independent Test**: capture the exact production invocation schedule before and after with the corrected profiling harness; confirm the count is ≤32 (or a published safe floor), that each removed invocation selected nothing executable, and that the accumulator → events → snapshot ordering is unchanged.

**Acceptance Scenarios**:

1. **Given** the corrected production-path harness, **When** it records the five-year invocation schedule after the change, **Then** the invocation count is 32 or fewer (or matches a stricter evidence-based safe floor published during planning).
2. **Given** each invocation eliminated as no-op, **When** its selection is inspected, **Then** it is shown to select only ephemeral or zero executable nodes.
3. **Given** any consolidated state-accumulation selection, **When** its build order is examined, **Then** every accumulator is built before the events that read it and before the snapshot that reads those events (semantics preserved).
4. **Given** the repeated hazard/setup calls and the standalone parameter-resolution call, **When** the post-change schedule is inspected, **Then** they appear as batched or folded selections rather than separate invocations, wherever dependencies allowed.

---

### User Story 3 - Preserved diagnostics, invariants, and failure semantics (Priority: P3)

When something goes wrong inside a now-batched selection — a model errors, a stage fails, a year is re-run over existing output — the maintainer still gets the same quality of signal as before: the failure names the specific model, stage, and year; multi-year invariants still hold; and re-running a completed year still behaves correctly.

**Why this priority**: batching many models into one invocation risks blurring which model failed and risks breaking rerun/failed-stage handling. Preserving these guarantees is what makes the consolidation shippable rather than a debuggability regression. It is P3 because it protects the change rather than delivering the headline value.

**Independent Test**: inject a model failure inside a batched selection and confirm the reported error still identifies model, stage, and year; run the determinism, multi-year-invariant, rerun-on-existing-output, and failed-stage suites and confirm all remain green.

**Acceptance Scenarios**:

1. **Given** a model that fails inside a batched selection, **When** the run errors, **Then** the surfaced error identifies the failing model, its stage, and the simulation year.
2. **Given** the existing determinism, multi-year-invariant, rerun-on-existing-output, and failed-stage test suites, **When** they are run after the change, **Then** all pass.
3. **Given** a run that stops after a completed year, **When** that year is re-executed over its existing output, **Then** the rerun semantics are unchanged from before the optimization.

---

### Edge Cases

- **Consolidation would cross a transaction boundary or reorder events**: such a consolidation MUST be rejected — events must be committed before the snapshot reads them. Correctness always wins over invocation count.
- **A "no-op" invocation actually selects an executable node under some config**: before removing any invocation, confirm it selects nothing executable across both the minimal/reference and Studio-realistic configs — an invocation empty under one config may not be under another.
- **Batching raises peak memory**: folding more models into one process can increase peak RSS. If peak RSS rises more than 10% above baseline, the consolidation that caused it MUST be reconsidered rather than shipped.
- **The 20% improvement is not met**: the outcome is not automatic — present the measured before/after evidence to the maintainer and obtain an explicit ship / no-ship decision (recorded in the ship decision record) rather than defaulting either way. Any consolidations still shipped after that decision must independently satisfy every correctness, determinism, and semantics requirement.
- **A model-level failure disappears into a batch**: if consolidation makes a failure's model/stage/year unidentifiable, that consolidation is not acceptable as-is.
- **Config-dependent schedule**: the minimal/reference config and the Studio-realistic config may produce different schedules; both must be measured and both must pass all correctness checks.
- **Shared dev database contamination**: every behavioral run uses an isolated database and run-scoped artifacts; the shared development database MUST remain byte-unchanged.
- **A specific slow node appears**: if — and only if — production-path timing names a specific slow model, SQL-level attention to that node is in scope; otherwise SQL is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Baseline and candidate measurements MUST run through the canonical production construction seam (the same path Studio → API → `planalign simulate` uses) with the exact Studio-shaped config and census workload — not a bespoke or simplified harness.
- **FR-002**: The corrected production-path profiling harness MUST capture the exact five-year invocation schedule (baseline and candidate) so the invocation count and its reduction are directly measured, not estimated.
- **FR-003**: A five-year production run MUST issue **32 or fewer** dbt invocations, down from the measured 62 — OR planning MUST publish a stricter, evidence-based safe floor before implementation, and the run MUST meet that published floor.
- **FR-004**: Repeated single-model hazard/setup invocations MUST be batched into dependency-compatible combined selections wherever dbt dependency order permits.
- **FR-005**: Invocations that select only ephemeral nodes or zero executable nodes MUST be eliminated, after confirming (across both tested configs) that they select nothing executable.
- **FR-006**: The standalone parameter-resolution invocation (`int_effective_parameters`) MUST be folded into a compatible existing selection rather than issued as its own invocation.
- **FR-007**: State-accumulation selections MUST be consolidated ONLY where dbt dependency order preserves accumulator → events → snapshot semantics. Any consolidation that would reorder these stages or violate a transaction boundary MUST NOT be made.
- **FR-008**: Transaction boundaries and event ordering on the production path MUST be preserved exactly.
- **FR-009**: Simulation outputs MUST be exactly preserved: for **every `fct_*` and `dim_*` mart table**, the schema and the full row multiset (including duplicate multiplicities) MUST match the baseline, with the sole exception of explicitly documented audit-timestamp fields.
- **FR-010**: Determinism MUST be preserved: an identical config and seed MUST produce identical events and outputs before and after the change, and across repeated post-change runs.
- **FR-011**: The existing multi-year-invariant, rerun-on-existing-output, and failed-stage suites MUST remain green after the change.
- **FR-012**: Model-level failure context and stage/year telemetry MUST remain available after consolidation — a failure inside a batched selection MUST still identify the failing model, stage, and year.
- **FR-013**: Both the minimal/reference configuration and the Studio-realistic configuration MUST pass all correctness, determinism, and semantics checks.
- **FR-014**: Every behavioral run in this effort MUST execute against an isolated database with run-scoped dbt artifacts; the shared development database (`dbt/simulation.duckdb`) MUST NOT be written or otherwise altered.
- **FR-015**: Peak memory (peak RSS) MUST NOT increase by more than **10%** versus the baseline peak RSS; a consolidation that exceeds this ceiling is disqualified.
- **FR-016**: After each consolidation tier, subprocess launch cost, dbt command wall time, model execution time, and non-dbt residue MUST be measured separately, so the source of any improvement or regression is attributable.
- **FR-017**: The median-of-three **warm** Studio-shaped wall time is the ship gate, with a target of at least a **20%** improvement versus baseline. If the full consolidation does not reach 20%, the outcome MUST NOT be auto-decided: the maintainer MUST be presented with the measured before/after evidence and MUST make an explicit ship / no-ship decision, which is recorded in the ship decision record.
- **FR-018**: Before/after artifacts MUST be captured for both baseline and candidate, including: invocation count, dbt command wall time, internal execution time, measurement residue, CPU time, peak RSS, config and census fingerprints, and the construction signature.
- **FR-019**: SQL for DC-plan or workforce models MUST NOT be modified unless production-path timing names a specific slow node; this feature is a schedule-consolidation change, not a query-tuning change.

### Key Entities

- **Invocation schedule**: the ordered sequence of dbt invocations a five-year production run issues, with each entry's selection, stage, and year; the primary object being consolidated. Baseline count is 62; target is ≤32.
- **Consolidation tier**: one applied batch of related consolidations (e.g., "batch the repeated hazard/setup calls"), measured independently so its effect on invocation count, wall time, and peak RSS is isolated.
- **Before/after run-cost artifact**: the recorded measurement set for a run — invocation count, command wall, internal execution, residue, CPU, peak RSS, config/census fingerprints, construction signature — used to prove the reduction and guard against regressions.
- **Correctness comparison**: the row-multiset and schema comparison between baseline and candidate authoritative outputs, including duplicate multiplicities and the documented audit-timestamp exemptions.
- **Ship decision record**: the recorded outcome of the ship gate. If the ≥20% warm-wall-time target is met, the consolidation ships; if not, the maintainer is presented the before/after evidence and makes an explicit ship / no-ship call, which is recorded here alongside the evidence it rests on.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A five-year Studio-shaped production run issues **32 or fewer** orchestration invocations (down from 62 — at least a 48% reduction), or meets a stricter evidence-based safe floor published during planning.
- **SC-002**: The median-of-three warm Studio-shaped run's improvement versus the pre-change baseline is measured and reported; a ≥20% improvement is the target that ships automatically. If it falls short, the maintainer is given the before/after evidence and records an explicit ship / no-ship decision rather than an automatic outcome.
- **SC-003**: The candidate run's outputs match the baseline exactly — for every `fct_*` and `dim_*` mart table, identical schema and row multiset (including duplicate multiplicities) — with only documented audit-timestamp fields exempt.
- **SC-004**: The determinism, multi-year-invariant, rerun-on-existing-output, and failed-stage suites all pass after the change.
- **SC-005**: An injected model failure inside a batched selection still surfaces an error that names the failing model, its stage, and the simulation year.
- **SC-006**: Peak RSS after the change is no more than 10% above the baseline peak RSS.
- **SC-007**: Both the minimal/reference and Studio-realistic configurations pass every correctness, determinism, and semantics check.
- **SC-008**: The shared development database (`dbt/simulation.duckdb`) is byte-identical before and after the entire effort.
- **SC-009**: For every headline claim (invocation count, wall-time improvement, peak RSS), a before/after artifact exists containing the invocation count, command wall, internal execution, residue, CPU, peak RSS, config/census fingerprints, and construction signature that substantiates it.

## Assumptions

- The corrected production-path baseline (issue #455 / PR #464) and the canonical construction seam (issue #477) are in place and are the reference this feature builds and measures against.
- The resolved quadratic `fct_yearly_events` deletion fix (issue #465 / PR #466) is present; this feature does not re-address that SQL and assumes it as a prerequisite.
- "Warm" wall time excludes first-run one-time costs (process/parse caches, OS file cache); the first repetition is discarded or labeled separately, consistent with the run-cost profile methodology.
- The ≤10% peak-RSS ceiling and the "compare every `fct_*`/`dim_*` mart" correctness scope are confirmed decisions (see Clarifications, Session 2026-07-21), not open defaults.
- Documented audit-timestamp exemptions are the inherently time-varying fields (run/audit timestamps, correlation IDs, run-metadata rows) that legitimately differ between two runs of identical logic; all other fields must match exactly.
- The Studio-realistic config and full census used for measurement are representative of production workloads (≈60,000 employees, five-year horizon), matching the profiled baseline.
- A 62 → 32 target is the headline objective; a stricter safe floor, if published during planning, supersedes it only by being more conservative (fewer invocations is acceptable; regressing correctness to hit a number is not).

## Dependencies

- Corrected production-path baseline: issue #455 / PR #464.
- Canonical orchestrator construction seam: issue #477 (feature 120).
- Prerequisite SQL fix for the quadratic `fct_yearly_events` deletion: issue #465 / PR #466.
- The run-cost profile and its go/no-go methodology: feature 116 (issue #455 / Roadmap 1/8), which established that orchestration overhead — not SQL — is the target.

## Out of Scope

- Any change to simulation results, event semantics, or plan-design behavior.
- SQL-level tuning of DC-plan or workforce models, unless production-path timing names a specific slow node.
- Building a compiled/alternative execution engine (a separate roadmap track); this feature stays within the existing dbt-invocation model and only reduces how many invocations are issued.
- Changes to the shared development database or to non-production entry points beyond preserving their behavior.
