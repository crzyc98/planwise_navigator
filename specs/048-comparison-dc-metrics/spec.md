# Feature Specification: DC Plan Metrics in Scenario Comparison

**Feature Branch**: `048-comparison-dc-metrics`
**Created**: 2026-02-12
**Status**: Draft
**Input**: User description: "Extend scenario comparison backend to include DC plan metrics (participation rate, average deferral rate, employer contribution rates) aggregated by year for each scenario"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View DC Plan Metrics Across Scenarios (Priority: P1)

A plan administrator comparing two or more scenarios wants to see how retirement plan outcomes differ. After running simulations with different plan designs (e.g., different match formulas, auto-escalation settings), they request a comparison and receive DC plan metrics alongside the existing workforce metrics. This lets them evaluate the financial impact of plan design changes on participation, deferral behavior, and employer costs.

**Why this priority**: This is the core value proposition. Without per-year DC plan metrics in the comparison response, users cannot evaluate plan design trade-offs across scenarios.

**Independent Test**: Can be fully tested by requesting a comparison between two completed scenarios and verifying that DC plan metrics (participation rate, deferral rate, contributions) appear in the response for each year.

**Acceptance Scenarios**:

1. **Given** two completed scenarios with different match formulas, **When** a comparison is requested, **Then** the response includes DC plan metrics for each scenario broken down by simulation year.
2. **Given** a multi-year simulation (e.g., 2025-2027), **When** a comparison is requested, **Then** DC plan metrics are returned for each year (2025, 2026, 2027) per scenario.
3. **Given** a scenario where no employees are enrolled, **When** a comparison is requested, **Then** participation rate is 0%, average deferral rate is 0, and contribution totals are 0 (no errors).

---

### User Story 2 - Compare DC Plan Deltas Against Baseline (Priority: P1)

A plan administrator wants to see not just raw metrics, but how each scenario differs from the baseline. For example, "Scenario B has +2.3% higher participation rate than baseline" or "Employer costs are $150K higher under Scenario C." Delta calculations make it easy to evaluate the marginal impact of plan design changes.

**Why this priority**: Delta calculations are essential for decision-making. Raw numbers alone are hard to compare; relative differences drive plan design decisions.

**Independent Test**: Can be tested by comparing a baseline scenario with one alternative and verifying that delta values (absolute and percentage) are computed correctly for all DC plan metrics.

**Acceptance Scenarios**:

1. **Given** a baseline scenario and one alternative, **When** a comparison is requested, **Then** delta values are computed for each DC plan metric (participation rate, deferral rate, all contribution amounts, employer cost rate).
2. **Given** three scenarios compared against a baseline, **When** a comparison is requested, **Then** deltas are calculated independently for each non-baseline scenario relative to baseline.
3. **Given** a baseline with zero employer match and an alternative with a match formula, **When** a comparison is requested, **Then** employer match delta shows the full match amount as the delta (avoiding division-by-zero errors in percentage calculations).

---

### User Story 3 - DC Plan Summary Deltas (Priority: P2)

A plan administrator reviewing a comparison wants a high-level summary showing the final-year DC plan metrics and their deltas, similar to how workforce summary deltas work today (final headcount, total growth). This provides a quick "bottom line" view of DC plan impact without scanning year-by-year data.

**Why this priority**: Summary deltas enhance usability but are not strictly required for analysis. Year-by-year data (P1) provides the same information in a more granular form.

**Independent Test**: Can be tested by checking that the summary_deltas section of the response includes DC plan metrics (final participation rate, total employer cost) alongside existing workforce summary deltas.

**Acceptance Scenarios**:

1. **Given** a multi-year comparison, **When** the response is returned, **Then** summary_deltas includes final-year participation rate and total employer cost with deltas vs baseline.
2. **Given** a single-year comparison, **When** the response is returned, **Then** summary_deltas DC plan values match the single year's values exactly.

---

### Edge Cases

- What happens when a scenario has no DC plan data in the snapshot table? The system returns empty DC plan metrics (all zeros) rather than failing.
- What happens when all employees are terminated in a given year (zero active employees)? Participation rate and deferral rate are 0, not a division-by-zero error.
- What happens when contribution columns contain NULL values? NULLs are treated as 0 in aggregations.
- What happens when scenarios cover different year ranges (e.g., baseline runs 2025-2027 but alternative runs 2025-2026)? DC plan metrics are only compared for overlapping years.
- What happens when the baseline scenario has zero values for a metric (e.g., zero employer match)? Percentage deltas are reported as 0% rather than causing an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST return DC plan participation rate per year per scenario, calculated as the percentage of active employees who are enrolled.
- **FR-002**: System MUST return average employee deferral rate per year per scenario, calculated only among enrolled employees.
- **FR-003**: System MUST return total employee contributions, total employer match, and total employer core contributions per year per scenario.
- **FR-004**: System MUST return total employer cost (match + core) per year per scenario.
- **FR-005**: System MUST return employer cost rate per year per scenario, calculated as total employer cost divided by total compensation, expressed as a percentage.
- **FR-006**: System MUST return participant count (number of enrolled employees) per year per scenario.
- **FR-007**: System MUST calculate absolute and percentage deltas for all DC plan metrics relative to the baseline scenario.
- **FR-008**: System MUST handle zero denominators gracefully (zero active employees, zero compensation, zero baseline values) by returning 0 rather than erroring.
- **FR-009**: System MUST include DC plan summary deltas in the existing summary_deltas response section for final-year participation rate and total employer cost.
- **FR-010**: System MUST return DC plan metrics alongside existing workforce and event comparison data in the same API response (no separate endpoint needed).

### Key Entities

- **DCPlanYearMetrics**: Aggregated DC plan metrics for a single scenario in a single simulation year. Contains participation rate, average deferral rate, contribution totals (employee, employer match, employer core), total employer cost, employer cost rate, and participant count.
- **DCPlanScenarioMetrics**: A collection of yearly DC plan metrics for a single scenario. Contains the scenario identifier, display name, and the list of per-year metrics.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can see DC plan participation rates, deferral rates, and contribution totals for each scenario in the comparison response without any additional API calls.
- **SC-002**: Delta calculations correctly show the difference between each scenario and the baseline for all DC plan metrics with both absolute and percentage deltas.
- **SC-003**: The comparison endpoint returns DC plan data within the same response time envelope as the current workforce-only comparison (no perceptible slowdown).
- **SC-004**: All edge cases (zero enrollment, NULL values, mismatched year ranges) are handled gracefully with zero-value defaults rather than errors.
- **SC-005**: Automated tests validate DC plan metric aggregation logic, delta calculations, and edge case handling.

## Assumptions

- The `fct_workforce_snapshot` table already contains the required columns: `is_enrolled_flag`, `current_deferral_rate`, `prorated_annual_contributions`, `employer_match_amount`, `employer_core_amount`, `prorated_annual_compensation`, and `employment_status`. No schema changes are needed.
- The active employee filter uses `UPPER(employment_status) = 'ACTIVE'`, consistent with the existing comparison service's pattern.
- DC plan metrics are computed from the same per-scenario DuckDB database files that the comparison service already opens for workforce metrics, so no additional database connections are needed.
- The baseline scenario always has valid data; if the baseline has no DC plan data, all deltas will be zero.
