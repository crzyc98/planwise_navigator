# Data Model: Data Import with Field Mapping

**Feature**: 087-data-import
**Date**: 2026-05-30

---

## Entity Overview

```
ImportSession
    │ 1
    │ has many
    ▼ n
FieldMapping          ◄── references ── MappingTemplate
    │
    │ (when generated)
    ▼
ParquetFile
```

---

## Entities

### ImportSession

Represents one upload-to-parquet workflow instance. Created when a file is uploaded; destroyed when the analyst generates the parquet or explicitly cancels.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `import_id` | `str` (UUID4) | PK, immutable | Auto-generated on creation |
| `correlation_id` | `str` (UUID4) | Immutable, equals `import_id` | Included in all error responses for diagnosis |
| `workspace_id` | `str` | Required, FK to Workspace | Must reference an existing workspace |
| `original_filename` | `str` | Required, max 255 chars | Original uploaded file name |
| `source_format` | `Literal["csv", "xlsx"]` | Required | Detected from file extension |
| `sheet_name` | `Optional[str]` | None for CSV | Selected Excel sheet name |
| `available_sheets` | `List[str]` | Empty for CSV | All sheets found in XLSX |
| `row_count` | `int` | >= 0 | Total rows in source file |
| `column_count` | `int` | >= 1 | Number of columns detected |
| `detected_columns` | `List[DetectedColumn]` | Non-empty | Schema inferred from source |
| `status` | `ImportStatus` | See enum | Lifecycle state |
| `created_at` | `datetime` | UTC, immutable | When file was uploaded |
| `created_by` | `str` | Required | Username/identifier of uploader |
| `mapping_saved_at` | `Optional[datetime]` | UTC | When mapping was last saved |
| `parquet_file_id` | `Optional[str]` | FK to ParquetFile | Set on successful generation |

**Storage**: `workspaces/{workspace_id}/imports/{import_id}/metadata.json`

**State Transitions**:
```
UPLOADED → MAPPING_IN_PROGRESS → GENERATING → COMPLETED
                                       └──────→ FAILED
UPLOADED → CANCELLED
```

---

### ImportStatus (Enum)

| Value | Meaning |
|-------|---------|
| `uploaded` | File received and parsed; awaiting mapping config |
| `mapping_in_progress` | Analyst is configuring field mappings |
| `generating` | Parquet generation in progress |
| `completed` | Parquet file successfully generated |
| `failed` | Generation failed; error details stored |
| `cancelled` | Session discarded by analyst |

---

### DetectedColumn

Represents a column as inferred from the source file. Embedded in `ImportSession.detected_columns`.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `name` | `str` | Unique within session | Original column name from header |
| `inferred_type` | `InferredType` | See enum | Pandas dtype inference result |
| `null_count` | `int` | >= 0 | Number of null/empty values |
| `sample_values` | `List[str]` | Up to 5 | Representative non-null values |

---

### InferredType (Enum)

| Value | Detected From |
|-------|--------------|
| `string` | Object dtype, no numeric parse |
| `integer` | Int64 dtype |
| `decimal` | Float64 dtype |
| `boolean` | Bool dtype |
| `date` | Datetime dtype, no time component |
| `timestamp` | Datetime dtype, has time component |
| `unknown` | Could not infer |

---

### FieldMapping

Defines how one input column maps to one output column, including optional transformations. A session's complete set of field mappings is stored as a JSON array.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `mapping_id` | `str` (UUID4) | PK, immutable | Auto-generated |
| `import_id` | `str` | FK to ImportSession | Parent session |
| `input_column` | `str` | Required | Must match a `DetectedColumn.name` |
| `output_column` | `str` | Required, max 128 chars, `[a-z0-9_]` | Target parquet column name |
| `output_type` | `OutputType` | Required | Target data type in parquet |
| `is_required` | `bool` | Default: `False` | If True, null input rows cause error |
| `is_excluded` | `bool` | Default: `False` | If True, column omitted from output |
| `transformations` | `List[Transformation]` | Ordered, max 5 | Applied in order |

**Storage**: `workspaces/{workspace_id}/imports/{import_id}/mapping.json`

---

### OutputType (Enum)

| Value | Parquet Type | Notes |
|-------|-------------|-------|
| `string` | `UTF8` | Default for object columns |
| `integer` | `INT64` | |
| `decimal` | `DOUBLE` | |
| `boolean` | `BOOLEAN` | |
| `date` | `DATE32` | Stored as days since epoch |
| `timestamp` | `TIMESTAMP` | UTC microseconds |

