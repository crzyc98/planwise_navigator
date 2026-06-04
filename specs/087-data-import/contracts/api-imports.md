# API Contract: Data Import Endpoints

**Feature**: 087-data-import
**Router prefix**: `/api/workspaces/{workspace_id}/imports`
**Date**: 2026-05-30

All endpoints follow the existing FastAPI patterns in `planalign_api/routers/`.
All request/response bodies are JSON unless noted.
All datetime fields are ISO 8601 UTC strings.

**Error envelope** (all 4xx/5xx responses):
```json
{
  "correlation_id": "uuid4",
  "error_code": "string",
  "message": "string",
  "resolution_hint": "string",
  "context": {}
}
```
`correlation_id` is always the `import_id` for import-scoped errors, or a request-scoped UUID for pre-session errors (e.g., upload validation). Include it in all bug reports.

---

## POST `/api/workspaces/{workspace_id}/imports/upload`

Upload a CSV or Excel file to begin an import session.

**Request**: `multipart/form-data`
- `file` (required): CSV (`.csv`) or Excel (`.xlsx`) file, max 500MB

**Response** `201 Created`:
```json
{
  "import_id": "uuid4",
  "workspace_id": "string",
  "original_filename": "census_2025.xlsx",
  "source_format": "xlsx",
  "available_sheets": ["Sheet1", "Employees"],
  "selected_sheet": null,
  "row_count": 4823,
  "column_count": 12,
  "detected_columns": [
    {
      "name": "EMP_ID",
      "inferred_type": "string",
      "null_count": 0,
      "sample_values": ["E001", "E002", "E003"]
    }
  ],
  "status": "uploaded",
  "created_at": "2026-05-30T14:00:00Z",
  "created_by": "analyst@fidelity.com",
  "preview_rows": [
    {"EMP_ID": "E001", "HIRE_DATE": "01/15/2020", "SALARY": "95000"}
  ]
}
```

**Error responses**:
- `400`: No filename, unsupported format
- `413`: File exceeds 500MB
- `404`: Workspace not found
- `422`: File has 0 data rows or is unparseable

---

## PATCH `/api/workspaces/{workspace_id}/imports/{import_id}/sheet`

Select an Excel sheet (required if `available_sheets` has > 1 entry and `selected_sheet` is null).

**Request body**:
```json
{
  "sheet_name": "Employees"
}
```

**Response** `200 OK`: Returns updated ImportSession (same shape as upload response, with refreshed `detected_columns` and `preview_rows` for the selected sheet).

**Error responses**:
- `404`: Import session not found
- `422`: Sheet name not in `available_sheets`

---

## GET `/api/workspaces/{workspace_id}/imports/{import_id}/preview`

Retrieve raw data preview (first 100 rows) from the uploaded file, before any mapping is applied.

**Query params**: None

**Response** `200 OK`:
```json
{
  "import_id": "uuid4",
  "columns": ["EMP_ID", "HIRE_DATE", "SALARY"],
  "rows": [
    {"EMP_ID": "E001", "HIRE_DATE": "01/15/2020", "SALARY": "95000"}
  ],
  "total_row_count": 4823,
  "preview_row_count": 100
}
```

---

## PUT `/api/workspaces/{workspace_id}/imports/{import_id}/mapping`

Save the complete field mapping configuration for this import session.

**Request body**:
```json
{
  "field_mappings": [
    {
      "input_column": "EMP_ID",
      "output_column": "employee_id",
      "output_type": "string",
      "is_required": true,
      "is_excluded": false,
      "transformations": []
    },
    {
      "input_column": "HIRE_DATE",
      "output_column": "hire_date",
      "output_type": "date",
      "is_required": false,
      "is_excluded": false,
      "transformations": [
        {
          "transform_type": "date_parse",
          "params": {"format": "%m/%d/%Y"}
        }
      ]
    },
    {
      "input_column": "NOTES",
      "output_column": "notes",
      "output_type": "string",
      "is_required": false,
      "is_excluded": true,
      "transformations": []
    }
  ]
}
```

**Response** `200 OK`:
```json
{
  "import_id": "uuid4",
  "status": "mapping_in_progress",
  "mapping_saved_at": "2026-05-30T14:05:00Z",
  "validation_errors": [],
  "output_column_count": 8
}
```

**`validation_errors`** (non-empty if mapping is invalid but still saved):
```json
[
  {
    "field": "output_column",
    "input_column": "HIRE_DATE",
    "message": "Output column name must match [a-z][a-z0-9_]+"
  }
]
```

**Error responses**:
- `404`: Import session not found
- `422`: Duplicate output column names, or input_column not in detected columns

---

## GET `/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview`

Return first 100 rows with all field mappings and transformations applied. Used for validation before generation.

