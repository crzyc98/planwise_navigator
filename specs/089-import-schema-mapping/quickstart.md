# Developer Quickstart: Schema-Aware Import (089)

**Feature**: 089-import-schema-mapping
**Branch**: `089-import-schema-mapping`

---

## What this feature changes

The data import wizard (087) is upgraded so that:
1. The output column is always selected from a canonical schema dropdown — no free-form names
2. Auto-suggestions are generated on upload using name similarity + aliases
3. Date formats, currency values, and boolean text are detected automatically
4. Data quality warnings (nulls in required fields, duplicate employee IDs) appear before generation

---

## New files to create

```
planalign_api/services/census_schema.py      # CensusSchema singleton — canonical field definitions
planalign_api/services/suggestion_engine.py  # Auto-suggestion logic (similarity + format detection)
tests/test_census_schema.py                  # Unit tests for schema definitions
tests/test_suggestion_engine.py              # Unit tests for suggestion scoring and format detection
tests/test_import_schema_mapping.py          # Integration tests for the new suggestion endpoint
```

## Files to modify

```
planalign_api/models/imports.py             # Add: ColumnSuggestion, FormatDetectionResult,
                                            #       DataQualityResult, SuggestionsResponse
planalign_api/routers/imports.py            # Add: GET .../suggestions endpoint
                                            # Modify: _validate_mapping() — enforce canonical names
planalign_api/services/import_service.py    # Modify: generate_parquet() — enforce required fields
planalign_api/services/mapping_engine.py    # Add: currency strip, boolean detection utils
planalign_studio/services/importService.ts  # Add: CensusField, ColumnSuggestion, SuggestionsResponse types
                                            #       getSuggestions() API function
planalign_studio/components/imports/FieldMappingStep.tsx  # Replace free-text with canonical dropdown
                                                          # Add: confidence badges, format detection panel
planalign_studio/components/imports/PreviewStep.tsx       # Add: data quality warnings panel
```

---

## Running tests

```bash
# Fast unit tests — should cover census_schema and suggestion_engine
pytest tests/test_census_schema.py tests/test_suggestion_engine.py -v

# Integration tests — requires no running server (in-memory)
pytest tests/test_import_schema_mapping.py -v

# Full fast suite (must stay under 10 seconds)
pytest -m fast
```

---

## Trying the feature end-to-end

```bash
# 1. Start the studio
planalign studio

# 2. Open a workspace, go to Data Sources → Import

# 3. Upload a CSV with non-standard headers (e.g., "EmpID", "Hire Date", "Salary", "Status")

# 4. After upload, the mapping wizard auto-loads suggestions
#    - "EmpID" → employee_id (High confidence)
#    - "Hire Date" → employee_hire_date (High confidence, detected format: %m/%d/%Y)
#    - "Salary" → employee_gross_compensation (High confidence, currency strip applied)
#    - "Status" → active (High confidence, Y/N → true/false detected)

# 5. Click "Preview Mapped Data" — see data quality warnings if any duplicates or nulls

# 6. Click "Generate" — parquet written to workspace with exact canonical column names
```

---

## Verifying output parquet schema

```bash
# After generation, verify the parquet has canonical column names
duckdb :memory: "
SELECT column_name, column_type
FROM (DESCRIBE SELECT * FROM read_parquet('workspaces/<id>/data/imports/<filename>.parquet'))
ORDER BY column_name
"
# Expected columns: employee_id, employee_birth_date, employee_hire_date,
#                   employee_gross_compensation, active (+ any mapped optional columns)
```

---

## Key implementation notes

- `CensusSchema.FIELDS` is a module-level tuple of `CensusFieldDefinition` — import it where needed, never instantiate a class
- `SuggestionEngine` is stateless — instantiate per-request or as a module-level singleton
- The `_validate_mapping()` function in `routers/imports.py` is the canonical enforcement gate — call `CensusSchema.is_canonical(name)` to check each output_column
- Format detection works on the first 20 non-null values from `DetectedColumn.sample_values` (already stored in session metadata from upload) — no need to re-read the parquet
- Currency stripping in `MappingEngine` is applied automatically when output_type is `decimal` and the source series is object dtype
- Boolean alias detection injects a `date_parse`-equivalent transform into the mapping at suggestion time — the mapping engine already handles all transforms via `_apply_transform()`
