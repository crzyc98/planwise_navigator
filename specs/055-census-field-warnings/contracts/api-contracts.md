# API Contracts: Census Field Validation Warnings

**Branch**: `055-census-field-warnings` | **Date**: 2026-02-20

## New Model: StructuredWarning

```python
class StructuredWarning(BaseModel):
    """A structured validation warning about a census column."""
    field_name: str = Field(..., description="Expected census column name")
    severity: Literal["critical", "optional"] = Field(..., description="Warning severity tier")
    warning_type: Literal["missing", "alias_found"] = Field(..., description="Type of warning")
    impact_description: str = Field(..., description="Human-readable simulation impact")
    detected_alias: Optional[str] = Field(None, description="Alias column name found in file")
    suggested_action: str = Field(..., description="Recommended user action")
```

## Modified Model: FileUploadResponse

**Endpoint**: `POST /api/workspaces/{workspace_id}/upload`

```python
class FileUploadResponse(BaseModel):
    success: bool
    file_path: str
    file_name: str
    file_size_bytes: int
    row_count: int
    columns: List[str]
    upload_timestamp: datetime
    validation_warnings: List[str]  # EXISTING - kept for backward compat
    structured_warnings: List[StructuredWarning] = Field(  # NEW
        default_factory=list,
        description="Structured validation warnings with severity and impact"
    )
```

**Example response with critical warnings**:
```json
{
  "success": true,
  "file_path": "data/census.parquet",
  "file_name": "census.parquet",
  "file_size_bytes": 524288,
  "row_count": 500,
  "columns": ["employee_id", "employee_gross_compensation", "active"],
  "upload_timestamp": "2026-02-20T10:30:00",
  "validation_warnings": [
    "Recommended column missing: employee_hire_date",
    "Recommended column missing: employee_birth_date",
    "Recommended column missing: employee_termination_date"
  ],
  "structured_warnings": [
    {
      "field_name": "employee_hire_date",
      "severity": "critical",
      "warning_type": "missing",
      "impact_description": "Tenure calculations, new hire identification, turnover modeling, and annualized compensation will not work correctly",
      "detected_alias": null,
      "suggested_action": "Add an employee_hire_date column to your census file"
    },
    {
      "field_name": "employee_birth_date",
      "severity": "critical",
      "warning_type": "missing",
      "impact_description": "Age-based calculations, age band segmentation, HCE determination, and retirement eligibility will not work correctly",
      "detected_alias": null,
      "suggested_action": "Add an employee_birth_date column to your census file"
    },
    {
      "field_name": "employee_termination_date",
      "severity": "optional",
      "warning_type": "missing",
      "impact_description": "Terminated employee identification may be incomplete",
      "detected_alias": null,
      "suggested_action": "Add an employee_termination_date column, or ensure the active column is present"
    }
  ]
}
```

**Example response with alias detection**:
```json
{
  "structured_warnings": [
    {
      "field_name": "employee_hire_date",
      "severity": "critical",
      "warning_type": "alias_found",
      "impact_description": "Tenure calculations, new hire identification, turnover modeling, and annualized compensation will not work correctly",
      "detected_alias": "hire_date",
      "suggested_action": "Rename column 'hire_date' to 'employee_hire_date' for full compatibility"
    }
  ]
}
```

## Modified Model: FileValidationResponse

**Endpoint**: `POST /api/workspaces/{workspace_id}/validate-path`

```python
class FileValidationResponse(BaseModel):
    valid: bool
    file_path: str
    exists: bool
    readable: bool = False
    file_size_bytes: Optional[int] = None
    row_count: Optional[int] = None
    columns: Optional[List[str]] = None
    last_modified: Optional[datetime] = None
    error_message: Optional[str] = None
    validation_warnings: List[str] = Field(  # NEW
        default_factory=list,
        description="Non-fatal validation warnings"
    )
    structured_warnings: List[StructuredWarning] = Field(  # NEW
        default_factory=list,
        description="Structured validation warnings with severity and impact"
    )
```

## Frontend TypeScript Interfaces

```typescript
export interface StructuredWarning {
  field_name: string;
  severity: 'critical' | 'optional';
  warning_type: 'missing' | 'alias_found';
  impact_description: string;
  detected_alias: string | null;
  suggested_action: string;
}

export interface FileUploadResponse {
  success: boolean;
  file_path: string;
  file_name: string;
  file_size_bytes: number;
  row_count: number;
  columns: string[];
  upload_timestamp: string;
  validation_warnings: string[];
  structured_warnings: StructuredWarning[];  // NEW
}

export interface FileValidationResponse {
  valid: boolean;
  file_path: string;
  exists: boolean;
  readable: boolean;
  file_size_bytes?: number;
  row_count?: number;
  columns?: string[];
  last_modified?: string;
  error_message?: string;
  validation_warnings: string[];             // NEW
  structured_warnings: StructuredWarning[];  // NEW
}
```