**Response** `200 OK`:
```json
{
  "import_id": "uuid4",
  "columns": ["employee_id", "hire_date", "salary"],
  "rows": [
    {"employee_id": "E001", "hire_date": "2020-01-15", "salary": 95000.0}
  ],
  "total_row_count": 4823,
  "preview_row_count": 100,
  "transformation_warnings": [
    {
      "input_column": "HIRE_DATE",
      "rows_affected": 3,
      "message": "3 values could not be parsed as date with format %m/%d/%Y; will be null"
    }
  ]
}
```

**Error responses**:
- `404`: Import not found
- `409`: No mapping saved yet (status is `uploaded`)

---

## POST `/api/workspaces/{workspace_id}/imports/{import_id}/generate`

Trigger parquet file generation from the saved field mappings.

**Request body**: (empty `{}`)

**Response** `202 Accepted` (generation always runs as a background task; client polls for status):
```json
{
  "import_id": "uuid4",
  "correlation_id": "uuid4",
  "status": "generating",
  "started_at": "2026-05-30T14:10:00Z"
}
```

Poll `GET .../imports/{import_id}` every 2 seconds until `status` is `completed` or `failed`.

**Final response shape** (from polling endpoint when `status` = `completed`):
```json
{
  "import_id": "uuid4",
  "correlation_id": "uuid4",
  "status": "completed",
  "parquet_file": {
    "file_id": "uuid4",
    "filename": "20260530_141023_census_2025.parquet",
    "row_count": 4823,
    "file_size_bytes": 287400,
    "created_at": "2026-05-30T14:10:23Z"
  }
}
```

**Error responses**:
- `404`: Import not found
- `409`: Session status not `mapping_in_progress` (must save mapping first)
- `422`: Mapping has unresolved validation errors

---

## GET `/api/workspaces/{workspace_id}/imports/{import_id}`

Get current status of an import session.

**Response** `200 OK`:
```json
{
  "import_id": "uuid4",
  "status": "completed | failed | generating | ...",
  "error_message": null,
  "error_rows": [],
  "parquet_file_id": "uuid4"
}
```

If `status` is `failed`:
```json
{
  "import_id": "uuid4",
  "correlation_id": "uuid4",
  "status": "failed",
  "error_message": "Type conversion failed: column 'SALARY' row 42 value 'N/A' cannot be cast to decimal",
  "resolution_hint": "Check column 'SALARY' for non-numeric values before mapping to decimal type",
  "error_rows": [
    {"row_number": 42, "column": "SALARY", "value": "N/A", "error": "cannot cast to decimal"}
  ]
}
```

---

## GET `/api/workspaces/{workspace_id}/parquet-files`

List all generated parquet files in the workspace.

**Response** `200 OK`:
```json
{
  "parquet_files": [
    {
      "file_id": "uuid4",
      "filename": "20260530_census_2025.parquet",
      "original_filename": "census_2025.xlsx",
      "row_count": 4823,
      "file_size_bytes": 287400,
      "schema": [
        {"name": "employee_id", "type": "string"},
        {"name": "hire_date", "type": "date"}
      ],
      "created_at": "2026-05-30T14:10:23Z",
      "created_by": "analyst@fidelity.com"
    }
  ],
  "total_count": 1
}
```

---

## GET `/api/workspaces/{workspace_id}/parquet-files/{file_id}/download`

Download a generated parquet file.

**Response** `200 OK`: Binary parquet file stream
`Content-Type: application/octet-stream`
`Content-Disposition: attachment; filename="{filename}"`

**Error responses**:
- `404`: File not found

---

## DELETE `/api/workspaces/{workspace_id}/parquet-files/{file_id}`

Delete a parquet file. Restricted to workspace manager (workspace creator).

**Response** `204 No Content`

**Error responses**:
- `403`: Requesting user is not workspace manager
- `404`: File not found

---

## GET `/api/workspaces/{workspace_id}/mapping-templates`

List saved mapping templates for the workspace.

**Response** `200 OK`:
```json
{
  "templates": [
    {
      "template_id": "uuid4",
      "name": "Standard HR Export Format",
      "description": "Maps SAP HR column names to canonical format",
      "field_count": 8,
      "created_at": "2026-05-01T10:00:00Z",
      "created_by": "analyst@fidelity.com"
    }
  ]
}
```

---

## POST `/api/workspaces/{workspace_id}/mapping-templates`

Save the current import session's mapping as a reusable template.

**Request body**:
```json
{
  "import_id": "uuid4",
  "name": "Standard HR Export Format",
  "description": "Maps SAP HR column names to canonical format"
}
```

**Response** `201 Created`:
```json
{
  "template_id": "uuid4",
  "name": "Standard HR Export Format",
  "created_at": "2026-05-30T14:15:00Z"
}
```

---

## POST `/api/workspaces/{workspace_id}/imports/{import_id}/apply-template`

Apply a saved template's field mappings to an import session (replaces existing mapping).

**Request body**:
```json
{
  "template_id": "uuid4"
}
```

**Response** `200 OK`: Updated mapping (same shape as `PUT .../mapping` response, with auto-matched columns).

Fields in the template are matched by `input_column` name. Unmatched template fields are silently skipped; source columns not in the template remain unmapped.
