# Feature Specification: NDT ADP (Actual Deferral Percentage) Test

**Feature Branch**: `052-ndt-adp-test`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Add ADP (Actual Deferral Percentage) test to the NDT suite"

## Clarifications

### Session 2026-02-19

- Q: When ADP test fails, should the system only report pass/fail, or also calculate corrective action amounts? → A: Report + suggest — show pass/fail and also calculate the excess HCE deferral amount needed to pass.
- Q: Where does safe harbor status come from — plan config, UI toggle, or both? → A: UI toggle at test time, similar to the existing "Include Match" toggle for 401(a)(4).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run ADP Test for a Single Scenario (Priority: P1)

A plan administrator selects a completed simulation scenario and year, then runs the ADP test to determine whether the plan's elective deferral distribution between HCE and NHCE groups complies with IRS nondiscrimination requirements.

**Why this priority**: The ADP test is the core deliverable. Without single-scenario execution, no other functionality has value.

**Independent Test**: Can be fully tested by selecting one scenario and year, running the ADP test, and verifying pass/fail result with HCE/NHCE average ADPs, applied prong, and margin.

**Acceptance Scenarios**:

1. **Given** a completed simulation scenario with eligible participants who have elective deferrals, **When** the user runs the ADP test for a specific year, **Then** the system displays: pass/fail result, HCE average ADP, NHCE average ADP, which prong (basic or alternative) was applied, the threshold used, and the margin.
2. **Given** a completed simulation scenario, **When** the user runs the ADP test, **Then** each participant's individual ADP is calculated as (pre-tax + Roth elective deferrals) / plan compensation.
3. **Given** a scenario where HCE average ADP is 6% and NHCE average ADP is 5%, **When** the ADP test runs, **Then** the basic test threshold is 6.25% (5% x 1.25), and the plan passes with margin of 0.25%.
4. **Given** a scenario where HCE average ADP is 3% and NHCE average ADP is 1.5%, **When** the ADP test runs, **Then** the alternative test threshold is 3.0% (lesser of 1.5% x 2 = 3.0% and 1.5% + 2% = 3.5%), and the plan passes with margin of 0.0%.
5. **Given** a scenario where HCE average ADP exceeds both prong thresholds, **When** the ADP test runs, **Then** the test result is "fail" with a negative margin indicating the excess amount, and the system calculates the total excess HCE deferral amount that would need to be reduced for the plan to pass.
6. **Given** a failing ADP test result, **When** the user reviews the output, **Then** the excess HCE deferral amount is displayed alongside the pass/fail result and margin.

---

### User Story 2 - Compare ADP Results Across Scenarios (Priority: P2)

A plan administrator selects multiple completed scenarios and runs the ADP test to compare how different plan designs or workforce compositions affect ADP compliance.

**Why this priority**: Scenario comparison is a core value proposition of PlanAlign Engine and follows the established NDT comparison pattern.

**Independent Test**: Can be tested by selecting 2-6 scenarios, running the ADP test, and verifying side-by-side results are displayed for each scenario.

**Acceptance Scenarios**:

1. **Given** 2-6 completed simulation scenarios, **When** the user runs the ADP test in comparison mode, **Then** the system displays ADP results for each scenario in a side-by-side grid layout.
2. **Given** multiple scenarios in comparison mode, **When** the user reorders scenarios, **Then** the display order updates accordingly.

---

### User Story 3 - View Participant-Level ADP Detail (Priority: P2)

A plan administrator expands the ADP test results to see individual participant detail, including each participant's deferral amount, compensation, individual ADP percentage, and HCE/NHCE classification.

**Why this priority**: Participant-level detail enables audit support and root cause analysis when a test fails, but is not required for the core pass/fail determination.

**Independent Test**: Can be tested by running the ADP test, toggling on employee detail, and verifying each participant row shows correct individual ADP calculation.

**Acceptance Scenarios**:

1. **Given** ADP test results are displayed, **When** the user requests participant-level detail, **Then** the system shows each eligible participant's employee ID, HCE status, elective deferral amount, plan compensation, and individual ADP percentage.
2. **Given** participant-level detail is displayed, **When** the user reviews the data, **Then** HCE and NHCE participants are clearly distinguished.

---

### User Story 4 - Safe Harbor Plan Exemption (Priority: P3)

A plan administrator runs the ADP test for a plan that has safe harbor status. The system recognizes the exemption and skips the ADP calculation, displaying a clear message that the plan is exempt.

**Why this priority**: Safe harbor exemption is an important compliance feature but applies only to plans with that specific designation.

**Independent Test**: Can be tested by configuring a plan with safe harbor status, running the ADP test, and verifying the system returns an "exempt" status without performing the calculation.

**Acceptance Scenarios**:

1. **Given** the ADP test interface is displayed, **When** the user toggles the "Safe Harbor" option on and runs the test, **Then** the system displays an "exempt" result with a message indicating the plan is not required to run ADP due to safe harbor status.
2. **Given** the "Safe Harbor" toggle is off (default), **When** the user runs the ADP test, **Then** the system performs the full ADP calculation as normal.
3. **Given** the user is in comparison mode with multiple scenarios, **When** the "Safe Harbor" toggle is on, **Then** all scenarios display exempt status.

---

### Edge Cases

