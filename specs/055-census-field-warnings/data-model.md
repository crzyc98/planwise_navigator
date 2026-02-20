# Data Model: Census Field Validation Warnings

**Branch**: `055-census-field-warnings` | **Date**: 2026-02-20

## Entities

### StructuredWarning

Represents a single validation finding about a census file column.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `field_name` | string | yes | The expected census column name (e.g., `employee_birth_date`) |
| `severity` | enum: `critical` \| `optional` | yes | Severity tier based on simulation impact |
| `warning_type` | enum: `missing` \| `alias_found` | yes | Whether the field is missing or an alias was detected |
| `impact_description` | string | yes | Human-readable explanation of simulation impact |
| `detected_alias` | string \| null | no | The alias column name found in the file, if any |
| `suggested_action` | string | yes | What the user should do (e.g., "Add this column" or "Rename to X") |

### FieldDefinition (internal constant, not API-exposed)

Defines the expected columns with their metadata.

| Field | Type | Description |
|-------|------|-------------|
| `column_name` | string | Expected column name |
| `severity` | `critical` \| `optional` | Tier classification |
| `impact_description` | string | What breaks without this field |
| `default_behavior` | string \| null | What default the simulation uses (optional fields only) |

## Field Classification

### Critical Fields

| Column Name | Impact Description |
|------------|-------------------|
| `employee_hire_date` | Tenure calculations, new hire identification, turnover modeling, and annualized compensation will not work correctly |
| `employee_gross_compensation` | Compensation-based calculations, merit raises, promotion modeling, HCE determination, and contribution calculations will use defaults or produce inaccurate results |
| `employee_birth_date` | Age-based calculations, age band segmentation, HCE determination, and retirement eligibility will not work correctly |

### Optional Fields

| Column Name | Impact Description | Default Behavior |
|------------|-------------------|-----------------|
| `employee_termination_date` | Terminated employee identification may be incomplete | Active status inferred from other fields |
| `active` | Employee active/inactive filtering may be unavailable | All employees treated as active |

## Relationships

- `StructuredWarning` is generated per missing/aliased column during `_parse_and_validate_file()`
- Multiple `StructuredWarning` objects are collected into `FileUploadResponse.structured_warnings` and `FileValidationResponse.structured_warnings`
- The flat `validation_warnings: List[str]` is derived from `structured_warnings` for backward compatibility
- `FieldDefinition` is a static constant map — not persisted, used at validation time only

## State Transitions

None — warnings are stateless. They are computed fresh on each upload or validate-path call and returned in the response. No persistence required.
