# Feature Specification: Fix Target Compensation Growth Persistence

**Feature Branch**: `064-fix-comp-growth-persist`
**Created**: 2026-03-09
**Status**: Draft
**Input**: User description: "Fix target compensation growth not persisted across sessions (GitHub Issue #199)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persist Target Compensation Growth Value (Priority: P1)

As a plan administrator, I set the "Target Compensation Growth" slider to a specific value (e.g., 7.5%), click "Calculate Settings" to derive merit/COLA/promotion rates, and save the scenario. When I navigate away and return to the Compensation section, I expect to see the same 7.5% value I previously set, not a hardcoded default.

**Why this priority**: This is the core bug. Without persistence, the target growth input resets on every component mount, making the slider effectively useless for saved scenarios. Users cannot trust that their compensation configuration is retained.

**Independent Test**: Can be tested by setting the target growth slider, saving the scenario, navigating away, and returning to verify the value is preserved.

**Acceptance Scenarios**:

1. **Given** a scenario with no prior compensation growth target set, **When** the user opens the Compensation section, **Then** the slider displays the default value of 5.0%.
2. **Given** a user sets the target growth to 7.5% and saves the scenario, **When** the user navigates away and returns to the Compensation section, **Then** the slider displays 7.5%.
3. **Given** a user sets the target growth to 7.5% and saves, **When** the user clicks "Calculate Settings" on return, **Then** the derived merit/COLA/promotion rates match what 7.5% would produce (not what 5.0% would produce).

---

### User Story 2 - Round-Trip Through API (Priority: P1)

As the system, when a scenario is saved, the target compensation growth value must be included in the API payload sent to the backend, stored in the scenario configuration, and returned when the scenario is loaded.

**Why this priority**: Without backend persistence, the frontend fix alone would only survive within a single browser session. True persistence requires the full stack round-trip.

**Independent Test**: Can be tested by saving a scenario via the API with a target growth value, then loading it via the API and verifying the value is returned.

**Acceptance Scenarios**:

1. **Given** a scenario with target compensation growth set to 8.0%, **When** the scenario is saved via the API, **Then** the payload includes the target compensation growth value.
2. **Given** a saved scenario with target compensation growth of 8.0%, **When** the scenario is loaded via the API, **Then** the response includes the target compensation growth value of 8.0%.
3. **Given** a scenario saved before this fix (no target growth field), **When** the scenario is loaded, **Then** the system defaults to 5.0% without errors.

---

### Edge Cases

- What happens when a scenario saved before this fix is loaded? The system should gracefully default to 5.0%.
- What happens if the backend receives a payload without the target growth field? It should use the default of 5.0%.
- What happens if the user changes the target growth but does not click "Save"? The unsaved value should not persist (standard form behavior).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The frontend form data model MUST include a target compensation growth field to hold the slider value.
- **FR-002**: The default form data MUST include a default value of 5.0 for target compensation growth.
- **FR-003**: The configuration payload builder MUST include the target compensation growth value in the data sent to the backend when saving.
- **FR-004**: The configuration context MUST hydrate the target compensation growth value from scenario overrides when loading a saved scenario.
- **FR-005**: The compensation section MUST initialize the target growth slider from the persisted form data instead of a hardcoded default.
- **FR-006**: The backend compensation settings model MUST include a field for the target compensation growth percentage.
- **FR-007**: The API scenario configuration schema MUST include the target compensation growth field.
- **FR-008**: The system MUST handle backward compatibility by defaulting to 5.0% when loading scenarios that were saved without this field.

### Key Entities

- **Scenario Configuration**: The saved configuration for a simulation scenario, extended to include target compensation growth percentage.
- **Compensation Settings**: Backend model representing compensation parameters, extended with a target growth field.
- **FormData**: Frontend data model for the configuration form, extended with target compensation growth.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Target compensation growth value survives a full save-navigate-reload cycle with 100% fidelity (value set equals value displayed on return).
- **SC-002**: Scenarios saved before this fix load without errors, displaying the default 5.0% target growth.
- **SC-003**: The "Calculate Settings" function produces correct derived rates based on the persisted target growth value, not a hardcoded default.
- **SC-004**: The target compensation growth value round-trips through the API (frontend to backend to frontend) without data loss or transformation errors.

## Assumptions

- The default target compensation growth value is 5.0%, consistent with the current hardcoded value in `CompensationSection.tsx`.
- The field name in the API payload follows existing project conventions.
- No database migration is required since scenario configurations are stored as flexible documents/YAML.
