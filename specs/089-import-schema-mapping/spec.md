# Feature Specification: Schema-Aware Import with Predictive Field Mapping

**Feature Branch**: `089-import-schema-mapping`
**Created**: 2026-06-03
**Status**: Draft
**Input**: User description: "this import process isn't what i was hoping. why doesn't it try to map to the actual needs of the system? the columns in the parquet HAVE to be certain names and contents. also, wouldn't we want to be predictive on this and also help the analyst with the data formatting"

## Clarifications

### Session 2026-06-03

- Q: Should the import wizard deduplicate employee_id values before writing the parquet, or pass duplicates through? → A: Pass duplicates through; preview warns the analyst; `stg_census_data.sql` deduplicates as designed (most-recent hire date wins).
- Q: Does `employee_ssn` contain real Social Security Numbers requiring PII protection? → A: No — the field holds synthetic identifiers (e.g., "SSN-00000001") assigned by order; no real SSNs are in play, so no special masking or log exclusion is required.
- Q: Should 087 free-form mapping templates be migrated or preserved? → A: No migration and no free-form targets at all — mapping targets are always canonical fields; 087 templates are superseded and do not carry forward.
- Q: What thresholds define high / medium / low auto-suggestion confidence? → A: High ≥ 85% name-similarity score against canonical name + known aliases; Medium 50–84%; Low < 50%.

## Context

The existing data import feature (087) treats the output parquet schema as flexible and analyst-defined. This is incorrect — the simulation engine reads census parquet files through `stg_census_data.sql`, which expects a fixed canonical schema. Imported files with wrong column names will silently fail or produce empty simulation results.

This feature replaces the free-form field mapping with a **schema-driven mapping wizard** that knows what columns the system needs, auto-suggests mappings from uploaded data, and guides analysts on correct data formatting — without requiring them to read documentation.

### Canonical Census Schema

The simulation engine requires these column names in the output parquet:

| Column | Required | Type | Description |
|--------|----------|------|-------------|
| `employee_id` | **Yes** | string | Unique employee identifier |
| `employee_birth_date` | **Yes** | date | Date of birth |
| `employee_hire_date` | **Yes** | date | Original hire date |
| `employee_gross_compensation` | **Yes** | decimal | Annual salary rate (not prorated) |
| `active` | **Yes** | boolean | Currently employed flag |
| `employee_ssn` | No | string | Synthetic SSN-style identifier (e.g., "SSN-00000001") — not a real SSN; no PII handling required |
| `employee_termination_date` | No | date | Termination date (if separated) |
| `employee_capped_compensation` | No | decimal | IRS 401(a)(17) capped compensation |
| `employee_deferral_rate` | No | decimal | Current deferral rate (0.00–1.00) |
| `employee_contribution` | No | decimal | Total employee contribution amount |
| `pre_tax_contribution` | No | decimal | Pre-tax deferral amount |
| `roth_contribution` | No | decimal | Roth deferral amount |
| `after_tax_contribution` | No | decimal | After-tax contribution amount |
| `employer_core_contribution` | No | decimal | Employer non-elective contribution |
| `employer_match_contribution` | No | decimal | Employer matching contribution |
| `eligibility_entry_date` | No | date | Plan eligibility entry date override |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Auto-Mapped Census Upload (Priority: P1)

An analyst uploads a CSV or Excel file with non-standard column names (e.g., "EmpID", "DOB", "Salary", "Hire Date"). The system automatically suggests which input column maps to each required output column, shows confidence levels, and lets the analyst confirm or correct suggestions — all without requiring knowledge of the canonical schema.

**Why this priority**: This is the core UX improvement. Without it, analysts who don't know the canonical column names will produce unusable parquet files or spend significant time figuring out the mapping. Predictive mapping is the feature.

**Independent Test**: Upload a census CSV with recognizable but non-standard column names. The system must suggest correct mappings for all four required fields with high confidence (no manual intervention needed for >80% of columns in a typical census file).

**Acceptance Scenarios**:

