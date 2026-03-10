# Feature Specification: Configurable Auto-Enrollment Opt-Out Rates

**Feature Branch**: `068-optout-rate-config`
**Created**: 2026-03-10
**Status**: Draft
**Input**: User description: "Expose auto-enrollment opt-out rate as configurable UI field (GitHub Issue #201)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Opt-Out Rates by Age Band (Priority: P1)

An analyst opens a scenario in PlanAlign Studio and navigates to the DC Plan configuration section. They see a collapsible "Opt-Out Assumptions" panel with pre-populated default values. They expand the "By Age" group and adjust the opt-out rate for young employees (ages 18-25) from 35% to 45% to model a scenario where younger workers are more likely to opt out of auto-enrollment. They save the scenario configuration.

**Why this priority**: This is the core value proposition. Without the ability to view and edit opt-out rates in the UI, analysts must manually edit YAML files, which is error-prone and inaccessible to non-technical users.

**Independent Test**: Can be fully tested by opening the DC Plan config, modifying age-based opt-out rates, saving, and verifying the values persist when the scenario is reloaded.

**Acceptance Scenarios**:

1. **Given** a scenario is open in PlanAlign Studio, **When** the analyst expands the DC Plan configuration section, **Then** they see a collapsible "Opt-Out Assumptions" panel with current opt-out rate values pre-populated.
2. **Given** the Opt-Out Assumptions panel is expanded, **When** the analyst modifies the "Young (18-25)" opt-out rate to 0.45, **Then** the value is accepted and displayed as 45%.
3. **Given** the analyst has modified opt-out rates, **When** they save the scenario configuration, **Then** the new values are persisted and displayed correctly when the scenario is reopened.

---

### User Story 2 - Configure Opt-Out Rates by Income Band (Priority: P1)

An analyst adjusts income-based opt-out rates to model how compensation levels affect auto-enrollment participation. They modify the low-income opt-out rate from 40% to 50% and the executive opt-out rate from 5% to 3%, then save the configuration.

**Why this priority**: Income-based opt-out rates are equally important to age-based rates for accurate participation modeling. Both are needed for realistic scenario analysis.

**Independent Test**: Can be fully tested by opening DC Plan config, modifying income-based opt-out rates, saving, and verifying values persist.

**Acceptance Scenarios**:

1. **Given** the Opt-Out Assumptions panel is expanded, **When** the analyst views the "By Income" group, **Then** they see four income-band opt-out rate fields with current values.
2. **Given** the analyst modifies income-band opt-out rates, **When** they save the configuration, **Then** the new rates are persisted and used in subsequent simulations.

---

### User Story 3 - Simulation Uses Custom Opt-Out Rates (Priority: P1)

An analyst configures custom opt-out rates in PlanAlign Studio and runs a simulation. The simulation engine uses the analyst's custom rates instead of the hardcoded defaults, producing enrollment results that reflect the custom assumptions.

**Why this priority**: The end-to-end data flow is essential — without this, the UI fields would be cosmetic only and provide no analytical value.

**Independent Test**: Can be tested by setting distinctive opt-out rates (e.g., 0.99 for all age bands), running a simulation, and verifying that nearly all auto-enrolled employees opt out.

**Acceptance Scenarios**:

1. **Given** custom opt-out rates are saved in a scenario, **When** the analyst runs a simulation, **Then** the simulation uses the custom rates for enrollment event generation.
2. **Given** no custom opt-out rates are configured, **When** the analyst runs a simulation, **Then** the simulation uses the existing default values (matching current hardcoded behavior).
3. **Given** an analyst sets the young age band opt-out rate to 0.99, **When** they run a simulation with new hires predominantly in the 18-25 age range, **Then** the vast majority of auto-enrolled young employees opt out.

---

### User Story 4 - Reset Opt-Out Rates to Defaults (Priority: P2)

An analyst who has customized opt-out rates wants to return to the system defaults. They click a "Reset to Defaults" action, and all opt-out rate fields revert to the standard values.

