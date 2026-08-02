# Feature Specification: Backtest Scorecard

**Feature Branch**: `131-backtest-scorecard`
**Created**: 2026-08-01
**Status**: Draft
**Input**: GitHub issue [#459](https://github.com/crzyc98/planwise_navigator/issues/459) — "Backtest harness: score fitted parameter packs against held-out census history." Depends on #458 (fitted parameter packs).

## Overview

A projection is only as trustworthy as its track record. Today an analyst can fit a parameter pack from a client's census history (#458) and run a projection, but nothing tells them — or the client — whether that fitted model would have predicted the years the client already lived through.

This feature adds a **backtest**: hold out the most recent one or two census snapshot years, fit the model on the earlier years only, simulate forward across the held-out span, and score what the simulation predicted against what actually happened. The output is a **scorecard** shipped with the parameter pack, so every projection built on that pack can be introduced as "the model, which reproduced your last N years within X%."

The scorecard makes honest point comparisons. It is not a statistical validation framework, and it does not claim confidence it has not earned.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Score a fitted model against held-out history (Priority: P1)

An analyst has 4 annual census snapshots from a client. They run a backtest against that directory. The system fits parameters on the first 3 snapshot years, starts a simulation from the last fitted year's census, projects through the held-out year, and reports — per metric — what the model predicted, what actually happened, and the error.

**Why this priority**: This is the feature. Without it there is no credibility artifact at all. Everything else refines the presentation or the confidence of this one number set.

**Independent Test**: Point the backtest command at a snapshot directory with ≥3 consecutive annual snapshots and confirm it produces a scorecard reporting predicted vs. actual for at least headcount and average compensation, without touching the shared development database.

**Acceptance Scenarios**:

1. **Given** a directory with snapshots for 2021–2024, **When** the analyst runs a backtest with the default holdout, **Then** the system fits on 2021–2023, simulates 2024, and reports predicted vs. actual for 2024.
2. **Given** the same directory, **When** the analyst requests a 2-year holdout, **Then** the system fits on 2021–2022, simulates 2023 and 2024, and reports each held-out year separately plus a cumulative row.
3. **Given** a snapshot directory with only 2 snapshots, **When** the analyst runs a backtest, **Then** the system refuses with a message stating that a backtest needs at least 3 snapshots (2 to fit, 1 to hold out) and does not produce a partial scorecard.
4. **Given** a completed backtest, **When** the analyst inspects the simulation databases used, **Then** each is an isolated per-run database and the shared development database is unmodified.

---

### User Story 2 - Read the scorecard and know whether to trust the model (Priority: P1)

The analyst opens the scorecard and, without reading code or querying a database, can see which metrics the model reproduced acceptably and which it missed. Each metric carries an absolute error, a percentage error, and a pass/warn/fail marker against a stated threshold. The thresholds themselves are printed on the scorecard, so a reader knows what "pass" meant.

**Why this priority**: A scorecard nobody can interpret is not a credibility artifact. The scoring and its presentation ship together or the feature has no user.

**Independent Test**: Run a backtest and confirm the human-readable scorecard states, for every scored metric, predicted value, actual value, absolute error, percent error, threshold applied, and status — and that a metric outside its threshold is visibly marked.

**Acceptance Scenarios**:

1. **Given** a completed backtest where predicted headcount is within 1% of actual and average compensation is off by 6%, **When** the analyst reads the scorecard, **Then** headcount shows as passing and average compensation shows as failing its stated threshold.
2. **Given** a census that carries no deferral-rate or enrollment columns, **When** the analyst reads the scorecard, **Then** the plan metrics are listed as **not observable in the source census** rather than scored as zero or omitted silently.
3. **Given** custom thresholds supplied by the analyst, **When** the scorecard is produced, **Then** the thresholds section reflects the supplied values and the pass/warn/fail markers are computed against them.
4. **Given** a completed backtest, **When** a downstream tool reads the machine-readable scorecard, **Then** it finds the same metrics, errors, thresholds, and statuses as the human-readable version, under a documented schema with a schema version.

---

### User Story 3 - See where the actuals fall in the seed spread (Priority: P2)

Because the simulation is stochastic, a single run's error mixes model error with random variation. The analyst runs the backtest across a small set of random seeds and the scorecard reports, per metric, the spread across seeds and where the actual value sits relative to that spread — inside the range, or outside it and by how much.

**Why this priority**: It separates "the model is wrong" from "that run was unlucky," which is the first question a skeptical reviewer asks. It is not required for the scorecard to be useful, so it follows P1.

**Independent Test**: Run a backtest with a multi-seed setting and confirm the scorecard reports a per-metric spread across seeds and an explicit statement of whether the actual value falls within it.

**Acceptance Scenarios**:

1. **Given** a backtest configured for 3 seeds, **When** it completes, **Then** the scorecard reports, per metric, the range across the 3 seed runs and whether the actual value falls inside that range.
2. **Given** a backtest configured for a single seed, **When** it completes, **Then** the scorecard reports point errors and states that no seed spread was computed, rather than reporting a degenerate zero-width range as meaningful.
3. **Given** a multi-seed backtest, **When** it is re-run with the same inputs and the same seed set, **Then** every reported number is identical.

---

### User Story 4 - Trust the harness itself (Priority: P2)

Before believing a scorecard about a client's data, a reviewer needs to know the harness is not systematically biased. The system provides a self-test: history generated by the simulator itself, fitted and backtested through the same path, must score near-perfect. A large error there indicts the harness, not the model.

**Why this priority**: It is what makes the other scorecards admissible evidence. It is a test asset rather than an analyst-facing workflow, so it sits below the analyst stories.

**Independent Test**: Generate snapshot history from a simulation run with known parameters, run the backtest over it, and confirm every scored metric lands inside a tight self-test tolerance.

**Acceptance Scenarios**:

1. **Given** census history produced by the simulator with known parameters, **When** the backtest runs over it, **Then** headcount and compensation errors fall inside the documented self-test tolerance.
2. **Given** a defect deliberately introduced into the comparison logic, **When** the self-test runs, **Then** it fails — the self-test detects harness error rather than passing unconditionally.

---

### User Story 5 - Carry the score forward as provenance (Priority: P3)

The backtest result is attached to the parameter pack it scored. When a projection later runs on that pack, the provenance chain is complete and auditable: which census files (by content hash) were fitted, what pack came out, what that pack scored on backtest, and which runs used it.

**Why this priority**: The chain matters at review time rather than at authoring time, and it is only valuable once scorecards exist and are believed.

**Independent Test**: Run a fit, run a backtest, run a projection with the pack, and follow the chain from recorded run provenance back to the scorecard and to the source census content hashes without manual bookkeeping.

**Acceptance Scenarios**:

1. **Given** a backtest of a pack, **When** it completes, **Then** the scorecard is stored with that pack and identifies the pack by its identifier and fingerprint.
2. **Given** a pack that has been backtested, **When** a projection runs using that pack, **Then** the run's recorded provenance lets a reviewer reach the scorecard for that pack.
3. **Given** a scorecard, **When** a reviewer inspects it, **Then** it names every source snapshot with its content hash, which snapshot years were fitted, and which were held out.
4. **Given** a pack whose seeds or configuration fragment were altered after the backtest, **When** a reviewer inspects the scorecard against the pack, **Then** the mismatch is detectable rather than silently presented as a current score.

---

### Edge Cases

- **Too few snapshots**: fewer than 3 usable snapshots, or a holdout that would leave fewer than 2 snapshots to fit, is rejected up front with a message naming the counts involved.
- **Non-consecutive snapshot years**: a gap in the annual sequence is rejected, consistent with the fitter's existing requirement.
- **Requested holdout larger than supported**: a holdout beyond the supported maximum of 2 years is rejected rather than silently clamped.
- **Held-out census missing a scored column**: metrics that depend on it are reported as not observable; the rest are still scored.
- **Employee population churn**: employees present in the actual held-out census but never derivable from the starting census (and vice versa) are handled as aggregate population differences, not as record-level match failures — scoring is on aggregates, not per-employee identity.
- **Actual value of zero**: percentage error against a zero actual is reported as undefined rather than as infinity or a division error; the absolute error is still reported.
- **A simulation run fails mid-backtest**: the backtest fails loudly, naming the seed and year that failed, and does not emit a scorecard scored on a partial run.
- **Interrupted backtest**: isolated run databases and any partial artifacts are identifiable as incomplete; a partially written scorecard is never presented as complete.
- **Plan metrics observable in some snapshot years but not others**: each held-out year reports observability independently rather than the whole metric being dropped.
- **Re-running a backtest on a pack that already has one**: the previous scorecard is replaced only on an explicit overwrite; otherwise the command refuses rather than quietly discarding prior evidence.

## Requirements *(mandatory)*

### Functional Requirements

**Backtest execution**

- **FR-001**: The system MUST provide a backtest operation that takes a directory of historical census snapshots and produces a scorecard end to end, without further analyst intervention.
- **FR-002**: The system MUST split the snapshot set into a fitting portion and a held-out portion, holding out the most recent 1 year by default and supporting a holdout of 2 years on request.
- **FR-003**: The system MUST fit parameters using **only** the fitting portion — no data from a held-out year may influence the fitted parameters, directly or indirectly.
- **FR-004**: The system MUST reject a backtest whose split would leave fewer than 2 snapshots to fit or fewer than 1 snapshot held out, stating the counts involved.
- **FR-005**: The system MUST start the backtest simulation from the census of the last fitted snapshot year and project forward across exactly the held-out years.
- **FR-006**: The system MUST run every backtest simulation in an isolated database and MUST NOT read from or write to the shared development database.
- **FR-007**: The system MUST run the backtest simulation over a configurable set of random seeds, defaulting to 3, supporting 1 through 5.
- **FR-008**: The system MUST produce identical scorecard values when re-run with the same snapshots, holdout, seed set, and thresholds.

**Scored metrics**

- **FR-009**: The system MUST score, for each held-out year, total headcount and headcount broken out by job level, age band, and tenure band.
- **FR-010**: The system MUST score, for each held-out year, total compensation and average compensation.
- **FR-011**: The system MUST score, for each held-out year, termination counts, hire counts, and promotion counts.
- **FR-012**: The system MUST score participation rate, average deferral rate, and employer match cost for each held-out year **when** the corresponding fields are present in that year's census, and MUST report them as not observable when they are absent.
- **FR-013**: The system MUST report, in addition to per-year figures, a cumulative figure across all held-out years for each scored metric.
- **FR-014**: The system MUST derive actual values solely from the held-out census snapshots and predicted values solely from the backtest simulation output, using the same band definitions on both sides so the comparison is like-for-like.

**Error presentation**

- **FR-015**: The system MUST report, per metric and per held-out year, the predicted value, the actual value, the absolute error, and the percentage error.
- **FR-016**: The system MUST assign each scored metric a pass / warn / fail status against a configurable threshold, defaulting to 2% for headcount metrics and 3% for compensation metrics, with documented defaults for the remaining metrics.
- **FR-017**: The system MUST state the thresholds in effect on the scorecard itself, including any the analyst overrode.
- **FR-018**: The system MUST report percentage error as undefined, rather than erroring or reporting an infinite value, when the actual value is zero.
- **FR-019**: The system MUST present an overall verdict summarizing the per-metric statuses, and MUST NOT let a failing verdict suppress the underlying detail.

**Seed spread**

- **FR-020**: When more than one seed is run, the system MUST report per metric the spread of predicted values across seeds and whether the actual value falls within that spread.
- **FR-021**: The system MUST identify which single predicted value each headline error is computed from, and MUST use the same choice consistently across all metrics and years.
- **FR-022**: When only one seed is run, the system MUST state that no seed spread was computed rather than presenting a zero-width spread as a result.

**Artifacts and provenance**

- **FR-023**: The system MUST write a human-readable scorecard and a machine-readable scorecard containing the same results, both stored alongside the parameter pack that was scored.
- **FR-024**: The system MUST document the machine-readable scorecard's schema, including a schema version field that changes when the structure changes incompatibly.
- **FR-025**: The scorecard MUST record every source snapshot with its content hash, which snapshot years were fitted, which were held out, the seed set used, and the identifier and fingerprint of the scored parameter pack.
- **FR-026**: The system MUST make a mismatch detectable between a scorecard and a parameter pack whose contents changed after the backtest ran.
- **FR-027**: The system MUST record, in the provenance of any simulation run that uses a backtested pack, enough information for a reviewer to reach that pack's scorecard.
- **FR-028**: The system MUST NOT alter the parameter pack's fitted contents or its fingerprint as a side effect of backtesting it.
- **FR-029**: The system MUST refuse to overwrite an existing scorecard for a pack unless overwriting is explicitly requested.

**Trust in the harness**

- **FR-030**: The system MUST include an automated self-test that backtests history generated by the simulator itself and asserts near-perfect scores within a documented tolerance.
- **FR-031**: The project MUST include a documented reference example of a backtest over a real or realistically anonymized census, with its scorecard, as the worked illustration of the feature.

**Failure behavior**

- **FR-032**: The system MUST fail the whole backtest, naming the failing year and seed, if any constituent simulation run fails, and MUST NOT emit a scorecard derived from a partial run.
- **FR-033**: The system MUST report progress during a backtest, since it runs multiple multi-year simulations and can take substantial time.

### Key Entities

- **Snapshot set**: the consecutive annual census files supplied by the analyst, each identified by year, row count, and content hash. Split by the backtest into a fitting portion and a held-out portion.
- **Backtest configuration**: the holdout length, the seed set, and the metric thresholds in effect for one backtest.
- **Parameter pack**: the fitted parameters produced from the fitting portion, identified by pack identifier and fingerprint. It is the subject of the score.
- **Metric comparison**: one scored metric for one held-out year (or cumulative) — predicted value, actual value, absolute error, percentage error, threshold, status, observability, and seed spread.
- **Scorecard**: the complete set of metric comparisons for one backtest, plus the thresholds, overall verdict, seed set, and the full provenance chain from snapshot hashes through pack to score. Exists in a human-readable and a machine-readable form carrying identical results.
- **Run provenance record**: the existing per-run record that already carries parameter-pack identity, extended so a run using a backtested pack points at its score.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst with a directory of 3 or more annual census snapshots can obtain a complete scorecard in a single command, with no manual database, configuration, or file handling steps.
- **SC-002**: 100% of backtest runs execute against isolated databases; the shared development database is unchanged across a backtest, verified automatically.
- **SC-003**: Every scored metric on the scorecard carries a predicted value, an actual value, an absolute error, a percentage error, a stated threshold, and a status — with no blank or unexplained cells; metrics the census cannot support are explicitly labeled unobservable.
- **SC-004**: The self-test over simulator-generated history scores every headcount and compensation metric inside its documented near-perfect tolerance, and fails when the comparison logic is deliberately broken.
- **SC-005**: Re-running an identical backtest twice produces identical machine-readable scorecards.
- **SC-006**: A reviewer given only a projection's run provenance can reach the source census content hashes through the pack and its scorecard, with every link present and no manual bookkeeping.
- **SC-007**: The machine-readable scorecard schema is documented and versioned, and a consumer written against the documented schema reads a produced scorecard without inference.
- **SC-008**: A published reference example shows a real or realistically anonymized backtest end to end, including its scorecard.
- **SC-009**: Backtesting a pack leaves that pack's fitted contents and fingerprint unchanged, verified automatically.
- **SC-010**: Every rejection case — too few snapshots, year gaps, unsupported holdout, failed constituent run, existing scorecard — produces a message naming the specific cause and the values involved, and produces no partial scorecard.

## Assumptions

Recorded defaults chosen where the source issue left room, so the spec is testable without further input:

1. **Minimum snapshots**: a backtest needs at least 3 usable snapshots (2 to fit, 1 held out), because the fitter itself requires at least 2 consecutive snapshots to link cohorts.
2. **Holdout default and maximum**: 1 year by default, 2 at most, matching the issue's "last 1–2 snapshot years."
3. **Seeds**: 3 by default, 1 to 5 supported, run serially. Parallel execution across seeds is out of scope for this feature and may be adopted later without changing the scorecard.
4. **Headline predicted value**: the median across seeds is the single predicted value each headline error is computed from, with the full spread reported alongside. The median is robust to one unlucky run and is well defined for the odd default seed count.
5. **Comparison is aggregate**: scoring compares population aggregates per year, not individual employee records. Employee identifiers in a simulated future do not correspond to identifiers in an actual census.
6. **Actuals from census only**: actual termination, hire, and promotion counts are derived from the held-out snapshots by the same cohort-linking logic the fitter already uses, so both sides of the comparison share one definition of each transition.
7. **Threshold defaults**: 2% for headcount metrics, 3% for compensation metrics; remaining metric defaults are set during design and printed on the scorecard. A "warn" band sits between pass and fail so a near-miss is distinguishable from a real miss.
8. **Scorecard placement**: scorecards are written under the parameter pack directory in a location that is not covered by the pack's fitted-content fingerprint, so recording a score cannot change the pack's identity (FR-028) while still traveling with it.
9. **A failing scorecard does not block anything**: a projection using a backtested pack surfaces the score but is never prevented from running. The scorecard is evidence for a human, not a gate.
10. **Interface scope**: this feature delivers the command-line workflow and the stored artifacts. Surfacing scorecards in the web studio is explicitly deferred, per the source issue.
11. **Configuration for the backtest simulation**: apart from the fitted parameters and the starting census, the backtest runs under the project's standard simulation configuration; comparing alternative configurations is out of scope.

## Dependencies

- **Parameter fitting from census history (#458)** — the backtest calls the existing fitter and scores the pack it produces. This feature adds no new estimation logic.
- **Run provenance recording (Feature 109 / parameter-pack provenance)** — extended, not replaced, to carry the backtest score reference.
- Parallel scenario fan-out (#457) is **not** a dependency; seeds run serially and a later adoption of the pool must not change scorecard values.

## Out of Scope

- Statistical inference: confidence intervals, hypothesis tests, or calibration claims beyond honest point comparison and observed seed spread.
- Automatic re-fitting or parameter tuning driven by backtest error.
- Web studio presentation of scorecards.
- Cross-client or cross-pack benchmark comparison.
- Per-employee predicted-vs-actual reconciliation.