1. **Given** an analyst uploads a CSV file, **When** the system detects columns, **Then** it automatically pre-populates the mapping UI with suggested target fields for each input column based on name similarity, data patterns, and common aliases
2. **Given** the mapping UI is shown, **When** the analyst reviews suggestions, **Then** each suggestion shows a confidence indicator (High ≥ 85% / Medium 50–84% / Low < 50% name-similarity score) and the matched canonical field name
3. **Given** the system suggests a mapping with low confidence, **When** the analyst reviews it, **Then** they can open a dropdown showing all canonical fields (required ones listed first) and select the correct target
4. **Given** all required fields are mapped, **When** the analyst clicks "Generate", **Then** the output parquet contains exactly the canonical column names the simulation engine expects
5. **Given** the analyst corrects a suggestion, **When** they change the target field, **Then** the confidence indicator updates to "User-confirmed" and the mapping is locked from further auto-update

---

### User Story 2 — Required Field Validation with Clear Guidance (Priority: P1)

The mapping wizard shows analysts which fields are required vs. optional, blocks generation if any required field is unmapped, and explains what each field is used for in plain language — so analysts understand why a field matters, not just that it is missing.

**Why this priority**: Without this, analysts can generate a parquet that the simulation engine silently ignores or errors on. Required-field validation is the safety net.

**Independent Test**: Upload a census file missing a compensation column. The mapping wizard must block generation and show a clear error identifying which required field is unmapped, with a plain-language description of what the field represents.

**Acceptance Scenarios**:

1. **Given** the mapping interface is loaded, **When** the analyst views target fields, **Then** required fields are visually distinguished from optional fields (e.g., asterisk, badge, or color)
2. **Given** a required field has no mapping, **When** the analyst attempts to generate parquet, **Then** the system blocks generation and highlights the unmapped required fields with a plain-language explanation of what each field is used for
3. **Given** an optional field has no mapping, **When** the analyst generates, **Then** the system proceeds and the output parquet column is omitted (simulation engine handles missing optional columns gracefully)
4. **Given** a required field is mapped, **When** the analyst hovers over the field label, **Then** a tooltip describes the field's purpose in plain language (e.g., "Annual salary rate — used to calculate compensation growth and DC plan contributions")

---

### User Story 3 — Data Formatting Guidance and Auto-Correction (Priority: P1)

When an input column is mapped to a date or decimal field, the system inspects the sample values, detects the format in use, and either automatically parses it correctly or prompts the analyst to confirm the format — before generation fails with a cryptic type error.

**Why this priority**: Date and compensation format mismatches are the most common reason import fails silently or produces wrong data. Proactive format detection eliminates this class of failure.

**Independent Test**: Map a column containing dates in "MM/DD/YYYY" format to `employee_hire_date`. The system must detect the format, show a sample of parsed values, and write correctly-typed DATE values to the parquet without requiring analyst intervention.

**Acceptance Scenarios**:

1. **Given** an input column is mapped to a date field, **When** the mapping is saved, **Then** the system samples the first 20 non-null values and displays the detected date format alongside a preview of parsed dates
2. **Given** the detected date format is ambiguous (e.g., "01/02/03"), **When** the analyst reviews the mapping, **Then** the system shows two or three format interpretations with parsed sample values and asks the analyst to confirm the correct one
3. **Given** an input column is mapped to a decimal/compensation field, **When** the mapping is saved, **Then** the system detects and strips common formatting (commas, currency symbols like `$`, parentheses for negatives) and previews the numeric result
4. **Given** an input column mapped to `active` (boolean) contains text values (e.g., "Y", "N", "Active", "Terminated"), **When** the analyst reviews, **Then** the system auto-detects the truthy/falsy pattern and previews correct boolean values
5. **Given** sample values cannot be parsed under any detected format, **When** the analyst reviews, **Then** the system flags the column with a clear error showing which sample values are unparseable and suggests a fix

---

### User Story 4 — Predictive Mapping from Prior Imports (Priority: P2)

When an analyst imports a file from the same source system they've used before (e.g., the same HR export format), the system recognizes the column pattern and pre-applies the prior mapping — so repeat uploads need zero manual mapping.

**Why this priority**: Analysts who run annual or quarterly imports from the same HR system will use this workflow repeatedly. Reducing per-import mapping effort to zero for repeat sources dramatically improves adoption.

