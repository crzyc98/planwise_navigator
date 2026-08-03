# Feature Specification: Seed Ensembles — Distribution Bands, Exceedance Risk, and Variance Attribution

**Feature Branch**: `133-seed-ensemble-bands`
**Created**: 2026-08-03
**Status**: Draft
**Input**: GitHub issue #460 (expands and supersedes #441). Dependency correction of 2026-07-20: depends on #455 (corrected production-path baseline), #477 (canonical construction), #478 (accepted per-run cost), #457 (bounded scenario fan-out). #456 is no longer a dependency; a native candidate evaluator from #469 may improve later versions but is not a prerequisite unless the revised #471 spike receives a GO decision.

## Why

A deterministic point estimate of 2030 employer cost is a liability in front of a sophisticated client: it invites the question "how confident are you?" and the honest answer today is unquantified. Every headline number should be a **distribution** — a band, an exceedance probability, and a ranked statement of which assumption drives the spread.

The determinism architecture already makes this *correct*: each seed is an exact, reproducible world, so an ensemble of seeds is a legitimate sample of stochastic outcomes rather than an artifact of nondeterminism. What was missing was run volume (now solved by bounded scenario fan-out) and presentation. This feature supplies both.

## Clarifications

### Session 2026-08-03

- Q: What does the "total employer cost" headline metric mean? → A: Plan cost only — employer match + employer core contributions. Total compensation remains a separate headline metric.
- Q: Where does attribution's unfrozen baseline come from? → A: Paired with reuse — attribution seeds must be a subset of the headline seed list; matching headline runs are reused as the baseline when seed *and* configuration fingerprint both match, otherwise the baseline run is executed.
- Q: What happens below the minimum successful-seed count? → A: Publish per-seed values and a record explicitly flagged as an insufficient sample, with percentile fields left empty rather than computed. No band-shaped number is ever produced from a thin sample.
- Q: Where is the ensemble aggregate written? → A: A dedicated ensemble database at a predictable, timestamped path alongside the per-seed databases, holding the aggregate and provenance only. No per-seed database is promoted to primary or mutated after its run.
- Q: Which percentile convention? → A: Linear interpolation between the two bracketing order statistics, matching the default of standard analysis tooling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Headline numbers become bands (Priority: P1)

An analyst preparing a client deck runs a five-year scenario with 25 seeds instead of one. Instead of a single 2029 employer-cost figure, they get a P10/P50/P90 band per year for each headline metric, stored in the ensemble's result database and printed as a table at the end of the run. They can now say "our central estimate is $2.1M, with a 10–90 range of $1.9M to $2.3M" and defend it.

**Why this priority**: This is the irreducible core. Bands alone change what the analyst can claim in front of a client. Exceedance statements and attribution are refinements on top of a distribution that must exist first.

**Independent Test**: Run an ensemble of N seeds against a small census in an isolated database and confirm the distribution table contains one row per (scenario, metric, year), with percentiles that bracket the per-seed values, and that the printed table matches the stored values.

**Acceptance Scenarios**:

1. **Given** a valid multi-year scenario configuration, **When** the analyst requests an ensemble of 25 seeds, **Then** the system executes 25 isolated single-seed runs and produces a distribution record for every headline metric and every simulated year, each carrying P10/P25/P50/P75/P90, mean, standard deviation, and the number of contributing seeds.
2. **Given** a completed ensemble, **When** the analyst re-runs it with the same seed list and configuration, **Then** the aggregated distribution values are identical to the previous run's, value for value.
3. **Given** a completed ensemble, **When** the analyst inspects the result, **Then** the seed list, the location of each per-seed result, and the aggregation provenance are recorded alongside the distributions.
4. **Given** an ensemble request, **When** the analyst does not specify seeds explicitly, **Then** the system derives the seed list deterministically from the scenario's configured base seed and reports the derived list before execution begins.

---

### User Story 2 - Probability of blowing the budget (Priority: P2)