- What happens when a participant has zero plan compensation? They are excluded from the test, and the count of excluded participants is reported.
- What happens when there are no HCE or no NHCE participants? The test returns an error result with a descriptive message explaining the group is empty.
- How are mid-year entrants handled? Their elective deferrals and compensation reflect only the portion of the year they were eligible, using the prorated amounts already calculated by the simulation engine.
- What happens when a participant is eligible for the plan but has zero elective deferrals? They are included in the test with an individual ADP of 0%, as they are eligible but not deferring.
- What if the IRS limits table does not have an entry for the requested plan year? The system returns an error result indicating missing configuration data.
- What happens when prior year testing method is selected but no prior year simulation data exists? The system falls back to current year testing and includes a warning message in the result.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate each participant's Actual Deferral Percentage as employee elective deferrals (pre-tax + Roth combined) divided by plan compensation.
- **FR-002**: System MUST separate eligible participants into HCE and NHCE groups using the same HCE determination logic as existing NDT tests (prior-year compensation compared to IRS threshold).
- **FR-003**: System MUST compute the average ADP for each group (HCE and NHCE) as the arithmetic mean of individual ADPs within the group.
- **FR-004**: System MUST apply the IRS two-prong test using the current year testing method by default:
  - **Basic test (Prong 1)**: HCE average ADP must not exceed NHCE average ADP x 1.25
  - **Alternative test (Prong 2)**: HCE average ADP must not exceed the lesser of (NHCE average ADP + 2 percentage points) OR (NHCE average ADP x 2)
- **FR-005**: System MUST determine the plan passes if either prong is satisfied, applying the more favorable prong (the one that produces the higher threshold).
- **FR-006**: System MUST output: pass/fail/exempt result, HCE average ADP, NHCE average ADP, which prong was applied (basic or alternative), the threshold used, and the margin (positive = passing, negative = failing).
- **FR-007**: System MUST exclude participants who are not eligible for elective deferrals in the plan year, and report the count of excluded participants.
- **FR-008**: System MUST include eligible participants with zero deferrals in the ADP calculation (individual ADP = 0%).
- **FR-009**: System MUST support an optional participant-level detail view showing each participant's employee ID, HCE status, elective deferral amount, plan compensation, individual ADP, and prior-year compensation.
- **FR-010**: System MUST support multi-scenario comparison (up to 6 scenarios) following the same comparison pattern as existing NDT tests.
- **FR-011**: System MUST provide a "Safe Harbor" toggle in the ADP test interface (off by default). When enabled, the system returns an "exempt" result without performing the ADP calculation.
- **FR-012**: System MUST support configurable testing method (current year or prior year) per plan, defaulting to current year. When prior year method is selected, the NHCE average ADP from the prior simulation year is used as the baseline for the two-prong test.
- **FR-013**: System MUST reference the IRS limits table for the applicable plan year to determine HCE compensation thresholds.
- **FR-014**: System MUST use the same census and contribution data sources as the existing ACP and 401(a)(4) tests.
- **FR-015**: When the ADP test fails, the system MUST calculate the total excess HCE deferral amount — the aggregate dollar amount by which HCE elective deferrals would need to be reduced for the HCE average ADP to meet the more favorable prong threshold. This is a reporting suggestion only; the system does not perform or trigger actual corrective distributions.

### Key Entities

- **ADP Test Result**: Represents the outcome of an ADP test for a single scenario and year, including pass/fail/exempt status, group averages, applied prong, threshold, margin, and (when failing) the excess HCE deferral amount needed to pass.
- **ADP Employee Detail**: Represents an individual participant's ADP test data including their elective deferrals, plan compensation, individual ADP percentage, and HCE classification.
- **HCE/NHCE Group**: Classification of eligible participants into Highly Compensated Employee and Non-Highly Compensated Employee groups based on prior-year compensation and IRS thresholds.
- **Testing Method Configuration**: Plan-level setting indicating whether ADP testing uses current year or prior year NHCE data, defaulting to current year.
- **Safe Harbor Toggle**: A user-controlled option at test time (off by default) indicating the plan meets safe harbor requirements and is exempt from ADP testing. Follows the same pattern as the "Include Match" toggle on the 401(a)(4) test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can run the ADP test and receive pass/fail/exempt results within the same response time as existing NDT tests (ACP, 401(a)(4), 415).
- **SC-002**: ADP test results are mathematically consistent: individual ADPs sum correctly to group averages, and the two-prong test logic matches IRS regulatory definitions.
- **SC-003**: ADP test results for safe harbor plans immediately return exempt status without performing unnecessary calculations.
- **SC-004**: Users can compare ADP results across up to 6 scenarios simultaneously in the same comparison interface used for other NDT tests.
- **SC-005**: Participant-level detail provides sufficient information for audit support, including all inputs to the individual ADP calculation.
- **SC-006**: The ADP test follows the same user interaction patterns as existing NDT tests (test type selection, year selection, scenario selection, comparison mode, employee detail toggle), requiring no additional user training.
- **SC-007**: When the ADP test fails, the excess HCE deferral amount is displayed, giving plan administrators an actionable corrective target without requiring manual calculation.

## Assumptions

- Elective deferrals (pre-tax + Roth) are available from the same workforce snapshot data used by other NDT tests. The existing prorated annual contributions field represents employee elective deferrals.
- Safe harbor status is controlled via a UI toggle at test time (off by default), requiring no changes to plan configuration schema. This matches the "Include Match" toggle pattern used by the 401(a)(4) test.
- The testing method (current year vs. prior year) follows the same pattern as HCE determination: current year uses the same year's NHCE data, prior year uses the previous simulation year's NHCE data.
- Mid-year entrants use the prorated compensation and contribution amounts already calculated by the simulation engine, so no additional proration logic is needed in the ADP test itself.
- The ADP test will be integrated into the existing NDT testing interface as a new test type option alongside ACP, 401(a)(4), and 415.
