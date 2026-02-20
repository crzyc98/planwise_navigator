# Feature Specification: Census Field Validation Warnings

**Feature Branch**: `055-census-field-warnings`
**Created**: 2026-02-20
**Status**: Draft
**Input**: User description: "When a user uploads a census file that is missing expected fields, they should see a clear, prominent warning explaining which fields are missing and what impact that will have on the simulation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Critical Field Missing Warning (Priority: P1)

As an analyst uploading a census file, I want to see a clear, prominent warning when critical fields are missing so that I understand my simulation results will be unreliable before I proceed.

**Why this priority**: Critical fields (hire date, compensation, birth date) directly affect the accuracy of core simulation outputs. Without them, the simulation produces misleading results that could lead to incorrect business decisions. Users must be clearly warned before proceeding.

**Independent Test**: Can be fully tested by uploading a census file missing `employee_birth_date` and verifying that a prominent amber/red warning appears listing the missing field and its downstream impact on age-based calculations and HCE determination.

**Acceptance Scenarios**:

1. **Given** a census file missing `employee_birth_date`, **When** the file is uploaded successfully, **Then** a prominent warning panel appears listing "employee_birth_date" as missing with an explanation that age-based calculations, age band segmentation, and HCE determination will not work correctly.
2. **Given** a census file missing `employee_gross_compensation`, **When** the file is uploaded successfully, **Then** a prominent warning panel appears explaining that compensation-based calculations, merit raises, promotion modeling, and contribution calculations will use defaults or fail.
3. **Given** a census file missing `employee_hire_date`, **When** the file is uploaded successfully, **Then** a prominent warning panel appears explaining that tenure calculations, new hire identification, and turnover modeling will not work correctly.
4. **Given** a census file missing multiple critical fields, **When** the file is uploaded successfully, **Then** all missing critical fields are listed together in a single warning panel with each field's impact clearly described.

---

### User Story 2 - Optional Field Missing Info (Priority: P2)

As an analyst, I want to see a less urgent informational notice when optional fields are missing so that I know which defaults the simulation will apply without being alarmed.

**Why this priority**: Optional fields have sensible defaults. Users should know about them for transparency, but missing optional fields should not block or discourage simulation use.

**Independent Test**: Can be fully tested by uploading a census file that has all critical fields but is missing optional fields like `employee_deferral_rate`, and verifying an informational notice (not a warning) appears explaining that defaults will be used.

**Acceptance Scenarios**:

1. **Given** a census file with all critical fields but missing `employee_deferral_rate`, **When** the file is uploaded successfully, **Then** an informational notice (visually distinct from critical warnings) appears explaining that the simulation will use default deferral rates.
2. **Given** a census file with all critical and optional fields present, **When** the file is uploaded successfully, **Then** no warning or notice about missing fields is shown — only the success confirmation.

---

### User Story 3 - Column Alias Detection (Priority: P3)

As an analyst whose census file uses non-standard column names, I want to see helpful suggestions when my columns appear to be aliases of expected columns so that I can rename them for compatibility.

**Why this priority**: Many census exports use slightly different column names (e.g., `hire_date` instead of `employee_hire_date`). Detecting aliases reduces user frustration and prevents unnecessary re-uploads.

**Independent Test**: Can be fully tested by uploading a census file with a column named `hire_date` (instead of `employee_hire_date`) and verifying a notice suggests renaming it.

**Acceptance Scenarios**:

1. **Given** a census file with a column `hire_date` but no `employee_hire_date`, **When** the file is uploaded, **Then** a notice appears suggesting the user rename `hire_date` to `employee_hire_date` for full compatibility.
2. **Given** a census file with `annual_salary` but no `employee_gross_compensation`, **When** the file is uploaded, **Then** a notice appears suggesting the rename to `employee_gross_compensation`.

---

### Edge Cases

