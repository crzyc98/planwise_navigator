# Feature Specification: Data Import with Field Mapping

**Feature Branch**: `087-data-import`
**Created**: 2026-05-30
**Status**: Draft
**Input**: User description: "i would like to build a process where you could upload a csv or excel file and it would have a way to map the input to the needed output and then it would create the parquet file for the analyst and store it in the workspace"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload and Map CSV/Excel Data (Priority: P1)

As an analyst, I want to upload a CSV or Excel file and define how its columns map to a target schema, so that I can prepare data for analysis in a standardized format.

**Why this priority**: This is the core workflow - without the ability to upload and define field mappings, the entire feature is non-functional. This is the MVP foundation.

**Independent Test**: An analyst can upload a CSV file, configure field mappings for at least 80% of columns, and complete the mapping UI without errors. Delivers value by enabling data preparation workflow.

**Acceptance Scenarios**:

1. **Given** an analyst is in a workspace, **When** they select "Import Data", **Then** they see an upload interface that accepts CSV and Excel files
2. **Given** a file is uploaded, **When** the system processes it, **Then** it displays a preview of the first 100 rows with column headers detected
3. **Given** the preview is displayed, **When** the analyst views the field mapping interface, **Then** they can see all input columns and can configure target field names, data types, and transformation rules
4. **Given** required mappings are incomplete, **When** the analyst attempts to generate output, **Then** the system shows clear validation errors indicating which fields are required
5. **Given** mappings are valid, **When** the analyst saves the mapping, **Then** the mapping is persisted in the workspace for future use

---

### User Story 2 - Generate Parquet Output (Priority: P1)

As an analyst, I want to convert the mapped CSV/Excel data into a parquet file, so that I can efficiently store and analyze large datasets.

**Why this priority**: Parquet generation is the core deliverable. Without it, the import process is incomplete. P1 because analysts need this output format for downstream analysis.

**Independent Test**: The system can generate a valid parquet file from a mapped CSV/Excel upload and store it in the workspace. File is readable by standard parquet tools.

**Acceptance Scenarios**:

1. **Given** field mappings are configured, **When** the analyst clicks "Generate Parquet", **Then** the system processes the data and creates a parquet file
2. **Given** a parquet file is being generated, **When** the analyst is waiting, **Then** the system shows a progress indicator and allows the analyst to monitor generation status until completion or failure
3. **Given** generation completes successfully, **When** the analyst views the workspace, **Then** the parquet file appears in the data files list with file metadata (size, row count, created date)
4. **Given** an error occurs during generation (data type mismatch, corrupted input), **When** generation fails, **Then** the analyst receives a clear error message indicating the specific issue and row numbers affected

---

### User Story 3 - Store and Manage Imported Data (Priority: P2)

As a workspace manager, I want imported parquet files to be stored securely in the workspace with clear versioning and access controls, so that team members can access prepared datasets.

**Why this priority**: File storage and management are important for collaboration but secondary to the core import functionality. P2 allows for MVP release with basic storage.

**Independent Test**: A parquet file generated from an import is persisted in workspace storage, accessible by workspace members, and listed in the workspace data files interface.

**Acceptance Scenarios**:

1. **Given** a parquet file is generated, **When** generation completes, **Then** the file is automatically stored in a workspace data directory with a unique name based on timestamp and original filename
2. **Given** multiple analysts import the same source data, **When** they generate parquet files, **Then** the system preserves both versions with distinct names and timestamps
3. **Given** a workspace member views the data files section, **When** they see imported parquet files, **Then** they can see metadata including original filename, import date, row count, and file size
4. **Given** an analyst no longer needs imported data, **When** they delete a parquet file, **Then** the file is removed from workspace storage and no longer appears in the data files list

---

### User Story 4 - Preview Mapped Data Before Generation (Priority: P2)

As an analyst, I want to see a preview of how my data will look after mapping is applied, before generating the parquet file, so that I can validate mappings are correct.

**Why this priority**: Preview functionality improves accuracy and reduces rework, but the feature is viable without it for MVP. P2 can be added after core import/generate works.

**Independent Test**: After configuring mappings, analyst can view a preview of transformed data (first 100 rows) showing mapped column names and data types before committing to parquet generation.

**Acceptance Scenarios**:

1. **Given** field mappings are configured, **When** the analyst clicks "Preview", **Then** the system displays a sample of the mapped data with transformed column names and types
2. **Given** preview is displayed, **When** the analyst identifies a mapping error, **Then** they can edit the mapping directly and preview updates without re-uploading the file
3. **Given** preview shows more than 100 rows of data, **When** analyst scrolls through preview, **Then** the preview renders all 100 rows without browser freeze and the analyst can reach the last row without reloading the page

---

### User Story 5 - Save and Reuse Mapping Templates (Priority: P3)

As an analyst, I want to save my field mappings as reusable templates, so that I can quickly map similar data sources without recreating mappings each time.

**Why this priority**: Template reuse improves efficiency for analysts who regularly work with similar data sources. P3 because it's an optimization rather than a core requirement.

**Independent Test**: An analyst can save a configured mapping as a template, then apply that template to a new CSV upload with minimal additional configuration.