A plan sponsor has a stated budget ceiling for the plan's cost to the employer. The analyst attaches thresholds to the scenario, and the ensemble reports, per year, the share of seeds that exceeded each threshold: "P(total employer plan cost > $2.4M in 2028) = 12%." This converts a band into a decision-relevant risk statement.

**Why this priority**: This is the statement the client actually acts on, but it is a thin derivation over the P1 distribution data and is useless without it.

**Independent Test**: Configure a threshold deliberately below the observed minimum and another above the observed maximum for a metric, run the ensemble, and confirm the reported exceedance probabilities are 100% and 0% respectively, with intermediate thresholds matching a hand count of per-seed values.

**Acceptance Scenarios**:

1. **Given** one or more configured thresholds on headline metrics, **When** an ensemble completes, **Then** the system reports for each threshold and year the fraction of seeds whose value exceeded it, together with the seed count that fraction is computed from.
2. **Given** a threshold configured on a metric the scenario does not produce, **When** the ensemble runs, **Then** the system reports the threshold as not evaluable and names the missing metric, rather than silently omitting it or reporting zero.
3. **Given** no thresholds are configured, **When** an ensemble completes, **Then** distributions are still produced and the risk section is reported as empty rather than failing the run.

---

### User Story 3 - What actually drives the spread (Priority: P3)

Having seen a wide band on employer plan cost, the analyst asks *why*. They request variance attribution and get a ranked table: freezing termination draws removes 61% of the variance in 2029 employer plan cost; freezing hire sampling removes 22%; enrollment and opt-out draws remove 9%. The analyst now knows which assumption to interrogate with the client.

**Why this priority**: Highest analytical value per unit of client trust, but the most expensive (it multiplies run volume) and the most dependent on the other two. It is the right thing to ship last and to gate behind an explicit request.

**Independent Test**: Construct a scenario in which one stochastic subsystem is configured to be effectively deterministic (e.g. a zero-rate subsystem) and confirm attribution ranks it at or near zero variance contribution, while a subsystem with a high rate ranks high.

**Acceptance Scenarios**:

1. **Given** an ensemble request that asks for attribution, **When** the run completes, **Then** the system reports, per headline metric and year, a ranked list of stochastic subsystems with the share of observed variance attributable to each, covering at minimum termination draws, hire sampling, and enrollment/opt-out draws.
2. **Given** an attribution run, **When** a single subsystem's draws are held fixed across seeds, **Then** all other subsystems' draws still vary exactly as they do in the unfrozen baseline at the same seed, so the measured variance reduction is attributable to the frozen subsystem alone.
5. **Given** a headline ensemble has already run at the attribution seeds under an unchanged configuration, **When** attribution is requested, **Then** the system reuses those runs as its baseline and executes only the frozen runs, reporting how many baseline runs were reused.
6. **Given** a headline run exists at an attribution seed but under a different configuration, **When** attribution is requested, **Then** the system executes a fresh baseline run for that seed rather than reusing the mismatched one.
3. **Given** attribution results, **When** the shares are inspected, **Then** each share is reported with its own seed count, and the report states plainly that shares are computed one factor at a time and need not sum to 100%.
4. **Given** an attribution run is requested, **When** the analyst reviews the plan before execution, **Then** the system states the total number of simulation runs the request implies, before spending them.

---

### User Story 4 - Bands travel to the client deliverable (Priority: P3)

The analyst exports batch results to a workbook and hands it to a colleague. The workbook contains a distribution sheet and, when attribution was run, an attribution sheet — so the uncertainty story survives leaving the terminal.

**Why this priority**: Delivery matters, but it is mechanical once the data exists, and the printed table already unblocks the analyst.

**Independent Test**: Run a batch with ensembles enabled, export, and confirm the workbook's distribution rows match the stored values.

**Acceptance Scenarios**:

