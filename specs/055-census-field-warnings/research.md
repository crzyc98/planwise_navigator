# Research: Census Field Validation Warnings

**Branch**: `055-census-field-warnings` | **Date**: 2026-02-20

## Decision 1: Backend Warning Structure

**Decision**: Enhance `_parse_and_validate_file()` to return structured warning objects instead of plain strings. Add a new `CRITICAL_COLUMNS` constant alongside existing `RECOMMENDED_COLUMNS`. Each warning includes field name, severity tier, impact description, and optional alias.

**Rationale**: The current backend returns flat strings like `"Recommended column missing: {col}"` with no severity or impact metadata. The frontend needs structured data to render tiered warnings with impact descriptions. Changing the internal return format is the minimal change — the API response model wraps it.

**Alternatives considered**:
- Keep flat strings and parse them in the frontend → Fragile, duplicates domain knowledge
- Add a separate validation endpoint → Unnecessary; validation already happens on upload

## Decision 2: API Response Evolution

**Decision**: Add a new `structured_warnings` field to `FileUploadResponse` containing typed warning objects. Keep the existing `validation_warnings: List[str]` for backward compatibility (populated from structured warnings). Add `validation_warnings` to `FileValidationResponse` (currently missing).

**Rationale**: The existing `validation_warnings` field is a `List[str]`. Changing its type would break the API contract. Adding a parallel `structured_warnings` field provides rich data while maintaining backward compatibility. The validate-path endpoint currently drops warnings entirely — this is a bug that should be fixed.

**Alternatives considered**:
- Replace `validation_warnings` type from `List[str]` to `List[WarningObject]` → Breaking change
- Only use the new field and deprecate old → Two-step migration adds complexity for no benefit now

## Decision 3: Frontend Warning Display

**Decision**: Replace the static "Required Census Columns" info box and the single-line warning text with a structured warning panel component. Use amber/orange for critical warnings, blue for optional notices. Display within the existing upload result area.

**Rationale**: Per clarification, the static info box lists inaccurate columns and should be removed. The new warning panel replaces both the static box and the current `setUploadMessage()` warning display, providing accurate context-specific feedback.

**Alternatives considered**:
- Modal dialog for warnings → Interrupts workflow, spec says warnings should be passive
- Toast/notification → Too transient, spec requires warnings visible without scrolling

## Decision 4: Field Impact Descriptions

**Decision**: Define impact descriptions as a constant map in the backend (`FIELD_IMPACT_DESCRIPTIONS`), keyed by column name. Each entry includes severity tier and human-readable impact text. This is the single source of truth — the frontend renders what the backend provides.

**Rationale**: Centralizing impact descriptions in the backend ensures consistency across upload and validate-path flows. The frontend should not duplicate this domain knowledge.

**Alternatives considered**:
- Define impacts in the frontend → Duplicates domain logic, goes out of sync
- Store in configuration/YAML → Over-engineering for a static mapping

## Decision 5: Validate-Path Endpoint Gap

**Decision**: Add `validation_warnings` and `structured_warnings` fields to `FileValidationResponse`. The validate-path handler already calls `_parse_and_validate_file()` which returns warnings, but currently discards them.

**Rationale**: FR-006 states warnings apply to both upload and validate flows. The `validate_path()` method in `FileService` already gets warnings from `_parse_and_validate_file()` but the handler in `files.py` doesn't pass them through.

## Key File Inventory

| File | Role | Change Scope |
|------|------|-------------|
| `planalign_api/services/file_service.py` | Warning generation | Add `CRITICAL_COLUMNS`, `FIELD_IMPACT_DESCRIPTIONS`, enhance `_parse_and_validate_file()` return, update `validate_path()` |
| `planalign_api/models/files.py` | API response models | Add `StructuredWarning` model, add `structured_warnings` to both response types, add `validation_warnings` to `FileValidationResponse` |
| `planalign_api/routers/files.py` | API route handlers | Pass structured warnings through in upload and validate-path handlers |
| `planalign_studio/services/api.ts` | Frontend API types | Add `StructuredWarning` interface, update `FileUploadResponse` and `FileValidationResponse` types |
| `planalign_studio/components/config/DataSourcesSection.tsx` | Upload UI | Remove static info box, add warning panel rendering, handle structured warnings |
| `tests/api/test_file_validation.py` | New test file | Test structured warning generation, tier classification, impact descriptions |
