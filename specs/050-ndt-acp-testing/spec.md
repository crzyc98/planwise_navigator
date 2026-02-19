# Feature Specification: NDT ACP Testing

**Feature Branch**: `050-ndt-acp-testing`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Add a new top-level Non-Discriminatory Testing section to PlanAlign Studio where users can run IRS compliance tests against completed simulations. Start with the ACP (Actual Contribution Percentage) test."

## Clarifications

### Session 2026-02-19

- Q: Should the ACP formula use the standard IRS definition (employer match + after-tax contributions) or include elective deferrals? → A: Standard IRS ACP definition — employer matching contributions + employee after-tax contributions only. Elective deferrals are reserved for the future ADP test.
- Q: Which employees should be included in the ACP test population? → A: All plan-eligible employees, whether or not they enrolled. Non-participants have 0% ACP per IRS rules.
- Q: Should the alternative ACP test use the full IRS formula or a simplified version? → A: Full IRS formula — alternative test threshold is the lesser of (NHCE ACP x 2) and (NHCE ACP + 2 percentage points), per Treas. Reg. 1.401(m)-2.
- Q: Should ACP results include per-employee detail or only aggregate group statistics? → A: Aggregate summary by default with an expandable per-employee table available on click, showing each employee's ACP, HCE/NHCE status, and contribution amounts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run ACP Test for a Single Scenario (Priority: P1)

A plan administrator wants to verify that a completed simulation passes the IRS ACP non-discrimination test. They navigate to the NDT Testing page from the sidebar, select the ACP test type, choose a simulation year, pick a completed scenario, and click "Run Test." The system displays a clear pass/fail result along with the HCE and NHCE group average ACP percentages.

**Why this priority**: This is the core value proposition. Without the ability to run and view ACP test results for at least one scenario, the feature delivers no compliance insight.

**Independent Test**: Can be fully tested by navigating to NDT Testing, selecting a scenario with a completed simulation, running the ACP test, and verifying the pass/fail result and group averages are displayed. Delivers immediate compliance verification value.

**Acceptance Scenarios**:

1. **Given** a completed simulation for year 2025 in the "baseline" scenario, **When** the user selects ACP test, year 2025, and the "baseline" scenario and clicks "Run Test", **Then** the system displays pass or fail status, HCE average ACP percentage, and NHCE average ACP percentage.
2. **Given** a completed simulation where HCE average ACP exceeds the IRS-allowed margin over NHCE average ACP, **When** the user runs the ACP test, **Then** the system displays "Fail" status and shows the specific percentages and threshold that was exceeded.
3. **Given** a completed simulation where HCE average ACP is within the IRS-allowed margin, **When** the user runs the ACP test, **Then** the system displays "Pass" status with the specific percentages and margin remaining.

---

### User Story 2 - View ACP Test Details and Breakdown (Priority: P2)

After running the ACP test, the administrator wants to see the numerical details behind the result: the contribution rates, IRS thresholds, which test method (basic 1.25x or alternative +2%) was more favorable, and a breakdown of HCE vs NHCE group sizes and contribution statistics. The administrator can also expand a per-employee table to see each individual's ACP, HCE/NHCE classification, and contribution amounts — particularly useful when diagnosing a failing test.

**Why this priority**: The pass/fail result alone (P1) is valuable, but understanding the margin and composition of each group is essential for plan administrators to take action on failing results or understand how close a passing result is to the threshold.

**Independent Test**: Can be tested by running an ACP test and verifying that detailed numerical breakdown is visible beneath the pass/fail summary, including both test methods and the one that was applied.

**Acceptance Scenarios**:

1. **Given** an ACP test has been run, **When** the user views the results, **Then** they see the HCE count, NHCE count, HCE average ACP, NHCE average ACP, the basic test threshold (NHCE x 1.25), the alternative test threshold (lesser of NHCE x 2 and NHCE + 2%), which test was applied (whichever is more favorable to the plan), and the pass/fail determination.
2. **Given** a scenario where the alternative test (+2%) is more favorable than the basic test (x1.25), **When** the user views results, **Then** the system indicates the alternative test was used for the final determination.
3. **Given** an ACP test has been run, **When** the user expands the per-employee detail section, **Then** they see a table listing each eligible employee with their individual ACP percentage, HCE/NHCE classification, employer match amount, and eligible compensation.

---

### User Story 3 - Compare ACP Results Across Multiple Scenarios (Priority: P3)

A plan administrator wants to compare ACP test results across multiple scenarios (e.g., "baseline" vs "high_growth") to understand how different plan designs or workforce assumptions affect compliance. They select multiple scenarios on the NDT Testing page and see a side-by-side comparison of pass/fail status and group averages.

**Why this priority**: Multi-scenario comparison extends the feature from a single-scenario compliance check to a plan design analysis tool. It depends on P1 and P2 working correctly first.

**Independent Test**: Can be tested by selecting two or more completed scenarios, running the ACP test, and verifying a comparison view shows pass/fail and group averages for each scenario side-by-side.

**Acceptance Scenarios**:

1. **Given** two completed scenarios ("baseline" and "high_growth") for year 2025, **When** the user selects both scenarios and runs the ACP test, **Then** the system displays results for each scenario in a comparison layout showing pass/fail, HCE average ACP, and NHCE average ACP per scenario.
2. **Given** one scenario passes and another fails the ACP test, **When** viewing the comparison, **Then** each scenario's pass/fail status is visually distinct (e.g., green for pass, red for fail).

---

### Edge Cases