1. **Given** a completed ensemble in a batch run, **When** results are exported to a workbook, **Then** the workbook contains a distribution sheet whose values match the stored distributions, and an attribution sheet when attribution was run.
2. **Given** an export of a batch where ensembles were not used, **When** the workbook is produced, **Then** the existing sheets are unchanged and no empty distribution sheet is added.

### Edge Cases

- **A seed run fails.** The ensemble must not silently aggregate a partial sample. The system reports how many seeds succeeded, withholds percentiles when survivors fall below the minimum viable sample, and names the failed seeds with their failure reason.
- **N = 1.** A single seed is not a distribution. It is recorded as an insufficient sample with no percentiles — never a band, and never a zero-spread record that could be mistaken for one.
- **Very small N (2–4).** Percentiles from four points are barely meaningful, so below the configured minimum none are computed; the per-seed values are still written so the analyst keeps the work. Above the minimum, the seed count accompanies every band so the reader can discount it.
- **Duplicate seeds in an explicit seed list.** Duplicates double-count an identical world and understate spread. The system rejects the list, naming the repeated seeds, rather than silently de-duplicating — a seed list that does not mean what it says is a provenance problem, and the ensemble size the user asked for would not match what ran.
- **Disk exhaustion.** N isolated databases multiply storage. The system estimates the footprint before starting and can discard per-seed databases after aggregation on request, retaining the aggregate and provenance.
- **Interruption mid-ensemble.** Cancelling leaves no orphaned worker processes and no half-written aggregate; partial state is either discarded or clearly labelled incomplete.
- **A metric is absent from the result set** (e.g. a scenario with the DC plan disabled produces no match cost). Absent metrics are reported as absent, not as zero.
- **Attribution requested with too few seeds to resolve signal from noise.** The system warns that shares are not resolvable at that sample size rather than presenting noise as a ranking.

## Requirements *(mandatory)*

### Functional Requirements

**Ensemble execution**

- **FR-001**: Users MUST be able to request an ensemble of N seeds for a multi-year simulation from the primary command-line interface and from the batch interface, using the same option name and semantics in both.
- **FR-002**: The system MUST execute each seed as a fully isolated single-seed run — one result database per seed — preserving the existing one-database-per-run isolation invariant.
- **FR-003**: The system MUST submit seed runs through the existing bounded run pool, so ensemble concurrency respects the same memory and CPU budgets as scenario fan-out and remains safe on a work laptop.
- **FR-004**: The system MUST resolve the complete seed list, and all configuration for every seed run, before any worker starts, so results never depend on scheduling order.
- **FR-005**: The system MUST derive seeds deterministically from the scenario's configured base seed when an explicit seed list is not supplied, and MUST accept an explicit seed list when supplied.
- **FR-006**: The system MUST report progress across the ensemble (seeds completed, running, failed) while it executes.
- **FR-007**: The system MUST support cancellation that terminates all in-flight seed runs and leaves no orphaned subprocesses.

**Aggregation**

