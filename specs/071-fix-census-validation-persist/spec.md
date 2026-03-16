# Feature Specification: Fix Census Validation Warning Persistence on Re-Upload

**Feature Branch**: `071-fix-census-validation-persist`
**Created**: 2026-03-16
**Status**: Draft
**GitHub Issue**: [#226](https://github.com/crzyc98/planwise_navigator/issues/226)
**Input**: Bug — When uploading a census file that triggers a validation warning, then re-uploading a corrected file, the original warning remains displayed. The validation should re-run on each new upload.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Re-Upload Corrected Census Clears Previous Warnings (Priority: P1)

A plan administrator uploads a census CSV that contains data issues (e.g., missing recommended columns or invalid values). The system displays validation warnings. The administrator corrects the CSV and re-uploads it. Upon re-upload, all previous warnings disappear and only warnings from the new file (if any) are shown.

**Why this priority**: This is the core bug. Without this fix, users cannot confirm whether their corrections resolved the issues, leading to confusion and mistrust of the validation system.

**Independent Test**: Upload a CSV with a known issue (e.g., missing `hire_date` column), observe the warning, then upload a corrected CSV with `hire_date` present. The warning must disappear.

**Acceptance Scenarios**:

1. **Given** a census file was uploaded that produced a "missing column" warning, **When** the user uploads a corrected file with the missing column added, **Then** the previous warning is no longer displayed and only warnings for the new file appear.
2. **Given** a census file was uploaded that produced data quality warnings (e.g., negative compensation values), **When** the user uploads a corrected file with valid values, **Then** the data quality warnings from the first upload are cleared.
3. **Given** a census file was uploaded with no warnings, **When** the user uploads a second file that has issues, **Then** only warnings from the second file appear.

---

### User Story 2 - Re-Upload Same Filename Triggers Fresh Validation (Priority: P1)

A plan administrator fixes a census CSV on disk (same filename) and re-uploads it. The system must treat this as a new upload, re-run validation, and display fresh results — even though the filename hasn't changed.

**Why this priority**: This is the most common re-upload pattern. Users fix a file and re-select it from the same path. If the system ignores the re-selection because the filename matches, the bug persists silently.

**Independent Test**: Upload `census.csv` with an issue, fix the file locally, re-select `census.csv` via the file picker. Confirm the onChange handler fires and validation re-runs.

**Acceptance Scenarios**:

1. **Given** a file named `census.csv` was previously uploaded, **When** the user selects a file named `census.csv` again (corrected version), **Then** the system processes the new file and refreshes all warnings.
2. **Given** the user is on the upload screen with stale warnings displayed, **When** the user selects the same filename via drag-and-drop, **Then** validation re-runs and warnings update.

---

### User Story 3 - Warnings Clear Immediately on Upload Start (Priority: P2)

When the user initiates a new upload, previous warnings should clear immediately (before the upload completes) so the user sees a clean "uploading..." state rather than stale warnings alongside a progress indicator.

**Why this priority**: This improves perceived responsiveness and prevents confusion about which warnings correspond to which file.

**Independent Test**: Upload a file with warnings, then start uploading a second file. During the upload (before response), verify the warning area is empty.

**Acceptance Scenarios**:

1. **Given** warnings from a previous upload are displayed, **When** the user selects a new file and upload begins, **Then** all previous warnings are cleared before the upload response arrives.
2. **Given** a large file is being uploaded (takes several seconds), **When** the upload is in progress, **Then** only the upload progress indicator is shown — no stale warnings are visible.

---

### Edge Cases

- What happens when the user selects a file but the upload fails (network error)? Previous warnings should still be cleared; an error message should display instead.
- What happens when the user cancels the file picker dialog without selecting a file? The existing warnings should remain unchanged (no action was taken).
- What happens when the user rapidly uploads multiple files in succession? Only the most recent upload's warnings should be displayed.
- What happens when the user navigates away from the upload section and returns? The warning state should reflect the most recent upload result (or be empty if no upload has occurred in the current session).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST clear all previous validation warnings (both structured warnings and data quality warnings) when a new census file upload begins.
- **FR-002**: System MUST re-run the full validation pipeline on each newly uploaded file, regardless of whether the filename matches a previously uploaded file.
- **FR-003**: System MUST display only warnings generated from the most recently uploaded file after the upload completes.
- **FR-004**: System MUST allow re-selection of the same filename in the file picker (the file input must not suppress duplicate filenames).
- **FR-005**: System MUST clear expanded/collapsed state of warning detail sections when warnings are refreshed.
- **FR-006**: System MUST clear previous warnings even if the new upload fails, replacing them with the appropriate error message.

### Key Entities

- **Structured Warning**: A field-level validation finding (e.g., missing column, alias found, auto-mapped column) with severity tier (critical, optional, info) and suggested action.
- **Data Quality Warning**: A row-level validation finding (e.g., null values, unparseable dates, negative compensation) with affected row count, percentage, and sample data.
- **Upload State**: The transient state of the census upload flow including status (idle, uploading, success, error), message, and the current set of warnings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of re-uploads result in a fresh set of warnings that reflect only the newly uploaded file — no stale warnings from prior uploads are shown.
- **SC-002**: Re-uploading a corrected file that resolves all issues results in zero warnings displayed.
- **SC-003**: Re-selecting the same filename triggers a new validation pass 100% of the time.
- **SC-004**: Previous warnings are visually cleared within 200ms of the user initiating a new upload (before the upload response arrives).

## Assumptions

- The backend already correctly regenerates validation results on each upload (confirmed by existing tests). The bug is isolated to the frontend warning state management.
- The fix scope is limited to the census upload UI component; no backend API changes are expected.
- The file input element's behavior of not firing `onChange` for the same filename is a known browser behavior that must be explicitly handled.
