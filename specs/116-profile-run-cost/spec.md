# Feature Specification: Run-Cost Profile — Orchestration Overhead vs Computation (Go/No-Go for Compiled Execution)

**Feature Branch**: `116-profile-run-cost`
**Created**: 2026-07-17
**Status**: Draft
**Input**: User description: "Profile multi-year simulation run cost: quantify dbt orchestration overhead vs DuckDB SQL execution time, produce a written breakdown and a go/no-go recommendation for building a compiled execution mode (GitHub issue #455, Roadmap 1/8)"

## Overview

This is a **measurement-and-decision feature**, not a product change. Its deliverable is a written, evidence-backed answer to one question: *where does the wall-clock time of a multi-year simulation actually go — tool orchestration overhead, or data computation?* The answer decides whether the platform invests in a compiled execution mode (Roadmap issue #456, projected 10–30× speedup) or redirects that effort to computation-level optimization.

The entire downstream roadmap (plan-design optimizer, seed ensembles, backtesting) is gated on per-run cost: at ~150 seconds per multi-year run, workloads needing hundreds of runs are impractical. One day of disciplined measurement prevents weeks of misdirected engineering.

**Hypothesis under test**: the majority of run time is per-invocation orchestration overhead (process startup, project parsing, template compilation across ~156 models × N years, single-threaded), not the underlying analytical computation. The profile must confirm or refute this with numbers.

## Clarifications

### Session 2026-07-17

- Q: Which decision rule should the report be held to (FR-007 thresholds)? → A: Keep defaults — GO if orchestration overhead ≥ 60% of full-census wall time AND probe ≥ 3× on its stage; NO-GO if overhead ≤ 40%; 40–60% band requires explicit written judgment. Confirmed by maintainer; no longer provisional.
- Q: Two census sizes (dev + tiny fixture) or add a larger client-scale point? → A: Maintainer is unsure but has observed that larger real censuses take much longer to run. Resolved as: measure **three sizes** (tiny fixture, dev census, large client-representative census), because the observation implies computation scales with population — so the overhead *share* is size-dependent and the go/no-go must be evaluated at the size the roadmap workloads will actually run (the largest point), not only the dev census.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evidence-backed go/no-go decision (Priority: P1)

The maintainer reads a short report and can decide — without re-running anything or trusting intuition — whether building a compiled execution engine is justified. The report states the measured split between orchestration overhead and computation, a projected speedup range with its assumptions spelled out, and an explicit GO or NO-GO recommendation against pre-stated decision criteria.

**Why this priority**: the decision is the entire point of the feature; every measurement exists to support it. A profile without a recommendation leaves the roadmap blocked.

**Independent Test**: read the report cold; verify every claim in it traces to a recorded measurement, the decision criteria were stated before the recommendation, and the recommendation follows mechanically from the numbers.

**Acceptance Scenarios**:

1. **Given** all measurements are complete, **When** the report is written, **Then** it contains a wall-time breakdown table, a projected speedup range with stated assumptions, and a single GO / NO-GO recommendation referencing pre-stated thresholds.
2. **Given** the measured overhead share and probe results, **When** they are applied to the decision criteria, **Then** the recommendation follows from the criteria without judgment calls left implicit.
3. **Given** the report recommends GO, **When** issue #456 is picked up, **Then** the report's projected speedup range and its assumptions are usable as that feature's success baseline.

---

### User Story 2 - Wall-time attribution across census sizes (Priority: P2)

The maintainer sees the same multi-year simulation timed against three census sizes — a tiny (~100-employee) fixture, the development census, and a large client-representative census — in isolated databases, with total wall time split into per-invocation orchestration cost versus reported model computation time at each size. This produces an **overhead-share-vs-size curve**: the maintainer has observed that larger real censuses take much longer to run, which implies computation scales with population and the overhead share shrinks with size — so the share must be known at the size real workloads run, not just at dev scale.

**Why this priority**: this is the most robust signal available and it feeds the P1 decision directly; the size curve is what makes the decision valid at client scale rather than only on the dev census.

**Independent Test**: run the same simulation configuration against all three census sizes and confirm total wall times and the overhead/computation split are captured at each size, with repeat runs showing the spread.

**Acceptance Scenarios**:

1. **Given** identical simulation configuration and horizon, **When** run against each of the three census sizes in isolated databases, **Then** total wall time for each size is recorded from at least 3 repetitions with the spread reported.
2. **Given** the per-model execution timings recorded by the toolchain during a run, **When** aggregated across all invocations and years, **Then** the report shows total wall time decomposed into orchestration overhead vs model computation, and the two components plus measurement residue account for the full wall time (residue ≤ 10%).
3. **Given** the number of orchestration invocations in one simulated year, **When** multiplied by the measured fixed cost of a minimal invocation, **Then** the estimated fixed overhead is consistent with the decomposition above (same order, stated explicitly).

---

### User Story 3 - Direct-execution headroom probe (Priority: P3)

The maintainer sees a concrete demonstration of the achievable ceiling: for at least one representative pipeline stage of one simulation year, the already-compiled model queries are executed directly against the database (bypassing the orchestration tool), producing equivalent results, and the stage wall time is compared with the standard path.

**Why this priority**: it converts the projected speedup from arithmetic into observed evidence, and de-risks issue #456 by proving the compiled queries are directly executable. It is P3 because Stories 1–2 can justify a decision without it in the extreme (e.g., overhead measured at 90%+).

**Independent Test**: execute one stage both ways against copies of the same starting database state; compare row counts/results and wall time.

**Acceptance Scenarios**:

1. **Given** a mid-simulation database state and the compiled queries for one stage, **When** the stage is executed directly versus through the standard path, **Then** both produce equivalent target-table contents (row counts and spot-checked values) and both wall times are recorded.
2. **Given** the probe's measured stage speedup, **When** extrapolated across all stages and years, **Then** the extrapolation method and its assumptions appear in the report alongside the resulting full-run projection.

---

### Edge Cases

- **Tiny census breaks models**: a ~100-employee population may produce empty cohorts or zero-row event years that error or skew timings. Use the existing multi-year test census already proven to run (the invariant-suite fixture); if a model still fails, record it and time the surviving portion rather than abandoning the comparison.
- **Run-to-run variance**: laptop thermal/background load can swamp small differences. Repetitions (≥3) with spread reported; if spread exceeds the effect being measured, the report must say so rather than present a false precision.
- **Warm vs cold caches**: first runs pay one-time costs (parsing caches, OS file cache). Discard or separately label the first repetition.
- **Shared dev database contamination**: all measurement runs go to isolated databases per the project's isolated-DB rule; the shared dev database is never written.
- **Large-census run budget**: the client-representative census makes each repetition materially slower (per the maintainer's observation). If 3 repetitions of the large size don't fit the time budget, reduce repetitions for that size only (minimum 2) and label its spread accordingly — never silently drop the size point, since it is the decision-grade one.
- **No real client census available**: if no client-scale census can be used directly, generate a synthetic one by scaling the development census (duplicating with perturbed identifiers/demographics); the report must note that synthetic scaling preserves size but not necessarily demographic mix.
- **Probe result divergence**: if direct execution produces different results than the standard path, that is itself a critical finding (hidden orchestration-tool semantics) and must be documented — it materially raises the risk estimate for issue #456 regardless of speed results.
- **Hypothesis refuted**: if computation dominates, the report must still be complete — the NO-GO path redirects effort and is an equally valid outcome.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All measurement runs MUST execute against isolated databases; the shared development database MUST NOT be written by any part of this work.
- **FR-002**: The profile MUST time the same multi-year simulation (3-year horizon) against three census sizes — the tiny (~100-employee) fixture census, the full development census, and a large client-representative census (roughly 5–10× the development census, or matched to the largest census observed in real use) — with at least 3 repetitions each (large size: minimum 2, labeled — see Edge Cases) and the spread (min/median/max) reported, and MUST present the orchestration-overhead share as a function of census size.
- **FR-003**: The profile MUST decompose total wall time into (a) orchestration overhead and (b) model computation time, using the toolchain's own recorded per-model timings, and the decomposition plus unattributed residue MUST account for total wall time within 10%.
- **FR-004**: The profile MUST measure the fixed cost of a minimal orchestration invocation and count invocations per simulated year, as an independent cross-check of the overhead estimate.
- **FR-005**: The profile MUST execute at least one pipeline stage of one simulation year directly against the database using the pre-compiled queries, verify result equivalence with the standard path (row counts and spot-checked values), and record both wall times.
- **FR-006**: The deliverable MUST be a written report containing: the breakdown tables, the census-size comparison, the probe result, a projected full-run speedup range with every assumption stated, and a GO / NO-GO recommendation.
- **FR-007**: The decision criteria MUST be stated in the report before the results are applied to them. Confirmed criteria (Session 2026-07-17): **GO** if orchestration overhead ≥ 60% of wall time AND the probe demonstrates ≥ 3× on its stage; **NO-GO** (redirect to computation-level optimization) if overhead ≤ 40%; between 40–60%, the recommendation must weigh the probe result and say which way and why. The overhead share is evaluated at the **large client-representative census** (the size roadmap workloads will actually run); shares at the other sizes are reported as context. If the recommendation differs by census size (e.g., GO at dev scale, NO-GO at client scale), the report MUST say so explicitly and recommend per scale. Deviating from these thresholds requires written justification in the report itself.
- **FR-008**: Every reported number MUST be reproducible: the report links the scripts/commands and configurations used, such that re-running them regenerates the same tables (modulo timing variance).
- **FR-009**: The measurement work MUST NOT change simulation behavior: no product code changes that alter results; any instrumentation added must be read-only with respect to simulation outputs.
- **FR-010**: The report MUST state the hardware/environment it was measured on, and note that projections transfer to other hardware only directionally.

### Key Entities

- **Run-cost profile report**: the single deliverable document; contains breakdown tables, comparison results, probe outcome, speedup projection with assumptions, decision criteria, and the recommendation. Lives with the project's documentation.
- **Timing sample**: one repetition of one measured configuration — census size, horizon, repetition index, total wall time, per-component times, environment note.
- **Decision record**: the GO / NO-GO outcome plus the criteria it was evaluated against; referenced by roadmap issue #456 (if GO) or a redirect issue (if NO-GO).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader can answer "what share of a run is orchestration overhead, at which census size?" with numbers and a stated uncertainty, directly from the report, in under 5 minutes of reading — including the client-representative size the decision turns on.
- **SC-002**: The overhead/computation decomposition accounts for ≥ 90% of measured total wall time at each measured census size.
- **SC-003**: Every headline number is backed by ≥ 3 repetitions with spread shown; no single-run numbers are presented as conclusions.
- **SC-004**: The report contains exactly one recommendation (GO or NO-GO), and it follows from decision criteria that appear earlier in the same document.
- **SC-005**: If GO: the report provides a projected full-run speedup range (e.g., "8–20×") with each assumption listed, usable as the acceptance baseline for the compiled-execution feature. If NO-GO: the report names the top 3 computation hotspots as the redirected optimization targets.
- **SC-006**: All measurement artifacts (scripts, configs) are committed and re-runnable; a second run of the harness regenerates the report's tables without manual editing.
- **SC-007**: The shared development database is byte-identical before and after the entire measurement campaign.

## Assumptions

- A 3-year horizon (e.g., 2025–2027) is representative of production multi-year runs; longer horizons scale the same per-year structure.
- The tiny census is the existing ~100-employee fixture census already used by the multi-year invariant/determinism suite (Feature 113), which is known to survive a full multi-year run.
- The overhead share is size-dependent (maintainer observation: larger real censuses run much longer), so the development census alone is **not** assumed representative of client scale — hence the three-size matrix with the decision evaluated at the largest size.
- Measurements on the primary development machine (macOS laptop) are decision-grade: the go/no-go turns on the overhead *share* (a ratio), which transfers across hardware far better than absolute times.
- The toolchain's own per-model timing records (its run artifacts) are trustworthy for the computation component; no external profiler is required for the decision.
- Effort scale is roughly 1–2 days (the third census size adds generation and run time to the original 1-day estimate); the feature does not include building any reusable profiling infrastructure beyond the scripts needed to regenerate the report.
- Existing open issue #455 is the source of record for context; this spec supersedes its method sketch where they differ.

## Dependencies

- **Blocks**: Roadmap issue #456 (compiled execution mode) — explicitly gated on this report's recommendation. Informs #457 (parallel fan-out) sizing.
- **Depends on**: the Feature 113 fixture census and the existing simulation CLI; no new product capabilities are required.

## Out of Scope

- Any performance *improvement* work — this feature only measures and decides.
- Profiling of the web Studio, API, batch export, or calibration paths (the multi-year simulation path is the one that gates the roadmap).
- Building a permanent, general-purpose benchmarking framework.
- Cross-platform (Linux/Windows) measurement.