- **FR-008**: After all seed runs complete, the system MUST aggregate per-seed results into a distribution record set keyed by scenario, metric, and simulation year, containing P10, P25, P50, P75, P90, mean, standard deviation, and the contributing seed count.
- **FR-009**: The aggregate MUST cover at minimum these headline metrics: active headcount, total compensation, employer match cost, total employer plan cost, plan participation rate, and average deferral rate.
- **FR-009a**: "Total employer plan cost" MUST mean employer match plus employer core contributions — the plan's cost to the employer, gross of forfeitures. Total compensation is a separate headline metric and MUST NOT be folded into it.
- **FR-010**: Percentiles MUST be computed by linear interpolation between the two bracketing order statistics, and this convention MUST be applied identically everywhere a percentile is reported, so the printed table, the stored aggregate, and the export never disagree.
- **FR-010a**: Because an interpolated percentile need not equal any observed seed's value, the system MUST NOT present a percentile as attributable to a specific seed or run.
- **FR-011**: The aggregate MUST be written into a dedicated ensemble database created for the ensemble, at a predictable path alongside the per-seed databases. It MUST NOT be written into the shared development database, and MUST NOT be written into any per-seed database.
- **FR-011a**: No per-seed database may be designated primary, mutated, or written to after its run completes. Per-seed databases are read-only inputs to aggregation.
- **FR-011b**: The ensemble database path MUST be discoverable by convention from the ensemble's location, so export and downstream tooling can locate the aggregate without being handed an explicit path, and MUST be reported to the user at the end of the run.
- **FR-012**: Aggregation MUST be reproducible: given the same seed list, configuration, and inputs, re-running the ensemble MUST produce identical aggregate values.
- **FR-013**: When the number of successful seeds falls below a configured minimum, the system MUST NOT compute or publish percentiles. It MUST still write the per-seed values and a distribution record whose percentile fields are empty and which is explicitly flagged as an insufficient sample, and MUST report which seeds failed and why.
- **FR-013a**: An empty percentile field MUST be distinguishable from a computed value of zero in every output medium — stored record, printed table, and export alike.
- **FR-013b**: A single-seed ensemble (N=1) MUST be treated as an insufficient sample under FR-013, never as a distribution with zero spread.
- **FR-013c**: An insufficient-sample record MUST be excluded from exceedance probabilities and from variance attribution, rather than contributing a thin or degenerate estimate to either.

**Risk statements**

- **FR-014**: Users MUST be able to configure one or more thresholds, each naming a headline metric and a value.
- **FR-015**: For each configured threshold and each simulated year, the system MUST report the proportion of successful seeds whose value exceeded the threshold, together with the seed count.
- **FR-016**: The system MUST report a threshold naming an unavailable metric as not evaluable, identifying the metric.

**Variance attribution**

- **FR-017**: Users MUST be able to request one-factor-at-a-time variance attribution as an explicit opt-in, separate from requesting bands.
- **FR-018**: The system MUST support holding a single stochastic subsystem's draws fixed across all seeds in an ensemble while every other subsystem continues to vary, for at minimum termination draws, hire sampling, and enrollment/opt-out draws. Merit draws SHOULD be included where that subsystem's randomness is separable.
- **FR-019**: For each supported subsystem, the system MUST measure the reduction in variance of each headline metric when that subsystem is frozen, relative to an unfrozen baseline computed over the *same seed list*, and report the results as a ranked table per metric and year. Frozen and baseline runs MUST be paired seed-for-seed, so that for any given seed the two runs differ only in the frozen subsystem.
- **FR-019a**: The attribution seed list MUST be a subset of the headline ensemble's seed list. Where a headline run exists for an attribution seed, the system MUST reuse it as the baseline run rather than re-executing it; where none exists, the system MUST execute the baseline run.
- **FR-019b**: The system MUST NOT reuse a headline run as a baseline unless both its seed and its effective configuration fingerprint match the attribution run's. A seed match alone is insufficient. On any mismatch the system MUST execute a fresh baseline run rather than reusing.
- **FR-019c**: The attribution report MUST state, per subsystem, how many baseline runs were reused and how many were freshly executed, so a reader can see what the comparison rests on.
- **FR-020**: The attribution report MUST state its method and its limits: that shares are measured one factor at a time, that they need not sum to 100%, and the seed count each share was measured from.
- **FR-021**: The system MUST state the total number of simulation runs an attribution request implies before executing it.
- **FR-022**: Freezing a subsystem MUST NOT alter any other subsystem's draw sequence, and an unfrozen attribution ensemble MUST reproduce exactly the results of a plain ensemble at the same seeds.

**Provenance and presentation**

