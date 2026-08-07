# Feature Specification: Plan-Design Optimizer

**Feature Branch**: `135-plan-design-optimizer`
**Created**: 2026-08-07
**Status**: Draft
**Input**: User description: "Roadmap 7/8: Plan-design optimizer (#461) — invert the tool from a calculator an expert hand-drives one scenario at a time into a system that, given objectives and constraints, searches match formulas × auto-enrollment designs × eligibility × vesting and returns a ranked, auditable efficient frontier of candidate plan designs."

## Clarifications

### Session 2026-08-07

- Q: Is the run-budget cap mandatory on every optimizer invocation, or does the system apply a default cap if the user omits it? → A: Mandatory — every invocation must state a run-budget cap explicitly; the system refuses to start without one.
- Q: What scale of design space must v1 support, and does that rule out exhaustive grid search as the sole strategy? → A: Moderate — up to ~6-8 levers with mixed discrete/continuous ranges; exhaustive grid is impractical, so budget-bounded sampling (grid seeding + local refinement) is required, not optional.
- Q: Does percentile-based constraint evaluation require the user to explicitly set a percentile per constraint, or does the system auto-apply a default conservative percentile when ensemble data happens to be available? → A: Explicit only — percentile-based evaluation activates only when the user names a percentile for that constraint; otherwise always point-estimate, even if ensemble data exists.
- Q: For FR-012 duplicate-candidate dedup, how should two continuous-range lever values be treated as "the same" candidate? → A: Exact match only — two candidates are the same iff every declared lever's effective value is identical; continuous levers dedup in practice only when a search step revisits an exact prior point.
- Q: When a candidate scenario run fails outright (crashes/times out/no output), does the optimizer retry it automatically before recording "failed," or record failure on the first occurrence? → A: No retry — a candidate run failure is recorded as "failed" immediately on first occurrence and counts once against the run budget.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - State objectives and get a ranked frontier (Priority: P1)

A benefits consultant wants to know the cheapest plan design that hits a participation target, without hand-testing scenarios one at a time. They write a design-space spec naming which levers may vary (e.g. match formula tiers, auto-enrollment default rate) and their bounds, an objective ("minimize total employer plan cost"), and a hard constraint ("participation rate ≥ 85%"). They run the optimizer with a run budget and get back a ranked table of candidate designs: each with its config delta from baseline, its objective value, and whether it satisfied every constraint.

**Why this priority**: This is the core value proposition — without it there is no product. Every other story augments this one.

**Independent Test**: Can be fully tested by authoring a two-lever design-space spec (match tier rate, auto-enrollment default rate) with one objective and one constraint, running the optimizer with `--max-runs 20`, and confirming a non-empty ranked candidate table is produced where every candidate marked "feasible" actually satisfies the constraint when independently re-checked against its own scenario output.

**Acceptance Scenarios**:

1. **Given** a valid design-space spec with 2 searchable levers, one objective, and one constraint, **When** the user runs the optimizer with a run budget of 20, **Then** the system evaluates at most 20 candidate designs, each as an isolated scenario run, and returns a candidate table ranked by objective value among feasible candidates.
2. **Given** a completed optimizer run, **When** the user inspects any single candidate row, **Then** they can see its full config (as a delta from the baseline config) and re-run that exact candidate independently to reproduce the same result.
3. **Given** a design-space spec with two objectives specified as a tradeoff (not a single minimize/maximize target), **When** the optimizer completes, **Then** the output includes the Pareto-efficient subset of evaluated candidates, distinguished from dominated candidates.

---

### User Story 2 - Guardrails against runaway or misleading search (Priority: P1)

A plan sponsor's actuary needs to trust that a search won't silently run for hours or make a promise the numbers don't back up. They set `--max-runs 15` and expect the optimizer to stop at that hard cap and report its best-found candidate rather than continuing indefinitely, and they expect every candidate's constraint status to be reported honestly — including the case where the constraint spec itself is infeasible.

