# Feature Specification: Census File Error Handling — Clear Messages and Early Detection

**Feature Branch**: `091-census-file-errors`
**Created**: 2026-06-05
**Status**: Draft
**Input**: User description: "Please implement the three Quick Wins from our error analysis plan to improve parquet file error handling in Fidelity PlanAlign."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Corrupted Census File Is Caught Before Simulation Starts (Priority: P1)

A workspace admin uploads a census file that is structurally intact on disk but internally corrupted (unreadable data). They then launch a simulation. Today the system silently accepts the file, starts the simulation, and returns a cryptic "Unknown error (code 1)" 60+ seconds later. With this fix, the system performs a lightweight readability check immediately when simulation is requested and stops immediately with a clear, actionable message before wasting simulation time.

**Why this priority**: This is the most disruptive failure path — users wait for a long simulation to fail and receive no guidance on what went wrong or how to fix it. Early detection eliminates the wait and provides immediate remediation direction.

**Independent Test**: Configure a scenario with a truncated or malformed census file. Trigger a simulation. Confirm that within 5 seconds the simulation is rejected with a message naming the census file as the problem and instructing the user to re-upload.

**Acceptance Scenarios**:

1. **Given** a scenario with a corrupted (unreadable) census file configured, **When** a user triggers simulation, **Then** the simulation is rejected immediately with a message identifying the census file as the cause and instructing the user to re-upload it.
2. **Given** a scenario with a census file missing required columns, **When** a user triggers simulation, **Then** the simulation is rejected with a message noting the schema mismatch and instructing the user to re-upload a corrected file.
3. **Given** a scenario with a valid census file, **When** a user triggers simulation, **Then** the pre-flight check passes silently and simulation proceeds normally without delay.
4. **Given** a scenario with a census file that has zero data rows, **When** a user triggers simulation, **Then** the simulation is rejected with a message indicating the file is empty.

---

### User Story 2 — Census File Errors During Simulation Return Specific Messages (Priority: P1)

If a census file passes the pre-flight readability check but still causes a failure during simulation processing (e.g., a type mismatch detected at a deeper processing stage), the user sees a specific, actionable message rather than a generic internal error code.

**Why this priority**: Even with a pre-flight check, edge cases exist where a file passes the quick read test but fails during deeper processing. The generic "Unknown error (code 1)" message provides no diagnostic value and leaves users with no path to resolution.

**Independent Test**: Force a simulation failure with output containing census/parquet-related error text. Confirm the returned error message describes the census file as the source — not "Unknown error (code 1)".

**Acceptance Scenarios**:

1. **Given** a simulation that fails with census/parquet-related error output from the processing layer, **When** the error is surfaced, **Then** the error message identifies the census file as the source and suggests re-uploading.
2. **Given** a simulation that fails due to a non-census cause (e.g., a configuration error), **When** the error is surfaced, **Then** the census-specific message is NOT shown; the correct category of error is shown instead.
3. **Given** a simulation that fails with a completely unrelated unknown error, **When** the error is surfaced, **Then** the generic fallback message appears and does not incorrectly attribute blame to the census file.

---

### User Story 3 — UI Displays Actionable Error With Remediation Steps (Priority: P2)

When a simulation fails due to a census file problem (either caught pre-flight or during processing), the PlanAlign Studio UI presents a user-readable message with clear remediation steps — not a raw stack trace, internal path, or error code.

**Why this priority**: Error messages that reach the UI must be consumable by non-technical users. A message like "Re-upload your census file" tells the user what to do next. A raw stack trace does not.

**Independent Test**: Trigger a census file error from the UI. Confirm the error panel shows a plain-language description and at least one actionable suggestion that points to the Import workflow.

**Acceptance Scenarios**:

1. **Given** a simulation fails due to a census file issue, **When** the UI renders the error, **Then** the user sees a plain-language description (e.g., "Census file cannot be read") and at least one remediation suggestion (e.g., "Re-upload your census file via the Import tab").
2. **Given** any simulation failure, **When** the error is displayed, **Then** no raw stack trace, internal file path, or bare error code is shown as the primary message.
3. **Given** a census file error with a remediation suggestion, **When** the user follows the suggestion and re-uploads a valid file, **Then** the simulation succeeds on the next attempt.

