# Feature Specification: New-Hire Cohort Isolation for Cost Comparison

**Feature Branch**: `134-new-hire-cohort`
**Created**: 2026-08-06
**Status**: Draft
**Input**: User description: "Cost Comparison: isolate the new-hire cohort (hired on/after the first simulation year)" (GitHub issue #512)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Isolate the cost of new hires under a plan design change (Priority: P1)

A benefits consultant comparing two plan designs (e.g. baseline match vs. a richer match formula) in the Cost Comparison view wants to know what the new design costs specifically for employees who will be hired during the simulation horizon, not blended with the much larger incumbent census that mutes the signal.

**Why this priority**: This is the entire point of the feature — without it, the Multi-Year Cost Matrix under-represents the effect that grows fastest over the simulation horizon (new-hire share of headcount).

**Independent Test**: Open Cost Comparison for two completed scenarios that differ in plan design, select the "Hired during the simulation" cohort, and confirm the reported employer cost, employer cost rate, and participation numbers all shift to reflect only employees hired on/after the first simulation year.

**Acceptance Scenarios**:

1. **Given** two completed scenarios are selected in Cost Comparison with the cohort filter at its default, **When** the user switches the cohort control to "Hired during the simulation (2025+)", **Then** the cost matrix, incremental-cost chart, and methodology panel all update to reflect only employees whose `employee_hire_date` falls on/after the resolved first simulation year, for every scenario and every year.
2. **Given** the cohort filter is set to "Hired during the simulation", **When** the user switches it to "Starting census", **Then** the displayed figures become the complement of the new-hire cohort — the starting census population — for the same scenarios and years.
3. **Given** a cohort other than "All employees" is active, **When** the user reloads the page, **Then** the previously selected cohort is restored from persisted preferences.

---

### User Story 2 - Trust that cohort figures are internally consistent (Priority: P1)

A user comparing "All employees", "Hired during the simulation", and "Starting census" for the same scenario/year wants the two cohort views to add up to the "all" view, and wants every displayed rate (participation, deferral, contribution) to be computed within the selected cohort rather than diluted by the full population.

**Why this priority**: A cohort filter that silently mixes cohort-scoped numerators with population-wide denominators produces numbers that look plausible but are wrong — worse than no feature, because it looks authoritative in a client-facing deck.

**Independent Test**: For a given scenario and year, sum the new-hire and starting-census employer cost and confirm it equals the "all employees" employer cost; separately confirm participation rate, deferral rate, and contribution-rate percentages differ between cohorts (proving they were recomputed, not sliced from a shared aggregate).

**Acceptance Scenarios**:

1. **Given** a scenario with a multi-year horizon, **When** new-hire cost and starting-census cost are summed for a given year, **Then** the sum equals the "all employees" cost for that year, for every year in the horizon.
2. **Given** the "Hired during the simulation" cohort is active, **When** the user views participation rate, average deferral rate, and contribution-rate percentages, **Then** those values are computed against the new-hire population's own totals, not the unfiltered population's totals.

---

### User Story 3 - Understand what's being shown (Priority: P2)

A user viewing a filtered cost figure needs to know at a glance that it's filtered, not a total — both live in the UI and in anything copied out (TSV export), since these numbers end up in client-facing spreadsheets and decks.

**Why this priority**: A filtered number that reads as a total is a credible misread risk once it leaves the app (e.g. pasted into a deck without the on-screen badge).

**Independent Test**: With a non-default cohort active, confirm a visible badge/label appears on the cost matrix and incremental-cost chart, the methodology panel names the active cohort and its definition, and the copy-to-TSV output includes the cohort label.

**Acceptance Scenarios**:

1. **Given** a cohort other than "All employees" is selected, **When** the user views the cost matrix or incremental-cost chart, **Then** a persistent, plainly worded badge (e.g. "Hired during the simulation (2025+)") is visible on that chart/table.
2. **Given** a cohort other than "All employees" is selected, **When** the user copies the matrix to TSV, **Then** the exported text identifies the active cohort.
3. **Given** the selected cohort has zero matching employees for a scenario/year (e.g. a single-year run, or "Starting census" on a fully-turned-over population), **When** the user views that cell/chart, **Then** the UI shows an explicit empty state rather than a bare `$0`.

### Edge Cases

- **Single-year simulation**: the "Hired during the simulation" cohort may be empty for year 1 (no time for hires to appear in a snapshot) depending on when hiring events land relative to the snapshot; must render an explicit empty state, not `$0` or a misleading chart gap.
- **Fully-terminated starting census**: "Starting census" cohort can be legitimately empty in later years if every incumbent has termed out — same empty-state treatment, not `$0`.
- **Re-run over a shifted year range**: a scenario database re-run with a different `start_year` than what's stamped in `run_metadata` must not silently misclassify part of the census as new hires — the resolved first-simulation-year cross-check must warn (not fail) on mismatch.
- **Unknown/corrupt persisted cohort value**: if a user's stored preference contains a value other than `all`, `new_hires`, or `baseline` (e.g. from a future app version or manual localStorage edit), the UI must fall back to `all` rather than erroring.
- **Invalid cohort query parameter**: a request with a `cohort` value outside the three allowed values must be rejected by the API with a 422, not silently coerced to `all`.
- **Comparison across scenarios with different first-simulation years**: out of scope for this feature (see Assumptions) — the resolved year is per-scenario, and cohort comparison assumes callers select scenarios that share a comparable horizon.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Cost Comparison view MUST offer a cohort selector with exactly three values: "All employees" (default), "Hired during the simulation" (new hires), and "Starting census" (baseline), applied identically to every scenario in the current comparison.
- **FR-002**: A "new hire" MUST be defined as an employee whose hire date falls on or after the first simulation year for that scenario's run; "starting census" MUST be defined as the complement (everyone not a new hire) within the same population the "all employees" view would show.
- **FR-003**: The first simulation year used for cohort classification MUST be resolved once per scenario (not re-derived per query) from the scenario's own simulated data, and MUST be cross-checked against that scenario's recorded run start year; a mismatch MUST produce a logged warning, not a hard failure or a silently different cohort split depending on which source was used.
- **FR-004**: Every rate or ratio shown under a non-default cohort (participation rate, average deferral rate, employer cost rate, employee/match/core/total contribution rate) MUST be computed using totals confined to that cohort, not derived by combining a cohort-scoped numerator with an all-population denominator.
- **FR-005**: For a given scenario and simulation year, the new-hire cohort's employer cost plus the starting-census cohort's employer cost MUST equal the all-employees employer cost, within floating-point rounding tolerance.
- **FR-006**: The single-scenario DC Plan Analytics view MUST support the same cohort filter as the multi-scenario Cost Comparison view.
- **FR-007**: Selecting a non-default cohort MUST NOT change the numbers shown for "All employees" — the default cohort's output MUST be identical, request for request, to current (pre-feature) behavior.
- **FR-008**: The selected cohort MUST persist across a page reload using the same mechanism as other Cost Comparison view preferences, and MUST fall back to "All employees" if the persisted value is not one of the three recognized cohort values.
- **FR-009**: Whenever a non-default cohort is active, the cost matrix and the incremental-cost chart MUST display a persistent, plain-language label naming the active cohort (including the resolved first simulation year, e.g. "Hired during the simulation (2025+)").
- **FR-010**: The "How these figures are measured" methodology panel MUST name the active cohort and state its definition whenever a non-default cohort is selected.
- **FR-011**: Any copy-to-TSV / export output from the cost matrix MUST include an indication of the active cohort when it is not "All employees".
- **FR-012**: A scenario/year cell with zero employees in the selected cohort MUST render an explicit empty-state indicator, distinguishable from a computed zero-dollar result.
- **FR-013**: A request specifying a cohort value outside the three recognized values MUST be rejected with a client-error response (422) rather than defaulting silently.
- **FR-014**: Changing the cohort selection MUST re-fetch and fully replace the displayed comparison data for all currently selected scenarios (no stale/partial mixing of cohorts across scenarios in one view).

### Key Entities *(include if feature involves data)*

- **Cohort**: A named partition of a scenario's simulated workforce population, one of `all`, `new_hires` (hired on/after the resolved first simulation year), `baseline` (everyone else). Applies uniformly across every simulation year and every scenario within a single comparison request.
- **Resolved First Simulation Year**: A per-scenario value derived from that scenario's own simulated data, cross-checked against the scenario's recorded run start year, used to classify every employee into `new_hires` or `baseline`.
- **DC Plan Analytics (cohort-scoped)**: The existing participation, contribution, and rate metrics, recomputed so that every ratio's numerator and denominator both come from the same cohort-filtered population.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can isolate the new-hire cohort's cost impact for a plan-design comparison in two clicks (select cohort control) from the existing Cost Comparison view, without leaving the page or re-selecting scenarios.
- **SC-002**: For every scenario and every simulation year, new-hire cost plus starting-census cost equals the all-employees cost exactly (within rounding), verified by an automated test — this is the cheapest and strongest guard against a mis-specified cohort predicate.
- **SC-003**: Selecting "All employees" produces results byte-identical to current (pre-feature) behavior for the same scenario selection, verified by a regression test.
- **SC-004**: 100% of screens and export paths that show a cohort-filtered number (cost matrix, incremental-cost chart, methodology panel, TSV export) visibly label the active cohort when it is not "All employees" — there is no filtered figure anywhere in the view that could be mistaken for a total.
- **SC-005**: A cohort selection survives a full page reload without the user having to reselect it.

## Assumptions

- Every scenario surfaced in Cost Comparison already has a completed, queryable `fct_workforce_snapshot`; cohort resolution reads only data that's already produced by a normal simulation run (no new pipeline stage or model).
- Comparing scenarios that were run over different simulation year ranges (and therefore have different resolved first-simulation-years) is not blocked by this feature — each scenario's own hire-date cutoff is used independently — but reconciling or flagging that mismatch to the user is out of scope.
- "Hire date" for cohort purposes is the employee's most recent hire date as recorded in the snapshot; re-hire semantics beyond what the snapshot already encodes are unaffected by this feature.
- This feature covers only the Cost Comparison view and the single-scenario DC Plan Analytics view that shares its data path; the Winners/Losers tab, `DCPlanComparisonSection`, and timeline views are explicitly out of scope (per the source issue) though the underlying predicate should be reusable by them later.