**Why this priority**: Provides a safety net for analysts who want to undo experimental changes without remembering the original default values.

**Independent Test**: Can be tested by modifying rates, clicking reset, and verifying all fields return to default values.

**Acceptance Scenarios**:

1. **Given** the analyst has modified opt-out rates, **When** they click "Reset to Defaults", **Then** all opt-out rate fields revert to the system default values.
2. **Given** rates have been reset, **When** the analyst saves the configuration, **Then** the default values are persisted.

---

### Edge Cases

- What happens when an analyst enters a value outside the valid range (e.g., negative number or greater than 1.0)?
  - The system rejects invalid values and displays a validation message indicating the acceptable range (0.00 to 1.00).
- What happens when an analyst clears an opt-out rate field and leaves it empty?
  - The system treats empty fields as using the default value, preventing incomplete configurations.
- What happens when a scenario was created before this feature existed (no opt-out rates in config)?
  - The system gracefully falls back to the existing hardcoded defaults, maintaining backward compatibility.
- What happens when all opt-out rates are set to 0.00?
  - The simulation produces zero opt-outs for auto-enrolled employees, resulting in 100% auto-enrollment participation.
- What happens when all opt-out rates are set to 1.00?
  - The simulation produces opt-outs for all auto-enrolled employees, resulting in 0% auto-enrollment participation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a collapsible "Opt-Out Assumptions" section within the DC Plan configuration area of PlanAlign Studio.
- **FR-002**: System MUST provide 4 age-band opt-out rate input fields: Young (18-25), Mid-Career (26-35), Mature (36-50), Senior (51+).
- **FR-003**: System MUST provide 4 income-band opt-out rate input fields: Low Income (<$30k), Moderate ($30k-$50k), High ($50k-$100k), Executive (>$100k).
- **FR-004**: System MUST pre-populate all opt-out rate fields with the current default values when no custom values have been set.
- **FR-005**: System MUST validate that all opt-out rate values are between 0.00 and 1.00 (inclusive).
- **FR-006**: System MUST persist custom opt-out rates as part of the scenario configuration.
- **FR-007**: System MUST pass custom opt-out rates through to the simulation engine so they are used during enrollment event generation.
- **FR-008**: System MUST fall back to default opt-out rates when a scenario has no custom values configured (backward compatibility).
- **FR-009**: System MUST provide a "Reset to Defaults" action that restores all opt-out rate fields to their default values.
- **FR-010**: System MUST display help text for each demographic segment explaining what the opt-out rate controls.
- **FR-011**: Opt-out rates MUST only apply to auto-enrolled employees, not voluntarily enrolled employees (preserving existing behavior).

### Key Entities

- **Opt-Out Rate Configuration**: A set of 8 demographic-segmented rates (4 age-band, 4 income-band) that control auto-enrollment opt-out probability. Associated with a scenario configuration.
- **Scenario Configuration**: Extended to include opt-out rate overrides alongside existing DC Plan parameters (eligibility, deferral, match formulas).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Analysts can view and modify all 8 opt-out rate fields within 30 seconds of opening the DC Plan configuration panel.
- **SC-002**: Custom opt-out rates persist correctly across scenario save/reload cycles with 100% fidelity.
- **SC-003**: Simulations using custom opt-out rates produce measurably different enrollment participation compared to default rates (verifiable by comparing two simulation runs).
- **SC-004**: Existing scenarios without custom opt-out rates continue to produce identical simulation results as before this feature (zero regression).
- **SC-005**: All 8 opt-out rate fields reject values outside the 0.00-1.00 range with clear user feedback.

## Assumptions

- The existing demographic segmentation (4 age bands, 4 income bands) is sufficient and does not need to be expanded or made configurable in this feature.
- The opt-out rate fields use decimal values (0.00 to 1.00) for internal storage, but may display as percentages in the UI for readability.
- The existing probabilistic opt-out logic in the enrollment event model does not need modification — only the variable values passed to it change.
- Default values match the current hardcoded values in the project configuration.
