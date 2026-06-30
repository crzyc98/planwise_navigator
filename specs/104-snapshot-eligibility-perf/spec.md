# Feature Specification: Optimize fct_workforce_snapshot Eligibility Branch

**Feature Branch**: `104-snapshot-eligibility-perf`
**Created**: 2026-06-29
**Status**: Draft
**Input**: GitHub issue [#365](https://github.com/crzyc98/planwise_navigator/issues/365) — "perf(dbt): fct_workforce_snapshot — eliminate correlated subquery + redundant fct_yearly_events scans"

## Overview

`fct_workforce_snapshot` is the heaviest mart in the simulation and the final model built each year. Its subsequent-years (year 2+) eligibility branch contains two query-shape problems that add avoidable work to every multi-year run: a correlated subquery that re-scans the event stream once per employee, and two redundant direct reads of the on-disk event table that duplicate a CTE already defined in the same model. This feature rewrites those constructs so the model produces **identical output** while doing less work.

The defining constraint is correctness: this is an internal query refactor, not a behavior change. Every column the model emits — workforce counts, eligibility status, enrollment dates — must be unchanged for every employee, every year, every configuration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Faster multi-year snapshot build with identical results (Priority: P1)

An analyst runs a multi-year simulation (e.g. `simulate 2025-2029`). The final snapshot for each year builds faster because the eligibility branch no longer re-scans the event stream per employee, yet every value in `fct_workforce_snapshot` matches what the prior implementation produced.

**Why this priority**: This is the entire purpose of the feature. The performance win is meaningless if the output changes, so the identical-output guarantee and the speedup are inseparable and both belong in the top-priority slice.

**Independent Test**: Run a multi-year simulation against an isolated database on the current `main`, capture `fct_workforce_snapshot`, run the same simulation against the rewritten model in a second isolated database, and diff the two snapshots. The diff must be empty; the rewritten run must complete in no more wall-clock time than baseline (faster expected, never slower).

**Acceptance Scenarios**:

1. **Given** a multi-year simulation on the rewritten model, **When** the run completes, **Then** `fct_workforce_snapshot` is row-for-row and column-for-column identical to the baseline snapshot for the same configuration and seed.
2. **Given** the same simulation, **When** comparing build time, **Then** the rewritten model's `fct_workforce_snapshot` stage takes no longer than baseline.
3. **Given** an employee with multiple eligibility determinations across years, **When** the snapshot resolves their eligibility, **Then** the most recent initial determination at or before the current year is used — the same one the correlated subquery selected.

---

### User Story 2 - Maintainable, consistent model source (Priority: P2)

A developer reading or modifying the eligibility branch finds the model sources current-year events from a single, named place rather than from a mix of one shared CTE and two ad-hoc direct table references with subtly different filters.

**Why this priority**: Consistency reduces the chance the next change introduces a year-filter mismatch or diverges the two read paths. It is real value but secondary to the performance/correctness outcome; the model is already correct today, just inconsistent.

**Independent Test**: Inspect the rewritten eligibility branch and confirm current-year event reads go through the shared current-year-events construct (or an equally single, named source), with no remaining ad-hoc direct reads of the event table inside that branch.

**Acceptance Scenarios**:

1. **Given** the rewritten eligibility branch, **When** a reviewer traces where current-year hire and eligibility events come from, **Then** they originate from one consistent source rather than separate redundant reads.

---

### Edge Cases

- **Employee with no eligibility events**: must still fall back to the baseline source exactly as before (the rewrite must not turn a missing-events fallback into a dropped row or a null where a baseline value existed).
- **Employee with eligibility events only in future years** (determination dated after the current year): must be treated identically to baseline — counted as pending, not eligible, per the existing date comparison.
- **Ties on most-recent year**: if an employee has multiple qualifying eligibility events, the rewrite must resolve to the same single row the correlated subquery produced, with no new duplicate rows entering the snapshot.
- **First simulation year**: the year-1 branch is out of scope and must be untouched; the rewrite applies only to the subsequent-years branch.
- **New-hire identification**: new hires sourced for the eligibility branch must match the same set of employees as before, including the new-hire id pattern and the exclusion of anyone already present in the baseline workforce.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The model MUST resolve each employee's most-recent initial eligibility determination (at or before the current simulation year) to exactly the same value as the existing correlated-subquery logic, without scanning the event stream once per employee.
- **FR-002**: The model MUST produce `fct_workforce_snapshot` output that is byte-identical to the pre-change output for every employee, every simulation year, and every tested configuration and random seed.
- **FR-003**: Within the subsequent-years eligibility branch, current-year event reads (new-hire source and eligibility-event source) MUST be sourced consistently from a single named current-year-events construct rather than separate redundant direct reads of the event table.
- **FR-004**: The change MUST be confined to the subsequent-years eligibility branch of `fct_workforce_snapshot`; the first-year branch and all other CTEs/outputs MUST remain functionally unchanged.
- **FR-005**: The model MUST preserve existing fallback behavior to the baseline source for employees lacking eligibility or enrollment events.
- **FR-006**: The model MUST NOT introduce new duplicate rows or change the snapshot's row grain.
- **FR-007**: The rewritten model MUST build in no more wall-clock time than the baseline for an equivalent multi-year run.
- **FR-008**: Validation MUST be performed against an isolated database (per-scenario or `DATABASE_PATH`), never the shared development database, across a full multi-year simulation rather than a single-year or single-model run.

### Key Entities *(include if feature involves data)*

- **Workforce snapshot**: the point-in-time per-employee state produced for each simulation year; the artifact whose output must remain identical.
- **Eligibility determination**: a per-employee event record indicating when an employee became (or is scheduled to become) plan-eligible; the most-recent initial determination at or before the current year drives the snapshot's eligibility columns.
- **Current-year event set**: the events belonging to the simulation year being built; should be read from one consistent source within the eligibility branch.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A full multi-year simulation produces a `fct_workforce_snapshot` that differs from the baseline by zero rows and zero cell values across all years and all tested configurations.
- **SC-002**: The eligibility branch resolves each employee's eligibility with a single pass over the event data rather than one lookup per employee (no per-row re-scan of the event stream remains).
- **SC-003**: The `fct_workforce_snapshot` build stage completes in equal or less wall-clock time than baseline for an equivalent multi-year run; any measured regression blocks the change.
- **SC-004**: At least one edge configuration (e.g. broad auto-enrollment scope with an early eligibility cutoff) is included in validation and also shows a zero-difference snapshot.
- **SC-005**: The subsequent-years eligibility branch contains no remaining ad-hoc direct reads of the event table that duplicate the shared current-year-events source.

## Assumptions

- "Byte-identical" is evaluated on the full set of `fct_workforce_snapshot` columns with a deterministic ordering applied before comparison; pure row/column ordering differences that do not change content are acceptable as long as the comparison normalizes ordering.
- Baseline for comparison is the current `main` implementation of `fct_workforce_snapshot` at the time the work begins.
- The performance benefit may be partially masked by existing object caching; the binding requirement is "no regression," with measurable improvement expected but not guaranteed on every configuration.
- No schema, config, seed, or downstream-model changes are required; the work is contained to the one model file.
- Validation uses the same random seed and configuration for baseline and rewritten runs so differences are attributable solely to the query rewrite.

## Out of Scope

- The first-simulation-year branch of the model.
- The separate DuckDB `checkpoint_threshold` tuning investigation (tracked independently in issue #366).
- Any change to eligibility business rules, event generation, or enrollment logic.
- Broader refactoring of `fct_workforce_snapshot` beyond the two identified constructs.