- **FR-023**: The system MUST record, with the aggregate, the seed list, the location of each per-seed result, the effective configuration fingerprint, the aggregation provenance, and whether attribution was run — using the existing run-metadata mechanism.
- **FR-024**: The system MUST print a distribution table and, when thresholds are configured, a risk-statement section at the end of an ensemble run.
- **FR-025**: Workbook export MUST include a distribution sheet, and an attribution sheet when attribution was run, without altering existing sheets or adding empty sheets when ensembles were not used.
- **FR-026**: Every reported band and share MUST carry its contributing seed count, so no number is presentable without the sample size behind it.
- **FR-027**: The system MUST warn when the successful-seed count is below the configured minimum, explaining that percentiles were withheld and naming the count required, without failing the run or discarding the per-seed results.
- **FR-028**: Users MUST be able to request that per-seed databases are discarded after successful aggregation, retaining the ensemble database, the aggregate, and the provenance. The system MUST state that discarding forfeits baseline reuse (FR-019a) for any later attribution run, which will then execute its own baseline runs.

### Key Entities

- **Ensemble**: One scenario configuration plus an ordered seed list, executed as N isolated runs. Identified by scenario, configuration fingerprint, and seed list.
- **Seed run**: A single, exactly reproducible simulated world — one seed, one isolated result database, one entry in the ensemble's provenance record.
- **Metric distribution** (`fct_metric_distributions`): The aggregate record — scenario, metric, simulation year, P10/P25/P50/P75/P90, mean, standard deviation, contributing seed count, and a sufficiency flag. Percentile fields are empty, and distinguishable from zero, when the sample is insufficient (FR-013).
- **Per-seed metric value**: One metric's value for one seed and year — the evidence a distribution summarizes, retained so percentiles can be independently recomputed and so an insufficient sample still yields usable output.
- **Risk statement**: A configured threshold (metric, value) paired with a per-year exceedance proportion and the seed count behind it.
- **Attribution result**: A stochastic subsystem paired with the share of a metric's variance in a given year attributable to it, plus the seed count and the frozen-subsystem identifier.
- **Stochastic subsystem**: A named source of randomness whose draws can be held fixed independently — termination, hiring, enrollment/opt-out, merit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can turn any existing single-run scenario into a banded result by adding one option, with no other change to the scenario's configuration.
- **SC-002**: Re-running an ensemble with the same seed list and configuration reproduces every aggregate value exactly, verified by comparing two independent ensemble runs.
- **SC-003**: Reported percentiles match an independent linear-interpolation recomputation from the per-seed values, for every headline metric and year, with no discrepancy in any cell.
- **SC-004**: Exceedance probabilities are exact: a threshold below every observed value reports 100%, above every observed value reports 0%, and intermediate thresholds match a direct count of per-seed values.
- **SC-005**: A 25-seed, five-year ensemble completes on a work laptop without exhausting memory, respecting the same concurrency budget as scenario fan-out.
- **SC-006**: Variance attribution ranks a deliberately dominant stochastic subsystem first and ranks a subsystem configured to be effectively deterministic at or near zero, on a purpose-built test scenario.
- **SC-007**: Freezing one subsystem leaves all other subsystems' results unchanged, verified by comparing an unfrozen attribution ensemble against a plain ensemble at the same seeds — the results are identical.
- **SC-011**: A baseline run reused from a headline ensemble produces the same attribution shares as a freshly executed baseline run at the same seed and configuration, verified by running attribution both ways and comparing.
- **SC-012**: Reuse never crosses a configuration boundary: an attribution run following a configuration change executes fresh baseline runs and reports zero reused, verified on a scenario whose configuration is altered between the headline ensemble and the attribution request.
- **SC-008**: Every band, probability, and attribution share presented in any output medium is accompanied by the number of seeds it was computed from — no exceptions.
- **SC-009**: A failed seed never silently reduces the sample: failure counts and reasons appear in the output of every ensemble containing one.
- **SC-013**: No band-shaped number is ever produced from a sample below the configured minimum, verified by running ensembles at N=1 and just under the minimum and confirming every percentile field is empty and flagged, in stored output, printed output, and export alike.
- **SC-010**: An interrupted ensemble leaves no running worker processes and no aggregate that appears complete.

