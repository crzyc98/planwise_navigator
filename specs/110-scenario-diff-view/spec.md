# Feature Specification: Studio Two-Scenario Diff View

**Feature Branch**: `426-studio-scenario-diff`
**Created**: 2026-07-12
**Status**: Draft
**Input**: User description: "Studio: two-scenario side-by-side diff view (metrics + the config deltas that caused them)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Understand What Changed Between Two Scenarios (Priority: P1)

An analyst selects two completed scenarios in the same workspace and opens a focused side-by-side diff. They can immediately see the settings that differ between the scenarios alongside the year-by-year outcome differences, so they can connect the levers they changed to the results that moved without opening separate configuration files or mentally reconciling dashboards.

**Why this priority**: This is the central analyst question the feature answers: what changed, what moved, and which changed setting explains it.

**Independent Test**: Create two otherwise comparable completed scenarios with one deliberate plan-setting change, open their diff, and verify that the changed setting and its corresponding annual metric divergence are both visible.

**Acceptance Scenarios**:

1. **Given** two completed scenarios in one workspace, **When** an analyst opens their diff with scenario A as the baseline, **Then** the view presents scenario A and B names, year-by-year values for both, and the change from A to B for every supported metric.
2. **Given** scenario B differs from scenario A only in an employer-match setting, **When** an analyst opens the diff, **Then** the configuration panel identifies that setting and its values in both scenarios, the employer-match-cost trend diverges where applicable, and unrelated headcount and average-compensation trends remain equal.
3. **Given** two scenarios have several effective-setting differences, **When** an analyst opens the diff, **Then** each changed setting is shown once with a stable dotted location, both values, and whether it exists only in A, only in B, or in both with different values.
4. **Given** settings that are equivalent after applying each scenario's overrides to its workspace defaults, **When** the analyst opens the diff, **Then** they do not appear as changes merely because their source files are structured differently.

---

### User Story 2 - Trust the Comparison Provenance (Priority: P2)

An analyst needs to distinguish a true lever effect from ordinary simulation variation or results generated at different times. The diff identifies when each scenario was generated and clearly signals whether their seeds and effective-configuration fingerprints are aligned, so the analyst knows when to treat differences cautiously.

**Why this priority**: A visually correct comparison can still be misleading without its provenance; the warning protects the reproducibility promise and makes interpretation safer.

**Independent Test**: Compare two completed scenarios generated with different seeds and verify a persistent, understandable warning says the differences may include seed noise; repeat with matching seeds and verify no seed-noise warning appears.

**Acceptance Scenarios**:

1. **Given** two compared scenarios with different random seeds, **When** an analyst opens the diff, **Then** a visible warning explains that observed differences may include seed noise.
2. **Given** two compared scenarios with matching seeds and available provenance, **When** an analyst opens the diff, **Then** both seed values, short configuration identifiers, and generation timestamps are available without a seed-noise warning.
3. **Given** a scenario produced before provenance records were available, **When** an analyst opens the diff, **Then** the comparison remains usable and clearly identifies the unavailable provenance rather than failing or implying verification.
4. **Given** provenance indicates either scenario may contain mixed-generation results, **When** an analyst opens the diff, **Then** the view displays a caution that results may not be attributable solely to the displayed configuration differences.

---

### User Story 3 - Reach the Diff from Existing Comparison Workflows (Priority: P3)

An analyst already working from the scenario list or an existing comparison surface can move directly to the focused diff when exactly two completed scenarios are in scope, rather than copying identifiers or reconstructing the comparison.

**Why this priority**: Direct entry points make the feature discoverable while preserving the existing multi-scenario views for broader comparisons.

**Independent Test**: Select exactly two completed scenarios from the scenario list and verify that a "Diff A vs B" action opens their diff; verify the same action is offered from an existing two-scenario comparison.

**Acceptance Scenarios**:

1. **Given** exactly two completed scenarios are selected, **When** an analyst views available comparison actions, **Then** they can open a focused A-vs-B diff in addition to the existing comparison option.
2. **Given** an existing comparison contains exactly two scenarios, **When** an analyst views the comparison, **Then** they can navigate to the focused diff while preserving the selected scenario order.
3. **Given** fewer than two, more than two, or any incomplete scenarios are selected, **When** an analyst views comparison actions, **Then** the focused diff is unavailable and the analyst receives clear guidance when they attempt an invalid direct link.

### Edge Cases