**Why this priority**: A search tool nobody can bound or trust is worse than the existing one-scenario-at-a-time workflow it replaces — this is a trust precondition for User Story 1, not an enhancement to it.

**Independent Test**: Can be fully tested by running a spec with `--max-runs 5` and an unreachable constraint (e.g. a cost ceiling below what any candidate in the declared design space can achieve), and confirming the run stops at exactly 5 evaluated candidates, reports no candidate as feasible, and names which constraint was never satisfied.

**Acceptance Scenarios**:

1. **Given** a design-space spec and `--max-runs N`, **When** the optimizer runs, **Then** it evaluates no more than N candidate scenarios and always reports a result (best-found-so-far), never an unbounded or silently-truncated search.
2. **Given** a spec whose constraints cannot be satisfied by any point in the declared design space, **When** the optimizer completes its budget, **Then** it reports zero feasible candidates and names the constraint(s) that were never satisfied, rather than presenting an infeasible candidate as a recommendation.
3. **Given** the same design-space spec and the same optimizer run seed, **When** the optimizer is run twice, **Then** both runs evaluate the same sequence of candidate configurations and produce the same ranked output.
4. **Given** a design-space spec, **When** the user inspects which config levers were touched, **Then** every lever not explicitly declared searchable remains pinned to the baseline config value in every candidate — no candidate silently varies an undeclared lever.

---

### User Story 3 - Export and drill down for client presentation (Priority: P2)

A consultant needs to bring optimizer results into a client conversation. They export the frontier and candidate table to a file they can attach to an email or walk through live, and for any candidate that catches a stakeholder's attention, they can open that candidate's full underlying scenario data to answer a follow-up question on the spot.

**Why this priority**: Without an exportable, drill-down-capable artifact, the optimizer's output is only usable inside a terminal session — this story is what makes the P1 capability usable in the actual client-facing workflow the tool exists for.

**Independent Test**: Can be fully tested by running a completed optimizer job, exporting its results, and confirming the export file contains every evaluated candidate's config delta, objective value, and constraint status, and that at least one candidate's underlying scenario database can be independently queried for full audit detail.

**Acceptance Scenarios**:

1. **Given** a completed optimizer run, **When** the user requests an export, **Then** they receive a file containing the full candidate table and (for two-objective specs) the Pareto frontier, in a format shareable outside the terminal.
2. **Given** a completed optimizer run, **When** the user wants to drill into one candidate's full detail, **Then** that candidate's underlying scenario data remains available and queryable after the optimizer run finishes, without needing to re-run anything.

---

### User Story 4 - Evaluate candidates against distributional risk, not a single point estimate (Priority: P3)

A risk-conscious plan sponsor doesn't want a design that looks cheap on one lucky draw of workforce turnover to later blow through budget. When ensemble data is available for the objective/constraint metrics, they want constraint satisfaction checked at a conservative percentile (e.g. a cost ceiling must hold at the 90th percentile outcome, not just the median), so a recommended design is defensible under realistic variability, not just a single deterministic run.

**Why this priority**: This is a credibility multiplier on top of the core search (P1/P2) rather than something the tool is unusable without — it is valuable once ensembles exist for a given metric, but the optimizer must work correctly without it too.

**Independent Test**: Can be fully tested by running the optimizer twice on the same spec — once evaluating constraints at the median and once at a stated conservative percentile — and confirming the second run marks strictly no more candidates as feasible than the first (a design that fails at the median can never newly pass at a more conservative percentile).

**Acceptance Scenarios**:

1. **Given** a constraint with a configured evaluation percentile and a metric with sufficient distributional data available, **When** a candidate is evaluated, **Then** its feasibility is determined by the metric's value at that percentile rather than a single-run point estimate.
2. **Given** a constraint metric for which no distributional data is available, **When** a candidate is evaluated, **Then** the system falls back to point-estimate evaluation and clearly labels that candidate's constraint check as a point estimate, never silently substituting a fabricated percentile value.

