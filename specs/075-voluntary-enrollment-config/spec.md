# Feature Specification: Voluntary Enrollment Rate Configuration

**Feature Branch**: `075-voluntary-enrollment-config`
**Created**: 2026-03-18
**Status**: Draft
**Input**: User description: "Add voluntary enrollment rate configuration to DC plan page"
**GitHub Issue**: [#247](https://github.com/crzyc98/planwise_navigator/issues/247)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Voluntary Enrollment Rate (Priority: P1)

A plan administrator wants to set the voluntary enrollment rate for a DC plan scenario so that the simulation reflects realistic voluntary participation levels specific to their workforce. They navigate to the DC plan configuration page, find the "Voluntary Enrollment Rate" field, enter a percentage (e.g., 40%), and save. When they run a simulation, the enrollment models use this configured rate as a multiplier on demographic-based enrollment probabilities.

**Why this priority**: This is the core feature — without the ability to set and persist the rate, nothing else works. It delivers the primary value of making voluntary enrollment configurable per scenario.

**Independent Test**: Can be fully tested by setting a voluntary enrollment rate in the UI, running a simulation, and verifying that enrollment counts change proportionally compared to the default behavior.

**Acceptance Scenarios**:

1. **Given** a scenario with no voluntary enrollment rate configured, **When** the user opens the DC plan config page, **Then** the voluntary enrollment rate field displays a placeholder indicating "default behavior" (demographic-based rates apply without modification).
2. **Given** the DC plan config page is open, **When** the user enters 40% as the voluntary enrollment rate and saves, **Then** the value is persisted in the scenario configuration and displayed correctly on subsequent page loads.
3. **Given** a scenario with voluntary enrollment rate set to 40%, **When** a simulation runs, **Then** the enrollment probability for each eligible employee is multiplied by 0.40 compared to the base demographic rate.

---

### User Story 2 - Independence from Auto-Enrollment Toggle (Priority: P1)

A plan administrator wants voluntary enrollment rate to function regardless of whether auto-enrollment is enabled or disabled. When auto-enrollment is OFF, voluntary enrollment is the only path to participation, and the configured rate should still apply. When auto-enrollment is ON, the voluntary rate applies to existing workforce members who were not auto-enrolled.

**Why this priority**: Tied with P1 because the rate must work in both auto-enrollment modes to be useful. If it only works in one mode, the feature is incomplete.

**Independent Test**: Can be tested by running two simulations — one with auto-enrollment ON and one with auto-enrollment OFF — both with the same voluntary enrollment rate, and verifying enrollment occurs in both cases.

**Acceptance Scenarios**:

1. **Given** auto-enrollment is disabled and voluntary enrollment rate is set to 50%, **When** a simulation runs, **Then** approximately 50% of eligible non-enrolled employees enroll voluntarily (subject to demographic adjustments).
2. **Given** auto-enrollment is enabled and voluntary enrollment rate is set to 50%, **When** a simulation runs, **Then** new hires within the auto-enrollment window are auto-enrolled AND existing eligible non-enrolled employees enroll at the configured voluntary rate.
3. **Given** auto-enrollment is enabled and voluntary enrollment rate is set to 0%, **When** a simulation runs, **Then** only auto-enrolled employees participate — no voluntary enrollments occur.

---

### User Story 3 - Validate Rate Input (Priority: P2)

A plan administrator enters an invalid voluntary enrollment rate (e.g., 150%, -10%, or non-numeric text). The system provides immediate feedback that the value must be between 0% and 100%, and prevents saving invalid values.

**Why this priority**: Input validation ensures data integrity but is secondary to core functionality. Users benefit from guardrails but can work around the lack of them by entering valid values.

**Independent Test**: Can be tested by attempting to enter various invalid values and verifying that appropriate validation messages appear and the form cannot be submitted.

**Acceptance Scenarios**:

1. **Given** the DC plan config page is open, **When** the user enters 150% as the voluntary enrollment rate, **Then** a validation message indicates the value must be between 0% and 100%, and the save action is blocked.
2. **Given** the DC plan config page is open, **When** the user enters -5% as the voluntary enrollment rate, **Then** a validation message indicates the value must be between 0% and 100%.
3. **Given** the DC plan config page is open, **When** the user clears the voluntary enrollment rate field and saves, **Then** the system reverts to default behavior (demographic-based rates without multiplier).

---

### Edge Cases

- What happens when the voluntary enrollment rate is set to exactly 0%? No voluntary enrollments should occur; only auto-enrolled employees participate (if auto-enrollment is enabled).
- What happens when the voluntary enrollment rate is set to exactly 100%? All eligible non-enrolled employees enroll voluntarily, effectively overriding demographic variation (enrollment probability capped at 100%).
- What happens when a scenario is duplicated? The voluntary enrollment rate from the source scenario should be copied to the new scenario.
- What happens when a previously set rate is cleared/removed? The system should revert to default demographic-based enrollment behavior (no multiplier applied).
- How does the rate interact with multi-year simulations? The same rate applies each simulation year to newly eligible employees who have not yet enrolled.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to configure a voluntary enrollment rate as a percentage (0%–100%) on the DC plan configuration page.
- **FR-002**: System MUST persist the voluntary enrollment rate per scenario, so each scenario can have its own rate.
- **FR-003**: System MUST apply the configured voluntary enrollment rate as a multiplier to demographic-based enrollment probabilities during simulation.
- **FR-004**: System MUST treat the voluntary enrollment rate as independent of the auto-enrollment toggle — the rate applies whether auto-enrollment is enabled or disabled.
- **FR-005**: System MUST validate that the voluntary enrollment rate is between 0% and 100% inclusive, rejecting values outside this range.
- **FR-006**: System MUST default to existing demographic-based enrollment behavior when no voluntary enrollment rate is explicitly configured (backwards compatible).
- **FR-007**: System MUST apply the voluntary enrollment rate to both new hire proactive enrollment and existing workforce voluntary enrollment models.
- **FR-008**: System MUST preserve demographic-specific deferral rate logic independently of the voluntary enrollment rate (the rate controls whether someone enrolls, not how much they defer).

### Key Entities

- **Voluntary Enrollment Rate**: A decimal value (0.0–1.0) representing the proportion of eligible employees expected to enroll voluntarily. Applied as a multiplier to base demographic enrollment probabilities. Stored per scenario in the scenario configuration.
- **Enrollment Probability**: The base likelihood of an employee enrolling, determined by age group and income level demographics. The voluntary enrollment rate scales this probability.
- **Scenario Configuration**: The per-scenario settings store that holds the voluntary enrollment rate alongside other DC plan parameters like auto-enrollment settings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can set and save a voluntary enrollment rate from the DC plan configuration page in under 30 seconds.
- **SC-002**: Simulation enrollment counts change proportionally when the voluntary enrollment rate is modified (e.g., halving the rate approximately halves voluntary enrollments).
- **SC-003**: Setting the voluntary enrollment rate to 0% results in zero voluntary enrollments across all simulation years.
- **SC-004**: Setting the voluntary enrollment rate to 100% results in all eligible non-enrolled employees enrolling voluntarily.
- **SC-005**: Existing simulations that do not specify a voluntary enrollment rate produce identical results to before this feature was added (backwards compatibility).
- **SC-006**: The voluntary enrollment rate functions correctly regardless of whether auto-enrollment is enabled or disabled.

## Assumptions

- The voluntary enrollment rate acts as a **uniform multiplier** on existing demographic-based enrollment probabilities, not as a flat override. This preserves the relative variation across age/income segments while scaling overall participation.
- Deferral rate selection (how much an employee contributes) remains governed by existing demographic-specific logic and is not affected by the voluntary enrollment rate.
- The existing flexible `config_overrides: Dict[str, Any]` storage pattern is sufficient — no database schema migration is needed.
- The UI field will be presented as a percentage (0–100%) for user friendliness, but stored internally as a decimal (0.0–1.0) for calculation purposes.
- The `AutoEnrollmentOptions` Pydantic model is the appropriate location for this field, as voluntary enrollment is conceptually related to enrollment configuration even though it is independent of the auto-enrollment toggle.

## Scope Boundaries

**In scope**:
- Adding a configurable voluntary enrollment rate field to the DC plan configuration UI
- Persisting the rate per scenario
- Applying the rate as a multiplier in dbt enrollment models
- Input validation (0%–100%)
- Backwards compatibility when the rate is not set

**Out of scope**:
- Configuring different voluntary enrollment rates per demographic segment (age/income groups have their own base rates already)
- Year-over-year rate changes within a single simulation run (same rate applies each year)
- Modifying deferral rate logic or amounts
- Changes to auto-enrollment window or auto-enrollment behavior
