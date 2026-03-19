# Feature Specification: Fix SimulationConfig.from_dict() Failure in Result Handler

**Feature Branch**: `079-fix-config-deser`
**Created**: 2026-03-18
**Status**: Draft
**Input**: User description: "Fix SimulationConfig.from_dict() failure in result handler on run completion"

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

### User Story 1 - Accurate Error Logging on Deserialization Failure (Priority: P1)

As a system operator, I need to understand why SimulationConfig deserialization fails in the result handler, so that I can diagnose and fix the root cause quickly.

**Why this priority**: The current error message is truncated to just "from_dict" method name, completely hiding the actual exception. This prevents diagnosis and means operators cannot determine whether the issue is a type mismatch, unknown field, or missing required field. Without this diagnostic information, debugging takes significantly longer.

**Independent Test**: Can be fully tested by triggering a SimulationConfig deserialization failure and verifying that (1) the error log includes the actual exception type and message (not just "from_dict"), (2) the log output contains enough information to identify the root cause (e.g., "TypeError: expected Decimal, got str", "KeyError: missing_field", etc.), and (3) this diagnostic information is captured consistently across all failure scenarios.

**Acceptance Scenarios**:

1. **Given** a merged config dict passed to `SimulationConfig.from_dict()` contains a Decimal value instead of a string, **When** deserialization is attempted, **Then** the error log shows "TypeError: Decimal type not supported in from_dict" (or similar specific message) instead of just "from_dict"
2. **Given** a merged config dict contains an unknown key that SimulationConfig doesn't expect, **When** deserialization is attempted, **Then** the error log shows the specific key name and the TypeError message instead of truncated output

---

### User Story 2 - Robust Config Deserialization with Key Filtering (Priority: P2)

As a system operator running multi-scenario simulations, I need SimulationConfig deserialization to gracefully handle merged config dicts that may contain extra keys, so that result handling doesn't fail after an otherwise successful simulation.

**Why this priority**: Config merging in Studio adds/drops keys dynamically based on scenario overrides. If from_dict() receives a dict with unknown keys, it raises an exception. This causes result handler to exit early and metadata to not be fully archived. By filtering unknown keys before construction, we make the deserialization robust to dynamic config merging.

**Independent Test**: Can be fully tested by calling `SimulationConfig.from_dict()` with a dict containing (1) all valid fields, (2) valid fields + extra unknown keys, and (3) valid fields minus some optional fields. All three cases should succeed, with case 2 silently stripping unknown keys and case 3 using model defaults.

**Acceptance Scenarios**:

1. **Given** a config dict contains all required fields plus extra unknown keys, **When** `SimulationConfig.from_dict()` is called, **Then** the extra keys are silently filtered out and the object is constructed successfully
2. **Given** a config dict contains required fields but lacks optional fields with defaults, **When** `SimulationConfig.from_dict()` is called, **Then** the object is constructed with default values for missing optional fields

---

### User Story 3 - Type-Safe Config Serialization Upstream (Priority: P3)

As a developer, I need to ensure that Decimal values in simulation config are converted to JSON-serializable types before reaching SimulationConfig.from_dict(), so that type mismatches don't occur during deserialization.

**Why this priority**: This addresses the root cause identified in Issue #235 — Decimal objects are serialized via `model_dump()` but not converted to floats. By using `model_dump(mode='json')` upstream (in the run archiver or logger), Decimal values are already converted before reaching from_dict(), preventing type errors entirely.

**Independent Test**: Can be fully tested by verifying that (1) config serialization uses `model_dump(mode='json')` at the archiver/logger boundary, (2) the resulting dict contains float values instead of Decimal objects, and (3) from_dict() receives only JSON-serializable types.

**Acceptance Scenarios**:

1. **Given** a SimulationConfig with Decimal fields is serialized for archiving, **When** the config is serialized, **Then** `model_dump(mode='json')` is used to convert Decimal values to floats
2. **Given** serialized config is passed to `SimulationConfig.from_dict()`, **When** deserialization is attempted, **Then** no TypeError occurs due to unexpected Decimal type

---

### Edge Cases

- What happens when a merged config dict contains nested Decimal values (e.g., within a dict or list field)?
- How does the system handle extremely large Decimal values that might lose precision when converted to float?
- What if the config contains keys with None values that should be stripped vs. legitimate None values for optional fields?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Result handler error logging MUST capture and display the actual exception type and message (not just the method name)
- **FR-002**: `SimulationConfig.from_dict()` MUST gracefully handle merged config dicts by filtering unknown keys before construction
- **FR-003**: `SimulationConfig.from_dict()` MUST support config dicts with missing optional fields by using model defaults
- **FR-004**: Config serialization at the archiver/logger boundary MUST use `model_dump(mode='json')` to convert Decimal values to floats
- **FR-005**: Result handler MUST complete without exceptions and ensure run metadata is fully archived regardless of deserialization handling
- **FR-006**: The fix MUST be backward compatible with existing code that constructs SimulationConfig correctly

### Key Entities

- **SimulationConfig**: Pydantic model that represents simulation parameters and settings, contains multiple fields of different types including Decimal values
- **Result Handler**: Component that processes simulation results after run completion, merges config, and archives run metadata
- **Run Metadata**: Archive of configuration, run state, database, and audit information saved after simulation completion

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Error logs from result handler show actual exception details (exception type and message) rather than truncated "from_dict" text, enabling sub-5-minute diagnosis of deserialization failures
- **SC-002**: SimulationConfig deserialization succeeds for config dicts containing 0-20% extra unknown keys (typical range from config merging)
- **SC-003**: Result handler completes without exceptions and fully archives run metadata for 100% of simulation runs
- **SC-004**: Run metadata is correctly displayed in Studio UI immediately after simulation completion, with no "undefined" or missing values
- **SC-005**: All existing simulations complete to completion without partial failures due to deserialization issues

## Assumptions

- The fix is applied in three steps as outlined in the GitHub issue: (1) improve error logging, (2) implement key filtering in from_dict(), (3) use model_dump(mode='json') upstream
- Filtering unknown keys is acceptable; we don't need to validate or warn about them
- Decimal values should be converted to float representation in JSON (acceptable precision loss for serialization purposes)
- The affected primary file is `planalign_api/services/simulation/result_handlers.py` with secondary changes in serialization boundaries
- SimulationConfig model schema is stable (no breaking changes to required fields expected during implementation)

## Related Issues

- **Issue #235**: JSON serialization of Decimal values — this fix depends on the upstream serialization solution from #235
- Similar deserialization failures may occur in other parts of the system that receive merged dicts

## Dependencies

- Resolution of Issue #235 for use of `model_dump(mode='json')` in serialization
- Access to result handler code and test data for validation
