# Feature Specification: Fix Vesting Analytics Endpoint AttributeError

**Feature Branch**: `029-fix-vesting-endpoint`
**Created**: 2026-01-28
**Status**: Draft
**Input**: Fix AttributeError in vesting analytics endpoint where Pydantic Scenario object is incorrectly accessed as dictionary

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Vesting Analysis Request (Priority: P1)

A user in PlanAlign Studio opens a workspace and scenario, then navigates to the vesting analysis feature to compare vesting schedules. They submit a vesting analysis request and expect to receive results comparing current vs proposed schedules.

**Why this priority**: This is the core functionality that is currently broken. Users cannot use vesting analysis at all due to the 500 Internal Server Error.

**Independent Test**: Can be fully tested by making a POST request to `/api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` with valid workspace/scenario IDs and verifying a successful response.

**Acceptance Scenarios**:

1. **Given** a valid workspace and scenario with completed simulation data, **When** user requests vesting analysis, **Then** the endpoint returns a successful response with vesting comparison data
2. **Given** a valid workspace and scenario, **When** vesting analysis is requested, **Then** the scenario name is correctly extracted and included in the response

---

### User Story 2 - Error Handling for Missing Data (Priority: P2)

A user attempts vesting analysis on a scenario that has not been simulated yet or where the workspace/scenario does not exist.

**Why this priority**: Proper error handling ensures users receive meaningful feedback rather than cryptic server errors.

**Independent Test**: Can be tested by making requests with invalid workspace/scenario IDs and verifying appropriate 404 error responses.

**Acceptance Scenarios**:

1. **Given** a non-existent workspace ID, **When** user requests vesting analysis, **Then** the endpoint returns 404 with "Workspace not found" message
2. **Given** a non-existent scenario ID, **When** user requests vesting analysis, **Then** the endpoint returns 404 with "Scenario not found" message
3. **Given** a scenario without simulation data, **When** user requests vesting analysis, **Then** the endpoint returns 404 with guidance to run simulation first

---

### Edge Cases

- What happens when scenario name is empty or None? The system should fallback to using the scenario_id as the name.
- What happens when other Scenario attributes are accessed incorrectly elsewhere in the codebase? A code review should identify any similar patterns.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST access Pydantic model attributes using dot notation (e.g., `scenario.name`) rather than dictionary access (e.g., `scenario.get("name")`)
- **FR-002**: System MUST fallback to `scenario_id` if `scenario.name` is None or empty
- **FR-003**: System MUST return appropriate HTTP error codes (404) for missing workspaces, scenarios, or simulation data
- **FR-004**: System MUST maintain existing vesting analysis functionality after the fix

### Key Entities

- **Scenario**: Pydantic BaseModel representing a simulation scenario with attributes: `id`, `workspace_id`, `name`, `description`, `config_overrides`, `status`, `created_at`, `last_run_at`, `last_run_id`, `results_summary`
- **VestingAnalysisRequest**: Request payload containing vesting schedule comparison parameters
- **VestingAnalysisResponse**: Response containing vesting analysis results

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Vesting analytics endpoint returns 200 OK for valid requests (currently returns 500)
- **SC-002**: No AttributeError exceptions occur when accessing Scenario object attributes
- **SC-003**: All existing vesting analysis tests pass after the fix
- **SC-004**: Error responses remain unchanged for invalid workspace/scenario IDs (404 status codes)

## Assumptions

- The `Scenario` Pydantic model will always have a `name` attribute defined (based on model definition)
- The `workspace_storage.get_scenario()` method returns a `Scenario` Pydantic model instance, not a dictionary
- No other endpoints in the codebase have similar dict-access patterns for Pydantic models (should be verified during implementation)

## Root Cause Analysis

**Location**: `planalign_api/routers/vesting.py:70`

**Bug**: Line 70 calls `scenario.get("name", scenario_id)` treating the `Scenario` Pydantic model as a dictionary.

**Fix**: Change to `scenario.name or scenario_id` to properly access the Pydantic model attribute with fallback.

**Impact**: Currently causes 500 Internal Server Error for all vesting analysis requests, completely blocking the feature.