- A requested scenario does not exist, belongs to another workspace, or is incomplete: no result values or configuration details are exposed, and the analyst receives the same clear invalid-comparison response used by other workspace comparisons.
- Both effective configurations are identical: the configuration panel states that there are no changed settings while metric and provenance information remain available.
- A setting exists only in one scenario after overrides are resolved: it is presented as an addition or removal rather than an ambiguous blank value.
- Cosmetic metadata such as names, descriptions, and timestamps differs: it is excluded from the setting-delta panel so the panel remains focused on result-driving differences.
- A comparison has incomplete annual data for one supported metric: available years remain visible and the missing data is explicitly identified rather than represented as a zero.
- A user navigates directly with the same scenario twice: the system rejects the request with a clear instruction to select two distinct completed scenarios.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a workspace-scoped, read-only focused comparison for exactly two distinct completed scenarios, designated A and B.
- **FR-002**: The comparison MUST show each scenario's display name and available generation provenance: generation timestamp, short effective-configuration identifier, and random seed.
- **FR-003**: The system MUST derive each scenario's effective settings using the same workspace-default and scenario-override rules used when that scenario is run.
- **FR-004**: The system MUST present a flat list of effective-setting differences containing the stable dotted setting location, A value, B value, and status: changed, only in A, or only in B.
- **FR-005**: The setting-delta panel MUST exclude non-result-driving cosmetic metadata, including names, descriptions, and timestamps.
- **FR-006**: The setting-delta panel MUST use understandable labels for commonly adjusted levers, including growth, compensation adjustments, employer match, automatic enrollment, and eligibility, while retaining the exact dotted setting location for every item.
- **FR-007**: The comparison MUST make it clear when no effective settings differ and MUST make the count of unchanged settings available without presenting the unchanged settings by default.
- **FR-008**: The comparison MUST display annual paired values and A-to-B deltas for headcount, average active-employee compensation, participation rate, employer match cost, and total employer cost.
- **FR-009**: Each supported metric MUST have a dedicated year-by-year paired trend and a final-year delta that states the direction and magnitude of the change from A to B.
- **FR-010**: Average active-employee compensation MUST be calculated per year from the annualized compensation values of active employees; it MUST be supplied alongside the other workforce comparison values.
- **FR-011**: The comparison MUST warn prominently when the scenarios use different random seeds, explaining that differences may include seed noise.
- **FR-012**: The comparison MUST warn prominently when available provenance indicates possible mixed-generation results for either scenario, explaining that differences may not be attributable solely to the displayed setting changes.
- **FR-013**: Missing provenance in older scenario results MUST not prevent a comparison; the system MUST identify it as unavailable rather than treating it as matching.
- **FR-014**: The system MUST provide a focused-diff entry point from the scenario list when exactly two completed scenarios are selected and from an existing comparison when it contains exactly two scenarios.
- **FR-015**: Invalid requests (missing scenario, scenario outside the workspace, incomplete scenario, duplicate selection, or a count other than two) MUST be rejected consistently with existing workspace-comparison behavior.
- **FR-016**: The feature MUST not modify scenario results, configurations, or provenance records; it is strictly a view over existing workspace and scenario artifacts.

### Key Entities

- **Scenario Pair**: Two distinct, completed scenarios in the same workspace, ordered as A (baseline) and B (comparison).
- **Effective Setting**: The result-driving setting value after applying a scenario's overrides to the workspace defaults using the rules that governed its run.
- **Setting Delta**: One difference between effective settings, including its dotted location, values for A and B, and whether it changed, was added, or was removed.
- **Annual Metric Comparison**: The values for A and B for one supported metric in each simulation year, plus the delta from A to B and final-year summary.
- **Scenario Provenance**: Available information identifying how a scenario's results were generated, including configuration identifier, seed, timestamp, and any indication of generation drift.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the specified single-lever acceptance case, 100% of comparisons show the one changed effective setting and the corresponding annual employer-match-cost difference, while unchanged headcount and average-compensation values show zero delta for every available year.
- **SC-002**: For every valid pair of completed scenarios, an analyst can identify the changed settings, seed status, and final-year change for all five supported metrics from one focused view without opening scenario configuration files.
- **SC-003**: 100% of comparisons with different seeds display a seed-noise warning, and 0% of comparisons with confirmed matching seeds display that warning.
- **SC-004**: 100% of comparisons involving older results without provenance remain viewable and explicitly indicate unavailable provenance rather than failing.
- **SC-005**: 100% of invalid two-scenario requests are rejected without exposing data from outside the requested workspace or from incomplete scenarios.
- **SC-006**: The focused diff introduces no writes to either scenario's stored results or configuration artifacts during viewing.

## Assumptions

- Existing workspace comparison data contains the annual workforce and retirement-plan measures needed by this view, except for average active-employee compensation, which becomes an additive comparison measure.
- Scenario A is the baseline, and all displayed deltas use B minus A; selected scenario order is preserved when users enter from an existing comparison.
- A short configuration identifier is a human-readable display of the run's recorded effective-configuration fingerprint, not a replacement for the setting-delta list.
- Provenance warnings are informational, not blocking: users may still inspect a comparison with different seeds, missing provenance, or possible generation drift.
- This version remains limited to two scenarios within one workspace. Multi-scenario comparisons, cross-workspace comparisons, exporting the diff, and changing existing broader comparison views are out of scope.