- What happens when a scenario has no completed simulation for the selected year? The system should display an informative message indicating the simulation has not been run, rather than showing empty or zero results.
- What happens when all employees in a scenario are classified as HCE (no NHCE group)? The system should indicate the test cannot be performed due to insufficient NHCE population and explain why.
- What happens when all employees in a scenario are classified as NHCE (no HCE group)? The system should indicate the test passes by default since there are no HCEs.
- What happens when an employee has zero eligible compensation? That employee should be excluded from the ACP calculation with a note about excluded participants.
- What happens when the selected year is the first simulation year and there is no prior-year compensation data for HCE determination? The system should use the current year's compensation as a fallback and indicate that prior-year data was not available.
- What happens when the IRS HCE compensation threshold is missing from configuration for the relevant year? The system should display an error indicating the missing configuration and which year's threshold is needed.
- What happens when eligible employees have not enrolled in the plan? They are included in the test population with an ACP of 0%, consistent with IRS rules. The results should show the count of eligible-but-not-enrolled participants.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST classify each employee as HCE or NHCE based on prior-year compensation exceeding the IRS HCE compensation threshold for the determination year.
- **FR-002**: System MUST calculate per-employee ACP as (employer matching contributions + employee after-tax contributions) / eligible compensation, per standard IRS ACP test methodology. Elective deferrals (pre-tax and Roth) are excluded from the ACP test and reserved for the future ADP test.
- **FR-002a**: System MUST include all plan-eligible employees in the ACP test population, regardless of whether they enrolled or are actively contributing. Non-participating eligible employees have an ACP of 0%.
- **FR-003**: System MUST compute the average ACP for the HCE group and the NHCE group separately.
- **FR-004**: System MUST apply both the basic ACP test (HCE ACP ≤ NHCE average x 1.25) and the alternative ACP test (HCE ACP ≤ the lesser of NHCE average x 2 and NHCE average + 2 percentage points) per Treas. Reg. 1.401(m)-2, and use whichever test is more favorable to the plan.
- **FR-005**: System MUST determine pass/fail based on whether the HCE average ACP exceeds the more favorable threshold.
- **FR-006**: System MUST display the pass/fail result, HCE average ACP, NHCE average ACP, both test thresholds, and the applied test method.
- **FR-007**: System MUST display the count of employees in each group (HCE and NHCE) and the count of excluded employees (if any).
- **FR-007a**: System MUST provide an expandable per-employee detail table showing each employee's individual ACP, HCE/NHCE classification, employer match amount, and eligible compensation. The table is collapsed by default and expanded on user action.
- **FR-008**: System MUST allow users to select one or more completed scenarios and a simulation year before running the test.
- **FR-009**: System MUST provide a navigation entry point in the sidebar for NDT Testing, accessible from any page.
- **FR-010**: System MUST include the HCE compensation threshold in the IRS limits configuration data for each simulation year.
- **FR-011**: System MUST support displaying ACP results for multiple scenarios simultaneously in a comparison layout.
- **FR-012**: System MUST only allow running NDT tests against years where a simulation has been completed.

### Key Entities

- **HCE Determination**: Classification of each employee as Highly Compensated Employee or Non-Highly Compensated Employee for a given plan year, based on prior-year compensation relative to the IRS threshold. Key attributes: employee identifier, determination year, prior-year compensation, HCE threshold, HCE status (true/false).
- **ACP Calculation**: Per-employee actual contribution percentage for a given plan year. Key attributes: employee identifier, plan year, employer matching contributions, employee after-tax contributions, eligible compensation, calculated ACP percentage, HCE/NHCE classification.
- **ACP Test Result**: Aggregate outcome of the ACP non-discrimination test for a scenario and year. Key attributes: scenario identifier, plan year, HCE count, NHCE count, HCE average ACP, NHCE average ACP, basic test threshold, alternative test threshold, applied test method, pass/fail status.

## Assumptions

- HCE determination uses only the prior-year compensation method. The 5% owner test is out of scope for this MVP.
- "Eligible compensation" is the annual compensation field from the workforce snapshot (the Section 415 compensation limit from `config_irs_limits.csv` is already applied upstream).
- "Employer matching contributions" corresponds to the employer match amount already calculated in the simulation.
- "Employee after-tax contributions" are currently not modeled in the simulation; for MVP, ACP will be calculated using employer matching contributions only. After-tax contribution support can be added when that contribution type is modeled.
- The IRS HCE compensation threshold for 2024 is $155,000 and for 2025 is $160,000. These will be added to the `config_irs_limits.csv` seed.
- Employees who terminated before the end of the plan year are still included in the ACP test if they were eligible participants during the year (consistent with IRS rules).
- The test population includes all plan-eligible employees (enrolled or not). Non-participants have 0% ACP, which lowers group averages consistent with IRS methodology.
- The test type selector defaults to "ACP" since it is the only test available at launch, but the UI is designed to accommodate additional test types (ADP, top-heavy, etc.) in the future.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can run an ACP non-discrimination test and see pass/fail results within 5 seconds of clicking "Run Test" for a single scenario.
- **SC-002**: ACP calculations are mathematically accurate: per-employee ACP = (employer match + after-tax contributions) / compensation, and group averages match the arithmetic mean of individual ACPs.
- **SC-003**: HCE determination correctly classifies 100% of employees based on prior-year compensation vs the IRS threshold for the relevant year.
- **SC-004**: Both IRS test methods (basic 1.25x and alternative +2%) are computed and the more favorable one is applied, matching manual calculation for any test dataset.
- **SC-005**: Users can compare ACP results across 2 or more scenarios in a single view without navigating between pages.
- **SC-006**: The NDT Testing page is accessible from the main navigation within one click from any page in the application.
