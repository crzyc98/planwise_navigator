# Feature Specification: Vesting Hours Requirement Toggle

**Feature Branch**: `030-vesting-hours-toggle`
**Created**: 2026-01-29
**Status**: Draft
**Input**: User description: "Add 1000-hour vesting requirement toggle to the Vesting Analysis UI"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Hours Requirement for Schedule Comparison (Priority: P1)

As a plan administrator, I want to toggle the 1000-hour vesting requirement for each schedule being compared so that I can model forfeitures with and without this common ERISA provision.

**Why this priority**: This is the core feature request - enabling the hours requirement configuration is the primary value delivered.

**Independent Test**: Can be fully tested by opening the Vesting Analysis page, toggling the hours requirement on for one or both schedules, and verifying the toggle state is reflected in the UI.

**Acceptance Scenarios**:

1. **Given** I am on the Vesting Analysis page with a workspace and scenario selected, **When** I view the schedule selection area, **Then** I see a toggle/checkbox labeled "Require 1,000 hours" next to each schedule selector (current and proposed).

2. **Given** a schedule's hours requirement toggle is enabled, **When** I look at the schedule configuration section, **Then** I see an input field to customize the hours threshold with a default value of 1000.

3. **Given** a schedule's hours requirement toggle is disabled, **When** I look at the schedule configuration section, **Then** the hours threshold input is hidden or disabled.

---

### User Story 2 - Analyze with Hours Requirement Applied (Priority: P1)

As a plan administrator, I want the hours requirement settings to be sent to the API when I click Analyze so that the forfeiture calculations reflect the configured parameters.

**Why this priority**: Without passing the values to the API, the toggle would have no functional effect - equally critical as the UI controls.

**Independent Test**: Can be tested by enabling the hours requirement, clicking Analyze, and verifying the API request payload includes `require_hours_credit: true` and `hours_threshold` values.

**Acceptance Scenarios**:

1. **Given** I have enabled hours requirement for the current schedule with threshold 1000, **When** I click Analyze, **Then** the API request includes `current_schedule.require_hours_credit: true` and `current_schedule.hours_threshold: 1000`.

2. **Given** I have disabled hours requirement for the proposed schedule, **When** I click Analyze, **Then** the API request includes `proposed_schedule.require_hours_credit: false`.

3. **Given** I have set a custom hours threshold of 750 for a schedule, **When** I click Analyze, **Then** the API request reflects `hours_threshold: 750` for that schedule.

---

### User Story 3 - View Hours Requirement in Results Summary (Priority: P2)

As a plan administrator, I want to see which hours requirement settings were used in the analysis results so that I can verify the analysis matches my intended configuration.

**Why this priority**: Important for transparency and trust in results, but secondary to the core configuration capability.

**Independent Test**: Can be tested by running an analysis with hours requirement enabled and verifying the results summary displays the hours configuration.

**Acceptance Scenarios**:

1. **Given** I have run an analysis with hours requirement enabled for the current schedule, **When** I view the results, **Then** I see an indication that the current schedule analysis applied a 1000-hour (or custom threshold) requirement.

2. **Given** I have run an analysis with hours requirement disabled for both schedules, **When** I view the results, **Then** the display indicates no hours requirement was applied (or omits the hours mention entirely).

3. **Given** I have run an analysis with different hours settings per schedule, **When** I view the results, **Then** I can distinguish which settings were applied to which schedule.

---

### User Story 4 - Understand Hours Requirement Impact (Priority: P3)

As a plan administrator, I want clear explanatory text about what the hours requirement does so that I understand its impact before enabling it.

**Why this priority**: Improves usability and reduces user confusion, but not critical for core functionality.

**Independent Test**: Can be tested by viewing the hours requirement toggle area and verifying explanatory text is present and accurate.

**Acceptance Scenarios**:

1. **Given** I am viewing the hours requirement toggle area, **When** I look for explanatory information, **Then** I see text explaining that employees who don't meet the threshold lose one year of vesting credit.

---

### Edge Cases

- What happens when hours threshold is set to 0? System accepts 0 as a valid threshold (effectively no hours requirement even if toggled on).
- What happens when hours threshold is set above 2080? System prevents input above 2080 (maximum reasonable annual work hours).
- What happens when user toggles hours requirement on/off multiple times before analyzing? System uses the final toggle state when Analyze is clicked.
- How does the UI behave when results are already displayed and user changes hours settings? The existing results remain visible but represent the previous configuration; user must click Analyze again to update.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a toggle/checkbox for hours requirement next to each schedule selector (current and proposed).
- **FR-002**: System MUST show an hours threshold input field when the toggle is enabled, with a default value of 1000.
- **FR-003**: System MUST hide or disable the hours threshold input when the toggle is disabled.
- **FR-004**: System MUST validate hours threshold is between 0 and 2080 inclusive.
- **FR-005**: System MUST include `require_hours_credit` and `hours_threshold` in the API request payload for both schedules.
- **FR-006**: System MUST display the hours requirement configuration used in the analysis results summary.
- **FR-007**: System MUST show explanatory text indicating that employees not meeting the hours threshold lose one year of vesting credit.
- **FR-008**: System MUST preserve hours requirement settings when switching between schedule types.

### Key Entities

- **VestingScheduleConfig**: Extended UI state to include `require_hours_credit` (boolean) and `hours_threshold` (number) matching the existing TypeScript interface.
- **Analysis Results Display**: Enhanced to show hours requirement parameters used in the analysis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure hours requirement settings for both schedules in under 30 seconds (toggle + optional threshold adjustment).
- **SC-002**: 100% of API requests include the correct hours requirement parameters matching the UI state.
- **SC-003**: Analysis results clearly indicate hours requirement settings for both schedules when applicable.
- **SC-004**: Users can differentiate between analyses run with and without hours requirements by viewing the results summary.

## Assumptions

- The backend API already fully supports `require_hours_credit` and `hours_threshold` parameters (confirmed via backend model inspection).
- The TypeScript types in `api.ts` already include these fields in `VestingScheduleConfig` (confirmed).
- The hours threshold default of 1000 is the industry standard for ERISA vesting credit requirements.
- The maximum threshold of 2080 represents a full-time work year (52 weeks x 40 hours).
- Explanatory text should be concise and positioned near the toggle without requiring a modal or tooltip.
