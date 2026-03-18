# Feature Specification: Fix JSON Serialization of Decimal Values in Logger

**Feature Branch**: `078-fix-json-serializer`
**Created**: 2026-03-18
**Status**: Draft
**Input**: User description: "Fix JSON serialization of Decimal values in logger"

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.

  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Fix Logger Crash When Serializing Configuration (Priority: P1)

As a system operator, I need the orchestrator to start successfully and log configuration without throwing a TypeError, so that simulation initialization completes without errors.

**Why this priority**: This is a critical blocker - the application crashes during initialization when attempting to log configuration containing Decimal values. Without fixing this, no simulations can run.

**Independent Test**: Can be fully tested by initializing PipelineOrchestrator with a config containing Decimal fields and verifying that (1) no TypeError is raised, and (2) the configuration is successfully logged to JSON format.

**Acceptance Scenarios**:

1. **Given** a PipelineOrchestrator is initialized with configuration containing Decimal fields, **When** `observability.set_configuration()` is called during initialization, **Then** the configuration is serialized to JSON without raising a TypeError
2. **Given** configuration is logged to JSON, **When** the JSON output is parsed, **Then** all Decimal values are represented as valid JSON numbers (not as objects)

---

### User Story 2 - Ensure All Pydantic Models with Decimals Serialize Correctly (Priority: P2)

As a developer, I need all Pydantic models with Decimal fields to serialize consistently to JSON, so that logging and data export work reliably across the entire system.

**Why this priority**: This ensures robustness for any future config models or event data that may contain Decimal values. It prevents similar bugs from occurring elsewhere in the codebase.

**Independent Test**: Can be fully tested by verifying that `model_dump(mode='json')` is used appropriately at serialization boundaries (when converting Pydantic models to JSON), with unit tests confirming Decimal serialization works as expected.

**Acceptance Scenarios**:

1. **Given** any Pydantic model with Decimal fields, **When** serialized using `model_dump(mode='json')`, **Then** all Decimal values are converted to floats in the resulting dictionary
2. **Given** run_summary configuration is being logged, **When** the config is serialized, **Then** Decimal values are automatically converted without custom encoder logic

---

### Edge Cases

- What happens when a config contains nested Decimal values (e.g., within a list or dict)?
- How does the system handle very large Decimal values that might lose precision when converted to float?
- What if a Decimal value is NaN or Infinity?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST serialize Pydantic model configurations containing Decimal fields to JSON format without errors
- **FR-002**: System MUST apply serialization at the source (when converting models to dicts for JSON output) rather than patching the JSON encoder
- **FR-003**: System MUST ensure that all Decimal values in configuration are converted to numeric representations (floats) in JSON output
- **FR-004**: System MUST log configuration during PipelineOrchestrator initialization without throwing TypeErrors
- **FR-005**: System MUST maintain data accuracy when converting Decimals to JSON-serializable formats (appropriate precision handling)

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: PipelineOrchestrator initialization completes successfully without TypeErrors when configuration contains Decimal values
- **SC-002**: Configuration logging produces valid JSON output parseable by standard JSON parsers
- **SC-003**: All existing simulations that previously failed with "Object of type Decimal is not JSON serializable" now run to completion
- **SC-004**: Unit tests confirm that Decimal serialization works correctly for all affected code paths (logger.py, run_summary.py, pipeline_orchestrator.py)

## Assumptions

- The fix should be applied at the serialization boundary (using Pydantic's `model_dump(mode='json')`) rather than creating a custom JSON encoder
- Decimal values should be converted to float representation in JSON output (acceptable precision loss for logging purposes)
- The affected files are `logger.py:57`, `run_summary.py:129`, and `pipeline_orchestrator.py:118` as identified in the bug report
