# Feature Specification: Fix Import File 422 — Data Type "str" Not Recognized

**Feature Branch**: `090-fix-import-str-type`
**Created**: 2026-06-05
**Status**: Draft
**Input**: User description: "when i'm testing the import file, i'm getting http 422 deteail not implemented error data type str not recognized"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Upload a Census File Without Errors (Priority: P1)

A workspace admin uploads a CSV or Excel census file through PlanAlign Studio. After uploading, they should be taken to the field-mapping step with the file's columns and a sample of rows shown. No errors should occur during upload.

**Why this priority**: Uploading a file is the entry point for the entire import workflow. If upload fails, no downstream steps (mapping, validation, parquet generation) are possible.

**Independent Test**: Upload any valid census CSV and confirm the file is accepted and the mapping UI opens with detected columns.

**Acceptance Scenarios**:

1. **Given** a valid CSV file with all-text columns, **When** the user uploads it, **Then** the system accepts the file and returns the detected column list with no error.
2. **Given** a valid CSV file with mixed column types (dates, numbers, text), **When** the user uploads it, **Then** the system accepts the file without returning a 422 error.
3. **Given** an Excel (.xlsx) file, **When** the user uploads it, **Then** the system converts it and shows detected columns with no error.

---

### User Story 2 — Generate Parquet from Mapped Census Data (Priority: P1)

After mapping source columns to canonical census fields, the admin triggers parquet generation. The system converts the transformed data and returns a downloadable parquet file.

**Why this priority**: Parquet generation is the final, blocking step of the import workflow. If it fails with a 422, the imported data cannot be used in any simulation.

**Independent Test**: Complete an upload + mapping for any CSV, click "Generate", and confirm a parquet file is produced and listed in the workspace.

**Acceptance Scenarios**:

1. **Given** a saved column mapping, **When** the user triggers parquet generation, **Then** the system produces a parquet file without returning a 422 "data type str not recognized" error.
2. **Given** mapped columns that include string, date, and decimal fields, **When** parquet generation runs, **Then** all columns are correctly typed in the output file.
3. **Given** columns that contain only text values (no numeric parsing possible), **When** parquet generation runs, **Then** those columns are preserved as text in the parquet output.

---

### User Story 3 — Informative Error Messages for Unsupported Files (Priority: P2)

If the import file genuinely cannot be converted (e.g., corrupt data, unsupported structure), the user receives a clear, actionable error message — not an internal "not implemented" stack trace.

**Why this priority**: Users should never see raw internal errors. A clear message lets them fix the file themselves without needing support.

**Independent Test**: Upload a file with a known problem and confirm the error message describes the problem in plain language.

**Acceptance Scenarios**:

1. **Given** a file that causes a conversion error, **When** the user uploads or generates parquet, **Then** the error message describes what is wrong (e.g., "Column X could not be parsed as a date") rather than exposing an internal exception.

---

### Edge Cases

- What happens when a CSV column contains only null/empty values? The system should treat it as a text column and proceed rather than failing.
- What happens when every value in a column is a numeric string (e.g., `"123"`)? The system should infer the most appropriate type rather than throwing an error.
- What happens when a column name contains special characters or spaces? Column names should be sanitized rather than causing downstream failures.
- What happens when the file has hundreds of columns? The system should handle large schemas without timeout or memory errors.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST successfully convert and store any valid CSV or XLSX file containing text-typed columns (i.e., Python `str` / pandas `object` dtype) to parquet format without returning a 422 error.
- **FR-002**: The system MUST coerce pandas `object`-dtype columns to a recognized storage type (e.g., text/string) before writing to parquet, so no "data type str not recognized" error occurs.
- **FR-003**: The system MUST preserve column data integrity during the dtype coercion — values must not be truncated, reordered, or silently dropped.
- **FR-004**: The system MUST handle the parquet generation step the same way: any transformed column with text values must be written without error regardless of its source dtype.
- **FR-005**: When an unrecoverable conversion error does occur, the system MUST return a user-readable error message that identifies the problematic column and describes the issue, without exposing internal exception details.
- **FR-006**: The system MUST continue to correctly infer and preserve numeric (decimal/integer), date, and boolean column types where those types are unambiguous.

### Key Entities

- **ImportSession**: Tracks upload state, detected columns, and mapping status for a single file upload.
- **FieldMapping**: Maps a source column name to a canonical census field name with an explicit output type.
- **ParquetFile**: The final output artifact — a typed, immutable Parquet file stored in the workspace.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Uploading any well-formed CSV or XLSX census file returns HTTP 201 (not 422) 100% of the time, regardless of whether columns contain text, numbers, or dates.
- **SC-002**: Parquet generation completes successfully for any import session where a valid mapping has been saved — zero "data type str not recognized" errors in the test suite.
- **SC-003**: The end-to-end import workflow (upload → map → generate) completes without error for at least 5 representative census file formats tested in QA.
- **SC-004**: When a genuine data error occurs, the error message shown to the user identifies the specific column and problem (not an internal Python traceback).

## Assumptions

- The root cause is that pandas `object`-dtype (Python `str`) columns are passed directly to DuckDB's DataFrame registration without explicit type casting, and DuckDB 1.0.0 rejects the raw Python `str` type annotation in certain code paths.
- The fix involves normalizing column dtypes to a DuckDB-compatible representation (e.g., casting `object` columns to `pd.StringDtype()` or explicitly mapping to `VARCHAR`) before any DuckDB `register()` + `COPY TO PARQUET` call.
- No changes to the data model, Pydantic schemas, or existing API contracts are required — this is an internal data-handling fix only.
