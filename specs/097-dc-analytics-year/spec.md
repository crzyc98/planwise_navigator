# Feature Specification: DC Plan Analytics — 0% Deferral Fix and Year Filter

**Feature Branch**: `097-dc-analytics-year`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "based on the last few changes, i'm seeing on my analytics page called 'Dc plan' why is it no longer have anyone at 0% deferral rate even though it says i have 65% participation. can you also add to this page an option to pick the year of the simulation? and that should apply to when we compare as well"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Deferral Rate Distribution Includes Non-Participants (Priority: P1)

A planner reviews the DC Plan analytics page after running a simulation and sees a Deferral Rate Distribution chart. They expect the 0% bucket to represent all employees who are not actively deferring into the plan — both those who chose not to enroll and any enrolled employees with a zero deferral rate. After the 096-newhire-voluntary-enroll changes, all enrolled employees now have a positive deferral rate assigned, so the 0% bucket silently emptied. The planner interprets this as every participant deferring, when in reality 35% of eligible employees are simply not enrolled.

**Why this priority**: This is a data integrity bug that causes misleading analytics — the distribution appears to show 100% of the workforce deferring when only 65% are enrolled, and all of them happen to be at rates > 0%.

**Independent Test**: Can be fully tested by running a simulation with known non-enrolled employees and verifying the 0% bucket in the Deferral Rate Distribution chart equals the count of non-enrolled eligible employees.

**Acceptance Scenarios**:

1. **Given** a completed simulation where 65% of employees are enrolled and all enrolled employees have deferral rates > 0%, **When** the user views the Deferral Rate Distribution chart, **Then** the 0% bucket shows the count of non-enrolled eligible employees (approximately 35% of the workforce).
2. **Given** the chart tooltip for the 0% bucket, **When** hovered, **Then** it clearly labels those employees as "Not enrolled" or "0% deferral / Not participating" to distinguish them from enrolled employees with higher rates.
3. **Given** a simulation where some enrolled employees genuinely have a 0% deferral rate (e.g., census carry-overs), **When** viewing the chart, **Then** they are counted in the 0% bucket alongside non-enrolled employees, and the tooltip reflects the combined count.

---

### User Story 2 — Year Picker for Single-Scenario View (Priority: P2)

A planner selects a scenario that covers 2025–2027 and wants to compare how participation and contributions changed year over year. Currently, the KPI cards and deferral distribution chart show data aggregated across all years (or the final year only). The planner needs to quickly drill into a specific year — for example, to understand why Year 2 contributions spiked — without losing context about the full multi-year run.

**Why this priority**: Multi-year simulations are the primary use case, and providing year-level drill-down makes the page actionable rather than just informational.

**Independent Test**: Can be tested by selecting a 3-year scenario, picking Year 2 from the year picker, and verifying that all KPI cards and charts update to reflect Year 2 data only.

**Acceptance Scenarios**:

1. **Given** a completed multi-year scenario, **When** the user opens the DC Plan analytics page, **Then** a year picker is visible in the controls area, defaulting to "All Years" (aggregate across all simulation years).
2. **Given** a year picker set to "All Years," **When** the user selects a specific year (e.g., 2026), **Then** the KPI cards (participation rate, contribution totals) update to show that year's data only.
3. **Given** a specific year selected, **When** viewing the Deferral Rate Distribution chart, **Then** it reflects the deferral distribution for that year rather than the final/aggregate year.
4. **Given** a specific year selected, **When** viewing the Contributions by Year chart, **Then** the selected year is visually highlighted (e.g., different color or thicker bar) while other years remain visible for context.
5. **Given** a single-year simulation is loaded, **When** the year picker appears, **Then** it shows only that year and is effectively in a fixed-year view.

---

### User Story 3 — Year Picker Applied to Comparison View (Priority: P3)

A planner is comparing two or more scenarios and wants to see which scenario performs better in a specific simulation year, not just in aggregate totals. Currently, the comparison table shows summed contributions across all years, which masks year-by-year differences.

**Why this priority**: Scenario comparison is most valuable when comparing apples-to-apples at the same point in time; otherwise, a 3-year scenario will always appear "larger" than a 2-year scenario even if per-year performance is lower.

**Independent Test**: Can be tested by entering comparison mode with two 3-year scenarios, selecting Year 2 from the year picker, and verifying the comparison table updates to show Year 2 metrics for each scenario.