**Acceptance Scenarios**:

1. **Given** field mappings are configured, **When** the analyst saves mappings, **Then** they can optionally save as a reusable template with a descriptive name
2. **Given** a template is saved, **When** the analyst uploads a new file with the same structure, **Then** they can select the template to auto-populate field mappings
3. **Given** templates are available, **When** workspace members view the mapping interface, **Then** they can see a list of available templates in their workspace

---

### Edge Cases

- What happens when the uploaded CSV file is empty (0 rows)? → System shows error and prompts for a valid file with at least 1 data row
- What happens when an Excel file contains multiple sheets? → System displays a sheet selector UI; analyst chooses which sheet to import
- How does the system handle very large files (>1GB)? → System enforces file size limits and shows clear error message indicating maximum allowed size
- What happens when field values contain special characters or encoding issues? → System attempts UTF-8 decoding and shows warnings for problematic rows; analyst can choose to skip or transform rows
- How does system handle duplicate column names in input file? → System appends numeric suffixes (e.g., "Amount", "Amount_1") to distinguish columns and allows analyst to rename in mapping UI
- What happens if analyst closes the mapping UI without saving mappings? → System prompts to confirm; unsaved mappings are discarded; uploaded file is retained for next import attempt

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to upload CSV and Excel (XLSX) files through the web interface
- **FR-002**: System MUST automatically detect column headers and display a preview of uploaded file data (first 100 rows)
- **FR-003**: System MUST provide an interactive field mapping interface where analysts can define target field names, data types, and optional transformations for each input column
- **FR-004**: System MUST validate that all required output fields have corresponding input field mappings before allowing parquet generation
- **FR-005**: System MUST generate a valid Apache Parquet file from the mapped CSV/Excel data with schema matching the configured mappings
- **FR-006**: System MUST store generated parquet files in workspace storage with automatic organization by workspace and timestamp-based unique naming
- **FR-007**: System MUST display uploaded parquet files in the workspace data files list with metadata including filename, import date, row count, and file size
- **FR-008**: System MUST allow workspace members to view and download imported parquet files; file deletion is restricted to workspace managers only
- **FR-009**: System MUST provide data type support for at least: string, integer, decimal, date, boolean, and timestamp during field mapping
- **FR-010**: System MUST handle and report errors during parquet generation with specific error messages indicating data type mismatches, invalid values, or file corruption
- **FR-011**: System MUST persist field mappings temporarily during an import session, allowing analysts to edit mappings and preview data without re-uploading the file
- **FR-012**: System MUST support mapping transformations including: column renames, type conversions, string case transformations (uppercase, lowercase, title case), date format parsing, null value handling (replace with defaults or skip rows), and calculated fields limited to column references and arithmetic operators (`+`, `-`, `*`, `/`, string concatenation); Python built-ins, imports, and arbitrary code execution MUST be rejected
- **FR-013**: System MUST enforce a maximum file size limit of 500MB for uploads to prevent resource exhaustion
- **FR-014**: System MUST log all data imports including: file name, number of rows processed, mapping configuration, user who initiated import, and timestamp

### Key Entities

- **ImportSession**: Represents a single import session with metadata (import_id, workspace_id, uploaded_filename, row_count, status, created_at, created_by)
- **FieldMapping**: Defines transformation rules from input columns to output columns (import_id, input_column_name, output_column_name, data_type, transformation_rules, is_required)
- **ParquetFile**: Represents generated parquet output (file_id, workspace_id, original_filename, parquet_filename, storage_path, row_count, file_size_bytes, created_at, created_by)
- **MappingTemplate**: Reusable mapping configuration (template_id, workspace_id, template_name, field_mappings, created_at, created_by)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Analysts can complete a full import workflow (upload → map → generate parquet) in under 5 minutes for typical datasets (< 100K rows)
- **SC-002**: System successfully processes and generates parquet files for CSV/Excel uploads up to 500MB without data loss or corruption
- **SC-003**: 95% of attempted imports result in valid parquet files without requiring manual intervention or error recovery
- **SC-004**: Parquet files generated through the import interface are readable by standard analytics tools (Pandas, DuckDB, Spark) without format issues
- **SC-005**: Analysts report that the mapping interface clearly communicates validation errors and prevents invalid configurations from being saved
- **SC-006**: System supports at least 100 concurrent import operations without performance degradation on workspace servers
- **SC-007**: Workspace members can locate and access imported parquet files within the workspace with clear file organization and metadata visibility
- **SC-008**: Data imports are fully auditable - all import operations logged with user, timestamp, and mapping configuration for compliance

## Assumptions

- Analysts have existing workspaces where they want to store imported data
- File uploads will occur through the web interface (planalign_studio) rather than CLI
- Workspace storage infrastructure exists and can accommodate parquet files up to several GB per workspace
- Users have basic familiarity with CSV/Excel format and understand data mapping concepts
- Output schema for parquet files is flexible and defined per-import (not a fixed schema enforced globally)
- File encoding is primarily UTF-8; other encodings may require analyst intervention
- Parquet files are immutable after generation (no in-place updates; new imports create new files)