---

### Edge Cases

- What happens when the design-space spec declares zero searchable levers, or only one? (Degenerates to a single baseline evaluation, or the one-lever sweep case explicitly folded in from the prior sweep proposal — both must still produce a valid, if trivial, candidate table.)
- What happens when two candidates in the search happen to resolve to an identical effective config (e.g. two grid points land on the same discrete choice, or a refinement step revisits an exact prior continuous value)? The system must not double-charge the run budget for a config it has already evaluated, and must report the reused result. Two continuous values that are merely close but not exactly equal are treated as distinct candidates, not deduped.
- How does the system handle a candidate scenario run that fails outright (crashes, times out, or produces no usable output)? It must be recorded as a failed/non-evaluable candidate distinct from an "evaluated but infeasible" candidate, and must not silently drop from the run-budget accounting.
- What happens when the objective metric itself is unavailable for a candidate (e.g. the underlying mart didn't populate it)? The candidate must be reported as non-evaluable for that metric, never assigned a fabricated objective value.
- What happens when a constraint references a metric that isn't in the supported vocabulary at all (typo or unsupported metric name)? The spec must fail validation loudly before any scenario run starts, naming the invalid metric.
- What happens when the search space is small enough that the run budget exceeds the number of distinct candidates available (e.g. 3 discrete choices but `--max-runs 50`)? The system must not re-run duplicate points to burn the remaining budget — it should exhaust the space and report completion below budget.
- How does re-running the exact same spec + seed after the baseline config has changed underneath it get handled? The system must detect and surface that the baseline config no longer matches what a prior run used, rather than silently mixing results from two different baselines.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a design-space specification declaring which config levers are searchable and, per lever, either a discrete set of choices or a bounded continuous range, supporting up to approximately 6-8 searchable levers with mixed discrete/continuous ranges in v1. Every other config value not declared searchable MUST remain pinned to the baseline configuration for every candidate evaluated. Because exhaustive grid search is impractical at this scale, the search strategy MUST use budget-bounded sampling (e.g. grid seeding plus local refinement) rather than assuming every design-space point can be evaluated.
- **FR-002**: System MUST accept an objective specification (minimize or maximize exactly one named metric) and zero or more hard constraints (each a named metric with a comparison operator and threshold).
- **FR-003**: System MUST validate a design-space and objective/constraint spec before evaluating any candidate, and MUST fail with a specific, actionable error identifying the invalid lever, metric, or constraint when validation fails — never partially start a search on an invalid spec.
- **FR-004**: System MUST restrict objective and constraint metric names to a supported vocabulary (the headline distributional metrics already produced by the ensemble system, plus IRS-compliance pass/fail from the existing compliance marts) and reject any other metric name at validation time.
- **FR-005**: System MUST require a hard run-budget cap as a mandatory input on every invocation — the system MUST refuse to start a search when no cap is supplied — and MUST NOT evaluate more candidate configurations than that cap in a single invocation.
- **FR-006**: System MUST evaluate every candidate design as a fully isolated scenario run (its own database), independently re-runnable from its own stored configuration, consistent with the platform's existing one-database-per-scenario isolation invariant.
- **FR-007**: System MUST produce, for every evaluated candidate, a record of: the config delta versus the baseline, the resulting objective metric value (or "non-evaluable" if unavailable), and per-constraint pass/fail status (or "non-evaluable" if unavailable).
- **FR-008**: System MUST rank feasible candidates (those satisfying every declared constraint) by objective value, and MUST separately report infeasible and non-evaluable candidates rather than omitting them.
- **FR-009**: For specs declaring exactly two objectives as a tradeoff rather than a single minimize/maximize target, System MUST identify and report the Pareto-efficient subset of evaluated candidates.
- **FR-010**: System MUST seed its own search process such that the same design-space/objective/constraint spec plus the same seed reproduces the same sequence of evaluated candidates and the same reported results.
- **FR-011**: System MUST report a result even when the run budget is exhausted before the search converges, presenting the best feasible candidate found so far (or, if none is feasible, the fact that zero candidates satisfied all constraints and which constraint(s) were never met).
- **FR-012**: System MUST avoid re-evaluating a candidate configuration that is identical (after resolving the declared levers to effective config values) to one already evaluated within the same run, reusing the prior result instead of consuming additional run budget. Identity MUST be determined by exact match on every declared lever's effective value — no rounding or tolerance-based matching — so continuous-range levers dedup only when a search step revisits an exact prior point.
- **FR-013**: System MUST support exporting a completed run's full candidate table (and Pareto frontier, when applicable) to a file usable outside the terminal (e.g. for a client-facing document), containing every evaluated candidate regardless of feasibility.
- **FR-014**: System MUST keep every evaluated candidate's underlying scenario database available for independent drill-down after the run completes, without requiring re-execution.
- **FR-015**: System MUST evaluate a constraint by point estimate by default. Percentile-based evaluation MUST activate for a given constraint only when the user explicitly names an evaluation percentile for that constraint, and only then — and only if sufficient distributional (ensemble) data for that metric is available — MUST the system evaluate that constraint against the metric's value at that percentile instead. The system MUST NOT auto-select a percentile or switch evaluation mode based solely on ensemble data being available, and MUST clearly label which evaluation mode (point-estimate vs. percentile-based) was used for each constraint on each candidate.
- **FR-016**: System MUST record, for any candidate scenario run that fails to execute or produces no usable output, a distinct "failed" status separate from "evaluated and infeasible," and this failure MUST still count against the run budget. A failed candidate run MUST NOT be automatically retried — it is recorded as failed on the first occurrence and consumes exactly one unit of run budget.

### Key Entities

- **Design-Space Specification**: The set of config levers declared searchable for a given optimizer invocation, each with its allowed discrete choices or bounded continuous range. Everything not listed here is implicitly pinned to the baseline configuration. v1 MUST support up to approximately 6-8 searchable levers with mixed discrete/continuous ranges; at this scale exhaustive grid search is impractical, so budget-bounded sampling (e.g. grid seeding plus local refinement) is required rather than optional.
- **Objective/Constraint Specification**: One target metric to minimize or maximize (or, for the two-objective case, a tradeoff pair), plus zero or more hard constraints, each a metric name, comparison operator, threshold, and optional evaluation percentile.
- **Candidate**: One point in the design space that the optimizer evaluated — a resolved effective configuration (baseline + declared lever values), the isolated scenario run that produced its results, its objective value, and its per-constraint feasibility status.
- **Optimizer Run**: One bounded search invocation tying together a design-space spec, an objective/constraint spec, a run-budget cap, a seed, and the resulting set of evaluated candidates plus the derived ranking and (where applicable) Pareto frontier.
- **Baseline Configuration**: The starting plan-design configuration against which every candidate's config delta is expressed; every candidate that shares levers left undeclared must match the baseline exactly on those levers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from a stated objective ("minimize employer cost") and one hard constraint ("participation ≥ 85%") to a ranked candidate table within a single command invocation and a stated, bounded run budget — no manual scenario-by-scenario iteration required.
- **SC-002**: 100% of candidates reported as "feasible" in the output independently satisfy every declared constraint when their underlying scenario data is separately checked — zero false-feasible candidates.
- **SC-003**: Re-running the identical spec and seed reproduces an identical ranked candidate list, verified across at least 3 repeated runs.
- **SC-004**: A run given `--max-runs N` never evaluates more than N distinct candidate scenarios, verified by run-count in the output matching or falling below the declared budget on every invocation.
- **SC-005**: Every exported candidate table row can be traced back to a specific, independently re-runnable scenario configuration — 100% of exported candidates are drill-down-able.
- **SC-006**: An infeasible spec (constraints unsatisfiable within the declared design space) is reported as such, naming the binding constraint, in 100% of tested infeasible cases — never presented as a false recommendation.
