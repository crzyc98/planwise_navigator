# Data Model: Schema-Aware Import with Predictive Field Mapping

**Feature**: 089-import-schema-mapping
**Date**: 2026-06-03

---

## Canonical Census Schema (static definition)

The canonical schema is defined once in `census_schema.py` and never stored in the database. It is the single source of truth for what column names the simulation engine accepts.

### CensusFieldDefinition

```python
@dataclass(frozen=True)
class CensusFieldDefinition:
    field_name: str          # Canonical output column name (e.g., "employee_hire_date")
    required: bool           # True = blocks generation if unmapped
    data_type: str           # "string" | "date" | "decimal" | "boolean"
    description: str         # Plain-language explanation for UI tooltip
    aliases: list[str]       # Common input column names that map to this field
```

### Canonical Fields (16 total)

| field_name | required | data_type | Aliases (partial) |
|---|---|---|---|
| `employee_id` | **Yes** | string | EmpID, Emp_ID, ID, EmployeeID, Employee Number |
| `employee_birth_date` | **Yes** | date | DOB, Date of Birth, BirthDate, Birth_Date |
| `employee_hire_date` | **Yes** | date | Hire Date, HireDate, Date of Hire, Start Date |
| `employee_gross_compensation` | **Yes** | decimal | Salary, Annual Salary, Base Pay, Gross Comp, Compensation |
| `active` | **Yes** | boolean | Status, Active, Is Active, Employment Status, Employed |
| `employee_ssn` | No | string | SSN, Social Security, SSN_ID |
| `employee_termination_date` | No | date | Term Date, Termination Date, Separation Date, End Date |
| `employee_capped_compensation` | No | decimal | Capped Comp, 415 Limit, IRS Cap |
| `employee_deferral_rate` | No | decimal | Deferral Rate, Deferral %, Contribution Rate |
| `employee_contribution` | No | decimal | Total EE Contribution, Employee Contribution |
| `pre_tax_contribution` | No | decimal | Pre-Tax, Traditional 401k, Pre Tax Contribution |
| `roth_contribution` | No | decimal | Roth, Roth 401k |
| `after_tax_contribution` | No | decimal | After Tax, After-Tax |
| `employer_core_contribution` | No | decimal | ER Core, Non-Elective, Employer Core |
| `employer_match_contribution` | No | decimal | ER Match, Employer Match, Matching |
| `eligibility_entry_date` | No | date | Entry Date, Eligibility Date, Plan Entry |

---

## New Models (Python — `models/imports.py` additions)

### ConfidenceLevel

```python
ConfidenceLevel = Literal["high", "medium", "low"]
# high  = score >= 0.85
# medium = score 0.50–0.84
# low   = score < 0.50
```

### FormatDetectionResult

```python
class FormatDetectionResult(BaseModel):
    detected_format: Optional[str]          # e.g., "%m/%d/%Y" or None if no format found
    parsed_sample_values: List[str]         # ISO-formatted parsed samples for display
    is_ambiguous: bool                      # True if two+ formats parse equally
    format_options: Optional[List[str]]     # Only populated when is_ambiguous=True
```

### ColumnSuggestion

```python
class ColumnSuggestion(BaseModel):
    input_column: str                                 # Detected column from uploaded file
    suggested_canonical_field: Optional[str]          # Best-match canonical field name; None if Low
    confidence: ConfidenceLevel                        # high / medium / low
    confidence_score: float                            # Raw 0.0–1.0 similarity score
    reason: Literal["name_match", "alias_match",       # How the suggestion was derived
                    "value_pattern", "prior_mapping",
                    "no_match"]
    format_detection: Optional[FormatDetectionResult]  # Only for date/decimal/boolean fields
```

### DataQualityResult

```python
class DataQualityResult(BaseModel):
    duplicate_employee_id_count: int = 0       # Rows with duplicate employee_id values
    null_required_field_counts: Dict[str, int]  # Canonical field name → null row count
    compensation_outlier_count: int = 0         # Rows with compensation < 1000 or > 10,000,000
```

### SuggestionsResponse

```python
class SuggestionsResponse(BaseModel):
    import_id: str
    suggestions: List[ColumnSuggestion]
    data_quality: DataQualityResult
    canonical_schema: List[CensusFieldDefinition]  # Full schema for UI rendering
```

---

## Updated Models (Python — `models/imports.py` changes)

### FieldMapping (no structural change, constraint tightened)

`output_column` remains `str` at the model level. The constraint that it must be a canonical field name is enforced at the router layer in `_validate_mapping()`. No model change needed.

### MappingTemplate (deprecation note)

The `MappingTemplate` entity is still persisted but the save-template UI is removed from 089. Templates saved under 087 (with free-form output_column values) are ignored by the new suggestion engine. Future cleanup of orphaned templates is out of scope.

---

## New Models (TypeScript — `services/importService.ts` additions)

```typescript
export type ConfidenceLevel = 'high' | 'medium' | 'low';

export interface CensusField {
  field_name: string;
  required: boolean;
  data_type: 'string' | 'date' | 'decimal' | 'boolean';
  description: string;
}

export interface FormatDetectionResult {
  detected_format: string | null;
  parsed_sample_values: string[];
  is_ambiguous: boolean;
  format_options: string[] | null;
}

export interface ColumnSuggestion {
  input_column: string;
  suggested_canonical_field: string | null;
  confidence: ConfidenceLevel;
  confidence_score: number;
  reason: 'name_match' | 'alias_match' | 'value_pattern' | 'prior_mapping' | 'no_match';
  format_detection: FormatDetectionResult | null;
}

export interface DataQualityResult {
  duplicate_employee_id_count: number;
  null_required_field_counts: Record<string, number>;
  compensation_outlier_count: number;
}

export interface SuggestionsResponse {
  import_id: string;
  suggestions: ColumnSuggestion[];
  data_quality: DataQualityResult;
  canonical_schema: CensusField[];
}
```

---

## Storage: No Schema Changes

This feature adds no new database tables and no new filesystem directory structures. All persistence paths are inherited from 087:

| Data | Location |
|---|---|
| Import session metadata | `workspaces/{id}/imports/{import_id}/metadata.json` |
| Field mappings | `workspaces/{id}/imports/{import_id}/mapping.json` |
| Auto-mapping fingerprint cache | `workspaces/{id}/templates/imports/_auto_{fingerprint}.json` |
| Parquet output | `workspaces/{id}/data/imports/{timestamp}_{filename}.parquet` |

The auto-mapping fingerprint file is a new file within the existing `templates/imports/` directory — no new directory needed.

---

## State Transitions (MappingSession lifecycle)

```
uploaded → [auto-suggest call] → suggestions_loaded → [analyst confirms] → mapping_in_progress → generating → completed
                                                                         ↘ failed
```

The `suggestions_loaded` state is client-side only (React state). The backend `ImportSession.status` only tracks: `uploaded → mapping_in_progress → generating → completed / failed`.