---

### Transformation

An ordered instruction applied to a field during parquet generation. Multiple transformations can be chained on one column.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `transform_type` | `TransformType` | Required | See enum |
| `params` | `Dict[str, Any]` | Type-specific | See params table below |

**TransformType enum and params**:

| `transform_type` | Required `params` keys | Example |
|-----------------|----------------------|---------|
| `rename` | (none — output_column handles this) | — |
| `string_case` | `case: "upper" \| "lower" \| "title"` | `{"case": "upper"}` |
| `date_parse` | `format: str` | `{"format": "%m/%d/%Y"}` |
| `null_replace` | `value: Any` | `{"value": "UNKNOWN"}` |
| `null_drop` | (none) | `{}` |
| `calculated_field` | `expression: str` | `{"expression": "col_a + ' ' + col_b"}` |

**Calculated field safety**: Expressions are validated against a whitelist of allowed operations (string concatenation, arithmetic: `+`, `-`, `*`, `/`; column references). Python builtins and `import` are never allowed.

---

### ParquetFile

Represents a successfully generated parquet output file in workspace data storage. This entity is permanent (immutable after creation; only deletion by manager is allowed).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `file_id` | `str` (UUID4) | PK, immutable | |
| `workspace_id` | `str` | FK to Workspace | |
| `import_id` | `str` | FK to ImportSession | The import that created this |
| `filename` | `str` | `{timestamp}_{original_name}.parquet` | Stored filename |
| `storage_path` | `str` | Absolute filesystem path | `workspaces/{id}/data/imports/...` |
| `original_filename` | `str` | | Source file name for display |
| `row_count` | `int` | >= 0 | Rows in the parquet output |
| `file_size_bytes` | `int` | >= 0 | Parquet file size |
| `schema` | `List[ParquetColumn]` | Non-empty | Output column names and types |
| `created_at` | `datetime` | UTC, immutable | When generation completed |
| `created_by` | `str` | Required | Uploader username |

**Storage**: Index at `workspaces/{workspace_id}/data/imports/index.json` (append-only list of ParquetFile metadata). Parquet files at `workspaces/{workspace_id}/data/imports/{filename}`.

---

### ParquetColumn

Embedded in `ParquetFile.schema`.

| Field | Type | Notes |
|-------|------|-------|
| `name` | `str` | Output column name |
| `type` | `OutputType` | Parquet type |

---

### MappingTemplate

A named, reusable set of field mappings saved at workspace level.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `template_id` | `str` (UUID4) | PK, immutable | |
| `workspace_id` | `str` | FK to Workspace | Workspace-scoped |
| `name` | `str` | Required, max 128 chars | User-provided display name |
| `description` | `Optional[str]` | Max 512 chars | Optional description |
| `field_mappings` | `List[FieldMapping]` | Min 1 | Stored without `import_id` |
| `created_at` | `datetime` | UTC, immutable | |
| `created_by` | `str` | Required | |

**Storage**: `workspaces/{workspace_id}/templates/imports/{template_id}.json`

---

## Validation Rules

| Rule | Entity | Constraint |
|------|--------|-----------|
| Unique output column names | FieldMapping set | No two active (non-excluded) mappings may share `output_column` |
| Input column existence | FieldMapping | `input_column` must be in `ImportSession.detected_columns` |
| Output column naming | FieldMapping | `output_column` matches `^[a-z][a-z0-9_]{0,127}$` |
| Max transformation chain | FieldMapping | Max 5 transformations per field |
| Calculated field safety | Transformation | Expression validated before save; no Python builtins |
| File size on upload | ImportSession | Source file ≤ 500MB |
| Minimum source rows | ImportSession | Source file must have ≥ 1 data row |

---

## Filesystem Layout Summary

```
workspaces/{workspace_id}/
├── imports/                         # In-progress import sessions (temp)
│   └── {import_id}/
│       ├── source.parquet           # Uploaded file, immediately normalized
│       ├── mapping.json             # FieldMapping[] array
│       └── metadata.json            # ImportSession metadata
├── data/
│   └── imports/
│       ├── index.json               # ParquetFile[] list (append-only)
│       └── {timestamp}_{name}.parquet   # Final output files
└── templates/
    └── imports/
        └── {template_id}.json       # MappingTemplate
```
