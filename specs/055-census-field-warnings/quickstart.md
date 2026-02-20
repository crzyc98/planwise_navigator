# Quickstart: Census Field Validation Warnings

**Branch**: `055-census-field-warnings` | **Date**: 2026-02-20

## What This Feature Does

Enhances the census file upload experience by showing clear, tiered warnings when expected fields are missing. Critical fields (hire date, compensation, birth date) show prominent amber warnings with impact descriptions. Optional fields show informational blue notices. Replaces the inaccurate static "Required Census Columns" info box.

## Files to Change

### Backend (Python)

| File | Change |
|------|--------|
| `planalign_api/services/file_service.py` | Add `CRITICAL_COLUMNS`, `FIELD_IMPACT_DESCRIPTIONS`; enhance `_parse_and_validate_file()` to return structured warnings; update `validate_path()` to pass warnings through |
| `planalign_api/models/files.py` | Add `StructuredWarning` model; add `structured_warnings` field to `FileUploadResponse` and `FileValidationResponse`; add `validation_warnings` to `FileValidationResponse` |
| `planalign_api/routers/files.py` | Pass structured warnings in upload and validate-path handlers |

### Frontend (TypeScript/React)

| File | Change |
|------|--------|
| `planalign_studio/services/api.ts` | Add `StructuredWarning` interface; update `FileUploadResponse` and `FileValidationResponse` types |
| `planalign_studio/components/config/DataSourcesSection.tsx` | Remove static info box; add warning panel rendering for structured warnings; handle both upload and validate-path flows |

### Tests

| File | Change |
|------|--------|
| `tests/api/test_file_validation.py` | New file — test structured warning generation, tier classification, impact descriptions, alias detection |

## Implementation Order

1. **Backend models** — Add `StructuredWarning` and update response models
2. **Backend service** — Add field definitions and enhance warning generation
3. **Backend router** — Wire structured warnings through handlers
4. **Tests** — Validate warning generation for all scenarios
5. **Frontend types** — Update TypeScript interfaces
6. **Frontend UI** — Replace static box, render tiered warning panels

## How to Test

```bash
# Backend tests
source .venv/bin/activate
pytest tests/api/test_file_validation.py -v

# Manual test: upload a CSV missing critical fields
# 1. Start studio: planalign studio
# 2. Create/open workspace
# 3. Upload a CSV with only employee_id column
# 4. Verify amber warning panel appears with impact descriptions
```

## Constitution Compliance

- **Principle I (Event Sourcing)**: Not applicable — no event store changes
- **Principle II (Modular Architecture)**: Changes are contained to file service, models, router, and one frontend component
- **Principle III (Test-First)**: New test file covers all warning scenarios
- **Principle V (Type Safety)**: Pydantic model for StructuredWarning; TypeScript interface on frontend
- **Principle VI (Performance)**: No performance impact — adds metadata to existing validation pass