- What happens when a census file contains only `employee_id` and no other columns? All critical fields should be listed as missing with their impacts.
- What happens when the backend returns warnings but the upload itself failed for another reason (e.g., file too large)? The error takes precedence; field warnings are not shown.
- What happens when a column alias is detected AND the target column is also missing? The alias suggestion should take priority over the generic "missing" warning for that field.
- What happens when the user dismisses the warning and later re-uploads a corrected file? Previous warnings should be cleared and replaced with new validation results.
- What happens when warnings appear alongside a successful upload count (e.g., "500 rows loaded")? Both should be visible — warnings should not replace the success information.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST categorize missing census columns into two tiers: "critical" (fields that cause unreliable simulation results) and "optional" (fields where sensible defaults exist).
- **FR-002**: System MUST display a prominent warning panel (visually distinct from success messages) when one or more critical fields are missing after a successful upload.
- **FR-003**: System MUST display each missing critical field with a human-readable explanation of which simulation features are affected.
- **FR-004**: System MUST display a separate, lower-severity informational notice when optional fields are missing, explaining what defaults will be used.
- **FR-005**: System MUST continue to show upload success information (row count, column count) alongside any field warnings — warnings do not replace success feedback.
- **FR-006**: System MUST clear previous warnings when a new file is uploaded or validated.
- **FR-007**: System MUST include column alias suggestions when a known alternative column name is detected in the uploaded file.
- **FR-008**: Backend MUST return structured warning data that includes the field name, severity tier (critical/optional), and a human-readable impact description for each missing or aliased column.
- **FR-009**: The warning panel MUST be visible without scrolling after upload completes (it should appear in the upload result area, not hidden below the fold).
- **FR-010**: Critical field warnings MUST use a visually distinct style (e.g., amber or red background) that is clearly different from informational notices (e.g., blue or gray background).
- **FR-011**: Missing critical fields MUST NOT block or prevent simulation execution. Warnings are informational only — users may proceed to run simulations after seeing them.
- **FR-012**: The existing static "Required Census Columns" info box MUST be removed and replaced by the new dynamic warning system. Pre-upload, no column guidance is shown; post-upload/validate, the tiered warnings provide accurate, context-specific feedback.

### Key Entities

- **Field Severity Tier**: Classification of a census column as "critical" or "optional" based on its impact on simulation accuracy. Critical fields: `employee_hire_date`, `employee_gross_compensation`, `employee_birth_date`. Optional fields: `employee_termination_date`, `active`, `employee_deferral_rate`, and other supplementary columns.
- **Field Impact Description**: A mapping from each expected census column to a human-readable explanation of what simulation features depend on it.
- **Validation Warning**: A structured object containing the missing field name, its severity tier, its impact description, and optionally a detected alias suggestion.

## Clarifications

### Session 2026-02-20

- Q: Should the system prevent users from running a simulation when critical fields are missing, or only warn at upload time? → A: Warning-only at upload time; simulation runs normally. Users see the warning and choose whether to proceed. No simulation-blocking behavior.
- Q: Should the static "Required Census Columns" info box be kept, replaced, or updated alongside the new dynamic warnings? → A: Replace it with the new dynamic warning system. The static box lists inaccurate columns; the new tiered warnings provide accurate, context-specific guidance after upload/validate.

## Assumptions

- The existing backend validation logic in `file_service.py` already detects missing recommended columns and returns warnings. This feature enhances the warning payload structure and improves the frontend display.
- The current `RECOMMENDED_COLUMNS` list in `file_service.py` is the authoritative source for expected columns. The new "critical" tier is a subset of these recommended columns.
- The upload API response structure can be extended with additional warning metadata without breaking existing clients.
- The column alias mapping in `COLUMN_ALIASES` is the authoritative source for alias detection.
- The warning display area will reuse the existing upload status area in `DataSourcesSection.tsx` rather than introducing a separate modal or page. The static "Required Census Columns" info box will be removed as it is replaced by the dynamic warnings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of critical missing field warnings include a specific, human-readable impact description (not just the column name).
- **SC-002**: Users can identify all missing fields and their impacts within 5 seconds of upload completion without scrolling or clicking additional UI elements.
- **SC-003**: Critical and optional warnings are visually distinguishable — a user unfamiliar with the system can correctly categorize warning severity based on visual appearance alone.
- **SC-004**: Upload success information (row count, column count) remains visible when warnings are present — no information loss compared to a warning-free upload.
- **SC-005**: When a corrected file is re-uploaded, previous warnings are fully replaced by the new validation result within the same interaction.