## Assumptions

- **Ensemble result location.** Each ensemble creates a timestamped directory holding one database per seed plus one dedicated ensemble database for the aggregate and provenance (FR-011). This keeps the project's isolated-database rule intact — no run shares a database, and no completed run is mutated — while giving the aggregate a location that export and downstream tooling can find by convention. The shared development database is never an ensemble target.
- **Per-seed retention.** Per-seed databases are retained by default — they are the evidence behind the bands, and the reuse rule in FR-019a depends on them — and discarded only on explicit request (FR-028). Discarding them never removes the ensemble database or its provenance.
- **Seed derivation.** Derived seeds are a deterministic function of the configured base seed and the ensemble size, so a given base seed and N always yield the same seed list.
- **Attribution sample size and cost.** Attribution defaults to a seed count K no larger than the headline ensemble's N, drawn as a subset of the headline seed list (FR-019a). With four subsystems it costs 4K frozen runs, plus baseline runs only for seeds the headline ensemble does not already cover — typically zero when attribution follows a headline ensemble, and K when it is run standalone. The default K is chosen to keep a typical attribution request inside a single working session, and the implied run count is always stated before execution (FR-021).
- **Minimum viable sample.** The minimum successful-seed count for computing percentiles is a configured value, not a hard-coded constant, defaulting to roughly ten. Below it, percentiles are withheld (FR-013); above it, bands are published and carry their seed count.
- **Percentile convention.** Linear interpolation (FR-010), chosen so that a value spot-checked in standard analysis tooling agrees with the published one. The tradeoff accepted: a published percentile generally corresponds to no single simulated world, so "show me the run behind this number" is answerable for per-seed values but not for a band edge.
- **Metric definitions are inherited, not invented.** Headline metrics reuse the definitions already used by existing summary and export paths, so an ensemble median at N=1 equals the corresponding single-run figure. Total employer plan cost (FR-009a) reuses the existing combined employer-contribution measure rather than defining a new one.
- **Presentation ordering.** Printed table and workbook export ship first. Interactive band charts in the web studio are explicitly a follow-up and do not gate this feature.

## Dependencies

- **#455** — corrected production-path baseline; ensemble cost estimates are meaningless against a phantom baseline.
- **#477** — canonical construction; every seed run must be constructed identically, differing only in seed.
- **#478** — accepted per-run cost; N-run volume is only tolerable at the accepted per-run cost.
- **#457** — bounded scenario fan-out; the ensemble runner submits to that run pool rather than building a second concurrency mechanism.
- **#469 / #471** — a native candidate evaluator may improve later versions but is not a prerequisite, and becomes relevant only if the revised #471 spike receives a GO decision.
- **#441** — superseded. This feature subsumes seed ensembles; #441 closes when this lands.

## Concerns

- **The premise that per-subsystem RNG streams already exist is not accurate.** Randomness today flows from a single global seed value threaded into hash expressions scattered across many event-generation models and macros; there is no per-subsystem stream that can simply be pinned. Delivering FR-018 therefore requires introducing per-subsystem seed derivation that defaults to today's behavior exactly — a change touching many models, which must be proven to produce identical results at default settings before attribution can be trusted. This is the largest risk in the feature and the reason attribution is P3 rather than P1. It does not change the scope requested; it changes where the effort lands.
- **Cost compounds multiplicatively.** Headline bands cost N runs; attribution costs N plus one ensemble per subsystem. The run-count disclosure requirement (FR-021) exists so this is never discovered halfway through an afternoon.

## Out of Scope (v1)

- Distributions over *parameters* — uncertainty inherited from parameter fitting. That is a later marriage of this feature with the fitting work.
- Global sensitivity analysis (Sobol indices or similar). One-factor-at-a-time is sufficient to *rank* drivers, which is the decision this feature supports.
- Interactive band charts in the web studio. A follow-up; explicitly not a blocker.
- Correlations or joint distributions between metrics.