**Acceptance Scenarios**:

1. **Given** comparison mode is active with 2+ scenarios selected, **When** the user selects a specific year from the year picker, **Then** the scenario comparison table updates to show that year's metrics for each scenario.
2. **Given** a year is selected in comparison mode, **When** viewing the Contribution Totals by Scenario bar chart, **Then** the chart reflects contributions for that year only, not cumulative totals.
3. **Given** comparison mode is toggled off and then on again, **When** the year picker was set to a specific year, **Then** the year selection is preserved across the mode toggle.

---

### Edge Cases

- What happens when a single-year simulation is loaded and the user opens the year picker? The picker should show only the one available year and auto-select it.
- What happens when the selected year no longer applies after switching to a different scenario with a different date range? The picker should reset to "All Years" when the active scenario changes.
- What happens when comparison mode includes scenarios with different year ranges? The year picker should only show years present in all selected scenarios; years not available in all scenarios are grayed out or excluded.
- What happens for the 0% bucket when `active_only` is checked? The 0% bucket should reflect only non-enrolled active employees (non-enrolled terminated employees should be excluded when the active-only filter is on).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Deferral Rate Distribution chart MUST include non-enrolled eligible employees in the 0% bucket, so the full eligible population is represented in the distribution.
- **FR-002**: The 0% bucket label or tooltip MUST distinguish between "not enrolled" and "enrolled at 0%" if both categories can exist simultaneously.
- **FR-003**: The DC Plan analytics page MUST display a year picker control in the controls toolbar alongside the existing scenario selector and active-only toggle.
- **FR-004**: The year picker MUST default to "All Years" (aggregate) when a scenario is first loaded.
- **FR-005**: When a specific year is selected, the KPI cards (participation rate, total employee deferrals, employer match, employer core) MUST reflect that year's data only.
- **FR-006**: When a specific year is selected, the Deferral Rate Distribution chart MUST show the distribution for that year only.
- **FR-007**: When a specific year is selected in comparison mode, the comparison table and bar chart MUST show per-year metrics for each scenario rather than cumulative totals.
- **FR-008**: The year picker MUST automatically populate available years from the loaded simulation data (not hardcoded values).
- **FR-009**: Changing the active scenario MUST reset the year picker to "All Years."
- **FR-010**: When `active_only` is enabled, the 0% deferral bucket MUST count only non-enrolled active employees (non-enrolled terminated employees are excluded when the active-only filter is on).

### Key Entities

- **Eligible Employee**: Any employee present in the simulation snapshot for a given year, regardless of enrollment status.
- **Enrolled Employee**: An eligible employee with `is_enrolled_flag = true`.
- **Non-Enrolled Employee**: An eligible employee with `is_enrolled_flag = false` or null — these are effectively at 0% deferral.
- **Simulation Year**: A discrete year integer within the scenario's run range (e.g., 2025, 2026, 2027).
- **Deferral Rate Bucket**: A range category (0%, 1%–9%, 10%+) grouping employees by their current deferral rate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the fix, the sum of all Deferral Rate Distribution bucket counts equals the total eligible population (enrolled + non-enrolled) for the selected year, matching the denominator shown in the KPI participation card.
- **SC-002**: A planner can select any specific simulation year from the year picker and see all charts and KPIs update within 2 seconds, without a full page reload.
- **SC-003**: In comparison mode with a year selected, each scenario column in the comparison table shows that year's metrics, and the values are consistent with the single-scenario view for the same scenario and year.
- **SC-004**: The year picker is populated automatically from simulation data — no hardcoded year ranges — so it works correctly for any scenario start/end date combination.

## Assumptions

- The existing `deferral_distribution_by_year` field returned by the API already contains per-year deferral distribution data (populated by `_get_deferral_distribution_all_years`); the fix for FR-001 applies the same non-enrolled inclusion to this per-year data as well.
- "All Years" in the year picker for contribution totals means cumulative sum across all years (matching current behavior), not the average.
- The Contributions by Year chart retains its multi-year bar view even when a specific year is selected — the selected year is highlighted within the existing chart rather than reducing it to a single bar.
- The API already returns `contribution_by_year` per year and `deferral_distribution_by_year` per year; year-filtered KPI data can be derived client-side from these existing per-year structures without new API parameters.
