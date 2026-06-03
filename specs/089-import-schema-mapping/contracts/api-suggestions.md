# API Contract: Import Suggestions Endpoint

**Feature**: 089-import-schema-mapping
**Date**: 2026-06-03

---

## New Endpoint

### GET `/{workspace_id}/imports/{import_id}/suggestions`

Returns auto-suggestions for field mappings, format detection results, and an initial data quality scan — all in one round trip.

**Auth**: `X-User-Id` header (same as all other import endpoints)

**Success Response** — `200 OK`

```json
{
  "import_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "suggestions": [
    {
      "input_column": "Hire Date",
      "suggested_canonical_field": "employee_hire_date",
      "confidence": "high",
      "confidence_score": 0.91,
      "reason": "alias_match",
      "format_detection": {
        "detected_format": "%m/%d/%Y",
        "parsed_sample_values": ["2018-03-15", "2019-07-22", "2021-01-08"],
        "is_ambiguous": false,
        "format_options": null
      }
    },
    {
      "input_column": "Salary",
      "suggested_canonical_field": "employee_gross_compensation",
      "confidence": "high",
      "confidence_score": 0.95,
      "reason": "alias_match",
      "format_detection": {
        "detected_format": "currency_string",
        "parsed_sample_values": ["95000.00", "72500.00", "110000.00"],
        "is_ambiguous": false,
        "format_options": null
      }
    },
    {
      "input_column": "Dept Code",
      "suggested_canonical_field": null,
      "confidence": "low",
      "confidence_score": 0.21,
      "reason": "no_match",
      "format_detection": null
    }
  ],
  "data_quality": {
    "duplicate_employee_id_count": 3,
    "null_required_field_counts": {
      "employee_id": 0,
      "employee_birth_date": 2,
      "employee_hire_date": 0,
      "employee_gross_compensation": 0,
      "active": 0
    },
    "compensation_outlier_count": 1
  },
  "canonical_schema": [
    {
      "field_name": "employee_id",
      "required": true,
      "data_type": "string",
      "description": "Unique employee identifier — the primary key used across all simulation events"
    },
    {
      "field_name": "employee_hire_date",
      "required": true,
      "data_type": "date",
      "description": "Original hire date — used to calculate service tenure and plan eligibility"
    }
  ]
}
```

Note: `null_required_field_counts` in `data_quality` is computed based on which column (if any) is *currently suggested* as the mapping for each required field. If the required field has no suggestion yet, it is omitted from the count.

**Error Responses**

| Status | Condition |
|---|---|
| `404 Not Found` | Workspace or import session not found |
| `409 Conflict` | Import session source parquet not available (e.g., session was created but file upload failed) |

---

## Modified Endpoint: PUT `/{workspace_id}/imports/{import_id}/mapping`

**Change**: `_validate_mapping()` now additionally checks that every non-excluded `output_column` value is a canonical field name from `CensusSchema`. Free-form names return a 422 error.

**New error shape** (added to existing `MappingValidationError`):

```json
{
  "field": "output_column",
  "input_column": "Dept Code",
  "message": "Output column 'dept_code' is not a recognized census field. Choose from: employee_id, employee_birth_date, ..."
}
```

**Unchanged**: All other validation rules (no duplicate output_column, input_column must exist in detected columns).

---

## Unchanged Endpoints (087 contracts preserved)

All other endpoints from 087 retain their existing contracts:

- `POST /{workspace_id}/imports/upload`
- `PATCH /{workspace_id}/imports/{import_id}/sheet`
- `GET /{workspace_id}/imports/{import_id}/preview`
- `GET /{workspace_id}/imports/{import_id}/mapped-preview`
- `GET /{workspace_id}/imports/{import_id}`
- `POST /{workspace_id}/imports/{import_id}/generate`
- `GET /{workspace_id}/parquet-files`
- `GET /{workspace_id}/parquet-files/{file_id}/download`
- `DELETE /{workspace_id}/parquet-files/{file_id}`
- `GET /{workspace_id}/mapping-templates` (preserved; 087 templates ignored by suggestion engine)
- `POST /{workspace_id}/imports/{import_id}/apply-template` (preserved; only works if template has canonical output_columns)