**Independent Test**: Import a CSV, confirm a full mapping, generate parquet. Then import a second CSV with identical column names (simulating next year's export). The prior mapping is auto-applied with no manual steps required.

**Acceptance Scenarios**:

1. **Given** an analyst has previously completed an import mapping, **When** they upload a new file with the same column headers, **Then** the prior mapping is automatically applied and all suggestions show "Previously mapped" confidence
2. **Given** a new file has most but not all of the prior columns, **When** the mapping is pre-applied, **Then** matched columns are filled from prior mapping and unmatched columns are flagged for review
3. **Given** a saved mapping template exists in the workspace, **When** the analyst uploads a file, **Then** they can choose to apply any available template to pre-populate the mapping

---

### User Story 5 — Mapped Preview with Data Quality Warnings (Priority: P2)

Before generating the parquet, analysts can view a preview of the first 50 rows with all mappings and format transformations applied — and the system highlights any rows with data quality issues (nulls in required fields, out-of-range values, duplicate employee IDs).

**Why this priority**: Preview with data quality warnings gives analysts a final check before committing, catching issues that would cause simulation failures downstream.

**Independent Test**: Map a census with 5 duplicate employee IDs. The preview should flag those rows and warn the analyst before generation. After generation, verify that the parquet retains only the most recent hire date for each duplicate (matching `stg_census_data.sql` deduplication logic).

**Acceptance Scenarios**:

1. **Given** field mappings are configured, **When** the analyst clicks "Preview Mapped Data", **Then** a table shows the first 50 rows with canonical column names and formatted values
2. **Given** preview is displayed, **When** the system detects null values in required columns, **Then** affected rows are highlighted and a count of rows-with-issues is shown
3. **Given** preview shows duplicate `employee_id` values, **When** the analyst reviews, **Then** a warning notes that duplicates exist and explains that the simulation engine will keep the row with the most recent hire date — the import wizard does not deduplicate; duplicates are passed through to the parquet as-is
4. **Given** compensation values appear unreasonably large or small (e.g., < $1,000 or > $10,000,000 annually), **When** the preview renders, **Then** a soft warning flags the outlier rows for analyst review

---

### Edge Cases

- What if the uploaded file has no column headers? → System prompts analyst to specify whether row 1 is a header, and if not, generates generic column names (Column_1, Column_2…) for mapping
- What if two input columns are mapped to the same canonical output field? → System shows a conflict error and requires the analyst to resolve the duplicate target before proceeding
- What if `employee_id` column contains nulls? → System blocks generation and shows the count and row numbers of null IDs (employee_id is the primary key — nulls break the simulation)
- What if the file has 0 rows after the header? → System shows an error and prevents session creation
- What if date parsing produces dates outside plausible ranges (e.g., birth year 1850 or hire year 2099)? → System flags as a data quality warning, not a hard error (analyst may have unusual data)
- What if the analyst changes the sheet selection on an Excel file after mapping? → Mappings are cleared and the analyst must re-map for the new sheet's columns

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain and expose the canonical census schema definition (required fields, optional fields, data types, plain-language descriptions) as a first-class artifact that drives the mapping wizard
- **FR-002**: System MUST automatically suggest a target canonical field for each detected input column using name-similarity matching and value-pattern analysis, with a confidence level (High ≥ 85% / Medium 50–84% / Low < 50% similarity score against canonical field name and known aliases) for each suggestion
- **FR-003**: Suggestions MUST consider common column name aliases (e.g., "EmpID" → `employee_id`, "DOB" → `employee_birth_date`, "Salary" / "Annual Salary" / "Base Pay" → `employee_gross_compensation`, "Active" / "Status" → `active`)
- **FR-003a**: The mapping target selection MUST be constrained to canonical fields only — analysts select from the canonical field list; free-text target naming is not permitted at any point in the workflow
- **FR-004**: System MUST visually distinguish required canonical fields from optional ones throughout the mapping interface
- **FR-005**: System MUST prevent parquet generation when any required canonical field has no input mapping, with a specific error message per unmapped required field explaining its purpose in plain language
- **FR-006**: For columns mapped to date fields, system MUST inspect sample values, detect the format (ISO 8601, MM/DD/YYYY, DD/MM/YYYY, Excel serial date, etc.), and apply the correct parser — prompting the analyst to confirm when ambiguous
- **FR-007**: For columns mapped to decimal/compensation fields, system MUST auto-strip currency symbols, commas, and parenthetical negatives from values before type conversion
- **FR-008**: For columns mapped to the `active` boolean field, system MUST detect and apply common truthy/falsy text patterns (Y/N, Yes/No, True/False, Active/Terminated, 1/0) and display the detection mapping to the analyst
- **FR-009**: System MUST display a "Preview Mapped Data" view showing at least the first 50 rows with canonical column names, transformed values, and per-row data quality flags before generation
- **FR-010**: Preview MUST flag rows with null values in required fields, duplicate `employee_id` values (with a note that the simulation engine deduplicates by keeping the most recent hire date), and compensation values outside a plausible annual range; the import wizard does NOT remove duplicates — they are written to the parquet as-is
- **FR-011**: System MUST store completed mapping configurations and automatically apply them to future uploads with matching column headers in the same workspace
- **FR-012**: Generated parquet files MUST use exactly the canonical column names defined in FR-001 — analyst-invented or free-form column names are not permitted anywhere in the workflow or output; prior 087 free-form mapping templates are superseded and will not be applied or migrated
- **FR-013**: Optional canonical fields with no input mapping MUST be omitted from the output parquet (not written as a null column) so the simulation engine's `UNION ALL BY NAME` schema scaffold handles them correctly
- **FR-014**: System MUST log all mapping decisions (auto-suggested, user-confirmed, user-overridden) per import session for audit purposes

### Key Entities

- **CensusSchema**: The immutable canonical field definitions — field name, required flag, data type, plain-language description, common aliases. Single source of truth for the mapping wizard.
- **ColumnSuggestion**: A candidate mapping from one input column to one canonical field, with a confidence score and the reasoning (name match, value pattern, prior mapping)
- **FieldMapping**: A confirmed mapping from input column to canonical field, including the resolved format rule (e.g., date format string, boolean alias map), and whether it was auto-suggested or user-confirmed
- **FormatRule**: The detected or user-confirmed transformation applied to a column (date format, decimal stripping pattern, boolean alias map)
- **MappingSession**: An import session extended with schema-driven mapping state — which canonical fields are mapped, which are confirmed, which are missing
- **DataQualityWarning**: A per-row or per-column issue detected in the preview (null required field, duplicate key, outlier value)

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a typical HR census export, the system correctly auto-suggests mappings for all four required fields with no manual correction needed in at least 80% of first-time imports from a given source
- **SC-002**: Analysts complete the full mapping workflow for a repeat import (same source, same columns) in under 30 seconds — primarily just reviewing auto-applied prior mapping and clicking generate
- **SC-003**: Zero imports that pass validation produce a parquet file that fails to load in `stg_census_data.sql` due to wrong column names or wrong data types
- **SC-004**: Analysts report understanding why each required field is needed (validated via plain-language descriptions in the UI) — no documentation lookup required to complete a mapping
- **SC-005**: Date format detection correctly parses dates in at least 5 common formats (ISO 8601, MM/DD/YYYY, DD/MM/YYYY, YYYYMMDD, Excel serial) without analyst-specified format strings
- **SC-006**: Data quality warnings in preview identify at least 90% of rows that would cause simulation failures (null required fields, duplicate employee IDs) before the analyst commits to generation

---

## Assumptions

- The canonical schema is stable — column names in `stg_census_data.sql` will not change without a corresponding update to the schema definition in this feature
- The simulation engine's `UNION ALL BY NAME` approach means that optional columns absent from the parquet are handled gracefully; the import wizard does not need to write null columns for unmapped optional fields
- Analysts are the primary users; they have domain knowledge of their HR data but may not know the simulation engine's schema requirements
- The `employee_ssn` field contains synthetic identifiers (e.g., "SSN-00000001") assigned sequentially, not real Social Security Numbers — no PII masking, log exclusion, or compliance controls are required for this field
- The existing 087 import infrastructure (file upload, session management, parquet generation, audit logging) is preserved and this feature modifies the mapping step only — it does not replace file handling or storage
- Auto-suggestion uses string similarity and value pattern analysis only; it does not use ML models or external services
- Prior-mapping persistence is workspace-scoped — mappings from one workspace do not influence suggestions in another
