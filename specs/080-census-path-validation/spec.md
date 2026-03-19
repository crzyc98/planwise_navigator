# Feature Specification: Enforce Census Path Validation on Simulation Start

**Feature Branch**: `080-census-path-validation`
**Created**: 2026-03-18
**Status**: Draft
**Input**: User description: "Silent fallback to default census path when census_parquet_path missing from scenario config"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Census File Upload and Validation (Priority: P1)

Studio user uploads a census parquet file to a scenario folder and launches a simulation. The system validates that the census file exists and is readable before proceeding with the simulation run.

**Why this priority**: This is the primary success path. Users must be able to upload a census file and have confidence that the simulation uses the correct dataset. This is the MVP that delivers immediate value by preventing silent data corruption.

**Independent Test**: Can be fully tested by uploading a census file to a scenario, launching a simulation, and verifying that the run completes successfully with the uploaded census file in use.

**Acceptance Scenarios**:

1. **Given** a scenario with a valid census parquet file in the scenario folder, **When** the user launches a simulation from Studio, **Then** the simulation proceeds using the uploaded census file and succeeds.
2. **Given** a scenario with a valid census parquet file, **When** the simulation completes, **Then** the results are based on the uploaded census dataset (no fallback to default).

---

### User Story 2 - Missing Census File Error Messaging (Priority: P1)

Studio user attempts to run a simulation without uploading a census file. The system detects the missing census file before execution and displays a clear, actionable error message explaining what is required.

**Why this priority**: This is critical for user experience and data integrity. Rather than silently using a default census (corrupting results), the system must fail fast and guide the user to upload a census file. This prevents invalid simulation results.

**Independent Test**: Can be fully tested by attempting to run a simulation without uploading a census file and verifying that a clear, actionable error appears before the simulation starts.

**Acceptance Scenarios**:

1. **Given** a scenario with no census file uploaded, **When** the user attempts to launch a simulation, **Then** the system displays an error: "census_parquet_path is required but was not found in the scenario config. Ensure a census file has been uploaded to the scenario folder before running."
2. **Given** the user sees the error message, **When** they follow the guidance to upload a census file, **Then** they can successfully launch the simulation.

---

### User Story 3 - Invalid Census File Path Handling (Priority: P2)

The system resolves the configured census file path and validates that the file exists at that location. If the path is invalid or the file has been deleted, the system rejects the run with a clear error message rather than attempting to use a fallback path.

**Why this priority**: Ensures robustness beyond the initial upload scenario. Covers cases where a census file may have been moved, deleted, or the path becomes invalid after initial setup. Prevents silent fallback behavior.

**Independent Test**: Can be fully tested by configuring a census path that does not exist (or deleting a previously uploaded file) and verifying that a clear error is returned before simulation execution.

**Acceptance Scenarios**:

1. **Given** a scenario config with a `census_parquet_path` pointing to a non-existent file, **When** the user launches a simulation, **Then** the system displays an error: "Census file not found at '[path]'. Upload a valid census parquet file to the scenario folder and retry."
2. **Given** the user receives the file-not-found error, **When** they upload a valid census file to the correct location, **Then** the simulation can proceed.

---

### Edge Cases

- What happens if `census_parquet_path` is an empty string or whitespace-only value?
- How does the system handle census files that are corrupted or not valid parquet format?
- What if the scenario folder itself does not exist when trying to resolve the census path?
- What if the user has read permissions for the scenario folder but not for the census file?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST reject simulation execution if `census_parquet_path` is absent from the merged scenario config.
- **FR-002**: System MUST raise a `ConfigurationError` with message "census_parquet_path is required but was not found in the scenario config. Ensure a census file has been uploaded to the scenario folder before running." when `census_parquet_path` is missing.
- **FR-003**: System MUST validate that the resolved census file path exists on the filesystem before simulation execution.
- **FR-004**: System MUST raise a `ConfigurationError` with message "Census file not found at '[path]'. Upload a valid census parquet file to the scenario folder and retry." when the census file path does not exist.
- **FR-005**: System MUST NOT attempt to use a fallback or default census path—validation must be hard-fail only.
- **FR-006**: System MUST surface configuration validation errors in the Studio UI as pre-run validation failures, preventing simulation execution.
- **FR-007**: System MUST log the validation error with sufficient context (scenario ID, expected path, timestamp) for debugging and audit trails.

### Key Entities *(include if feature involves data)*

- **Scenario Config**: The merged configuration dictionary passed from Studio that may or may not contain `census_parquet_path`.
- **Census File**: A parquet file containing workforce population/census data required for baseline and simulation calculations.
- **Configuration Error**: A raised exception containing user-friendly and actionable error messages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Simulations without a valid census file fail immediately (before any data processing) with a clear error message, eliminating silent data corruption.
- **SC-002**: Users receive clear, actionable guidance on how to resolve missing census files within 1 second of attempting to run an invalid scenario.
- **SC-003**: 100% of pre-run census path validation errors are surfaced in the Studio UI (no warnings hidden in logs).
- **SC-004**: Zero instances of simulations running with default/fallback census data after this feature is deployed.
- **SC-005**: Audit logs capture all census path validation failures with scenario context for post-incident analysis.

## Assumptions

- **Assumption 1**: The `census_parquet_path` is always resolved to an absolute filesystem path before validation.
- **Assumption 2**: The scenario folder is always accessible from the simulation service (no cross-network or permission issues preventing basic path validation).
- **Assumption 3**: Census file format validation (e.g., checking it is valid parquet) is out of scope; only existence validation is required.
- **Assumption 4**: The merged scenario config is the single source of truth for census file location; no environment variable fallbacks exist.
- **Assumption 5**: Studio always constructs the merged config before calling the orchestrator; no null/missing config scenarios occur at this layer.

## Out of Scope

- Automated census file upload detection or import from external sources.
- Schema validation of the census parquet file.
- Handling of census files stored in remote/cloud locations (assumes local filesystem).
- Migration of existing simulations that may have relied on the default fallback path.