---

### Edge Cases

- What happens when the census file exists and is readable, but contains zero data rows? The pre-flight check should reject the simulation with an "empty census file" message rather than proceeding with zero employees.
- What happens when the census file has valid structure but wrong column names? The pre-flight check should detect the schema mismatch and surface a specific message, not a generic parquet error.
- What happens when the census file passes the pre-flight check but fails during deeper processing? The processing-layer error classifier should still return a census-specific message if the error output references the census file.
- What happens when the census file is large (many rows) and the pre-flight read times out? The check must complete within a fixed time limit; if it cannot, the simulation proceeds rather than hanging indefinitely.
- What happens when there is no census file path configured at all? This case is already handled; it must remain handled and not regress.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST perform a census file readability validation immediately before beginning simulation processing — verifying not only that the file path is configured and the file exists on disk, but also that the file can be opened and at least partially read without errors.
- **FR-002**: The readability validation MUST complete within a fixed short time limit; if the read operation cannot complete in time, the system MUST allow simulation to proceed rather than block indefinitely.
- **FR-003**: When the census file fails readability validation, the system MUST reject the simulation request immediately with an error that: (a) names the census file as the cause, (b) provides a one-sentence remediation instruction, and (c) does not expose internal paths, stack traces, or numeric error codes as the primary message.
- **FR-004**: The readability validation MUST also check that the census file contains at least one data row and MUST reject simulation with an "empty file" message if it does not.
- **FR-005**: The readability validation MUST check that the census file contains the required workforce columns and MUST reject simulation with a schema mismatch message if required columns are absent.
- **FR-006**: When the simulation processing layer reports an error whose output indicates a parquet or census file problem, the system MUST classify that error as a census file failure and return a user-friendly message identifying the census file — not a generic fallback error code.
- **FR-007**: Census file errors MUST be distinguishable from all other simulation error types — a general configuration error, a data quality test failure, and a census file error must each produce distinct, non-overlapping messages.
- **FR-008**: When a census file error is surfaced to the UI, the error response MUST include at least one actionable remediation suggestion pointing the user toward the Import workflow.
- **FR-009**: If a simulation fails for a reason unrelated to the census file, the system MUST NOT incorrectly attribute that failure to the census file.

### Key Entities

- **Census File**: The employee dataset file attached to a simulation scenario. May be valid, missing, corrupted, schema-mismatched, or empty.
- **Simulation Request**: A user-initiated request to run a simulation. Includes a pre-flight validation phase that runs before any processing begins.
- **Error Response**: The structured failure object returned to the caller. Contains a user-readable message, an error category, and zero or more actionable remediation suggestions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulations with a corrupted or unreadable census file are rejected within 5 seconds with a message explicitly referencing the census file — before any simulation processing begins.
- **SC-002**: 0% of census file failures return "Unknown error" or a bare error code as the primary user-facing message after this feature ships.
- **SC-003**: The UI error panel for census file failures includes at least one actionable remediation suggestion on 100% of occurrences.
- **SC-004**: Non-census simulation errors (configuration errors, data quality failures, unknown errors) are unaffected — their messages do not change and do not incorrectly reference census files.
- **SC-005**: A user who receives a census file error and follows the remediation suggestion (re-uploading a valid file) can complete simulation on the next attempt without contacting support.

## Assumptions

- The three improvements (pre-flight check, better error classification, structured UI error) are scoped to census parquet file failures only — other parquet usage in the system is out of scope.
- The pre-flight check reads a small sample of the file to verify readability; it does not perform a full scan, keeping latency well within the 5-second limit for typical file sizes.
- The remediation suggestion points users to the existing Import workflow in PlanAlign Studio; no new UI screens or import flows need to be built as part of this feature.
- "Corrupted parquet file" means any state where the file cannot be opened for reading, is truncated, or fails structural parsing — not application-level data value validation.
- Schema mismatch detection checks for the presence of required columns by name; data type coercion issues at the column level are out of scope for the pre-flight check.
- The existing path-not-configured and file-not-found checks remain in place and are not replaced by this feature.
