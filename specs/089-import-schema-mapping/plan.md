# Implementation Plan: Schema-Aware Import with Predictive Field Mapping

**Branch**: `089-import-schema-mapping` | **Date**: 2026-06-03 | **Spec**: [spec.md](spec.md)

## Summary

Upgrade the data import wizard (087) so that output column names are always constrained to the simulation engine's canonical census schema (16 defined fields from `stg_census_data.sql`). Auto-suggest mappings from uploaded column names using string similarity + alias matching, detect date formats and currency formatting automatically, and show data quality warnings (nulls in required fields, duplicate employee IDs) before parquet generation.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript / React 18 (frontend)
**Primary Dependencies**: FastAPI + Pydantic v2 (backend); React 18 + Tailwind CSS v4 (frontend); pandas ≥2.0 + DuckDB 1.0.0 (data processing); `difflib` stdlib (similarity — no new dependency)
**Storage**: Filesystem JSON (session metadata, mapping JSON, auto-fingerprint cache) + Parquet files — no new directories, no database schema changes
**Testing**: pytest (backend unit + integration); no frontend test framework currently active
**Target Platform**: macOS dev + Linux server deployment (on-premises)
**Project Type**: Web service (FastAPI backend + React/Vite frontend)
**Performance Goals**: Suggestions endpoint responds in < 500ms for any census file (≤ 500MB, ≤ 20 columns)
**Constraints**: No new pip dependencies; `difflib` replaces need for `rapidfuzz`; Tailwind CSS v4 via Vite plugin (no CDN)
**Scale/Scope**: Census files up to 500MB; max ~20 input columns per file; suggestion computation is O(n_columns × n_canonical_fields) — negligible at this scale

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Event Sourcing & Immutability | ✅ Pass | No changes to `fct_yearly_events`; parquet output is immutable after generation |
| II. Modular Architecture | ✅ Pass | Two focused new modules: `census_schema.py` (<100 lines) and `suggestion_engine.py` (<150 lines); no module exceeds 600 lines |
| III. Test-First Development | ✅ Pass | Unit tests for `census_schema` and `suggestion_engine` written before implementation |
| IV. Enterprise Transparency | ✅ Pass | FR-014: all mapping decisions (auto-suggested, user-confirmed, user-overridden) logged per session |
| V. Type-Safe Configuration | ✅ Pass | `CensusFieldDefinition` is a frozen dataclass; Pydantic v2 models for all API request/response types |
| VI. Performance & Scalability | ✅ Pass | `difflib.SequenceMatcher` on ≤20 columns × 16 canonical fields takes microseconds; format detection samples 20 rows only |

## Project Structure

### Documentation (this feature)

```text
specs/089-import-schema-mapping/
├── plan.md              # This file
├── research.md          # Phase 0 — algorithm decisions
├── data-model.md        # Phase 1 — entity definitions
├── quickstart.md        # Phase 1 — developer guide
├── contracts/
│   └── api-suggestions.md   # New endpoint + modified save-mapping contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
planalign_api/
├── services/
│   ├── census_schema.py          # NEW: CensusFieldDefinition dataclass + FIELDS singleton
│   ├── suggestion_engine.py      # NEW: SuggestionEngine — similarity, format detection, DQ scan
│   ├── import_service.py         # MODIFY: generate_parquet() enforces required fields
│   └── mapping_engine.py         # MODIFY: add currency strip util + boolean alias detection
├── models/
│   └── imports.py                # MODIFY: add ColumnSuggestion, FormatDetectionResult,
│                                 #         DataQualityResult, SuggestionsResponse
└── routers/
    └── imports.py                # MODIFY: add suggestions endpoint; enforce canonical names
                                  #         in _validate_mapping()

planalign_studio/
├── services/
│   └── importService.ts          # MODIFY: add CensusField, ColumnSuggestion, SuggestionsResponse
│                                 #         types + getSuggestions() API function
└── components/imports/
    ├── FieldMappingStep.tsx       # MODIFY: replace free-text input → canonical dropdown
    │                             #         add confidence badges + format detection panel
    └── PreviewStep.tsx            # MODIFY: add data quality warnings banner

tests/
├── test_census_schema.py          # NEW: unit tests for FIELDS definitions and helpers
├── test_suggestion_engine.py      # NEW: unit tests for scoring, format detection, DQ scan
└── test_import_schema_mapping.py  # NEW: integration tests for suggestions endpoint
```

## Implementation Phases

### Phase A — Backend Core (no frontend dependency)

**A1: `census_schema.py` — canonical schema definition**

Create `planalign_api/services/census_schema.py`:
- `CensusFieldDefinition` frozen dataclass (field_name, required, data_type, description, aliases)
- `FIELDS: tuple[CensusFieldDefinition, ...]` module-level singleton — 16 entries matching `stg_census_data.sql`
- `CANONICAL_NAMES: frozenset[str]` — set of all valid output column names
- `is_canonical(name: str) -> bool` helper
- `get_required_fields() -> list[str]` helper
- `get_field(name: str) -> CensusFieldDefinition | None` helper

**A2: `suggestion_engine.py` — auto-suggestion service**

Create `planalign_api/services/suggestion_engine.py`:
- `SuggestionEngine` class (stateless, no `__init__` args)
- `suggest(detected_columns: list[DetectedColumn]) -> list[ColumnSuggestion]`:
  - For each input column: normalize name (lowercase, replace non-alphanumeric with `_`)
  - Score against each canonical field name + all aliases using `SequenceMatcher.ratio()`
  - Take highest score across all alias candidates → confidence level
  - If score ≥ 0.50, set `suggested_canonical_field` to that canonical field name
  - Detect duplicate suggestions (two input columns mapping to same canonical field) → keep highest-scoring, downgrade second to Low
- `detect_format(column: DetectedColumn, canonical_type: str) -> FormatDetectionResult | None`:
  - For `date`: try ranked format list on `sample_values`; detect ambiguity
  - For `decimal`: detect currency string patterns in `sample_values`
  - For `boolean`: check truthy/falsy alias table against `sample_values`
- `scan_data_quality(session: ImportSession, suggestions: list[ColumnSuggestion]) -> DataQualityResult`:
  - Count duplicate `employee_id` values from `preview_rows` (limited to 100 rows; note this is a sample, not full scan)
  - Count null required fields based on `DetectedColumn.null_count`
  - Count compensation outliers from `preview_rows` where `employee_gross_compensation` candidate < 1000 or > 10,000,000
- `get_auto_fingerprint(column_names: list[str]) -> str`: SHA-256 of sorted, joined column names

**A3: Add new Pydantic models to `models/imports.py`**

Add (do not remove existing models):
- `ConfidenceLevel = Literal["high", "medium", "low"]`
- `FormatDetectionResult(BaseModel)`
- `ColumnSuggestion(BaseModel)`
- `DataQualityResult(BaseModel)`
- `SuggestionsResponse(BaseModel)`

**A4: Add suggestions endpoint to `routers/imports.py`**

Add `GET /{workspace_id}/imports/{import_id}/suggestions`:
- Load session via `_check_session()`
- Instantiate `SuggestionEngine()`
- Call `suggest(session.detected_columns)` → `suggestions`
- For each suggestion with `suggested_canonical_field`, call `detect_format()` and attach result
- Call `scan_data_quality(session, suggestions)` → `data_quality`
- Return `SuggestionsResponse`

**A5: Enforce canonical names in `_validate_mapping()`**

In `routers/imports.py`, add to `_validate_mapping()`:
```python
from .services.census_schema import is_canonical
if not is_canonical(m.output_column):
    errors.append(MappingValidationError(
        field="output_column",
        input_column=m.input_column,
        message=f"Output column {m.output_column!r} is not a recognized census field. "
                f"Valid fields: {', '.join(sorted(CANONICAL_NAMES))}",
    ))
```

**A6: Enforce required fields in `import_service.py`**

In `generate_parquet()`, before calling `_engine.apply()`:
```python
from .census_schema import get_required_fields
mapped_outputs = {m.output_column for m in mappings if not m.is_excluded}
missing = [f for f in get_required_fields() if f not in mapped_outputs]
if missing:
    raise ValueError(f"Required census fields not mapped: {', '.join(missing)}")
```

**A7: Add currency strip utility to `mapping_engine.py`**

Add `_strip_currency(series: pd.Series) -> pd.Series`:
- Apply `re.sub(r'[$€£,\s]', '', val)` and parenthetical negative transform on each string value
- Called automatically in `apply()` when `output_type == "decimal"` and series dtype is `object`

**A8: Unit tests**

`tests/test_census_schema.py`:
- All 16 canonical fields present
- Required fields: exactly employee_id, employee_hire_date, employee_birth_date, employee_gross_compensation, active
- `is_canonical()` returns True for all FIELDS, False for free-form names
- `get_field()` returns correct definition

`tests/test_suggestion_engine.py`:
- High-confidence match: "EmpID" → `employee_id` (≥0.85)
- Medium-confidence match: "Staff ID" → `employee_id` (0.50–0.84)
- Low/no match: "Department Code" → None
- Duplicate resolution: two inputs both matching `employee_id` → highest wins, second → Low
- Date format detection: "%m/%d/%Y" detected from US date samples
- Date ambiguity: "01/05/2024" → ambiguous between %m/%d/%Y and %d/%m/%Y
- Currency strip: "$95,000.00" → "95000.00"
- Boolean detection: Y/N → True/False

`tests/test_import_schema_mapping.py` (integration):
- POST upload → GET suggestions → 200 with correct ColumnSuggestions
- PUT mapping with canonical names → 200
- PUT mapping with free-form name → 422 with helpful error
- POST generate without required field mapped → 422
- POST generate with all required fields → 200, parquet schema has only canonical columns

### Phase B — Frontend (depends on Phase A endpoints)

**B1: Add types and `getSuggestions()` to `importService.ts`**

Add TypeScript interfaces: `CensusField`, `ConfidenceLevel`, `FormatDetectionResult`, `ColumnSuggestion`, `DataQualityResult`, `SuggestionsResponse`

Add API function:
```typescript
export async function getSuggestions(workspaceId: string, importId: string): Promise<SuggestionsResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/imports/${importId}/suggestions`);
  return handleResponse<SuggestionsResponse>(res);
}
```

**B2: Redesign `FieldMappingStep.tsx`**

On mount: call `getSuggestions()` and store in state as `{suggestions, canonicalSchema, dataQuality}`.

Mapping row changes:
- **Replace** the free-text `<input type="text" ... output_column>` with a `<select>` dropdown:
  - Options: `<option value="">— not mapped —</option>` + required fields first (with `*` prefix in label) + optional fields
  - Selected value pre-populated from suggestion if confidence ≥ Medium
  - `disabled={m.is_excluded}`
- **Add** confidence badge (next to Source Column): `High` (green), `Medium` (amber), `Low`/no suggestion (gray)
- **Add** format detection panel (below each row, collapsed by default):
  - For date fields: show `Detected format: %m/%d/%Y` + 3 sample parsed values + "Change format" link
  - For decimal fields: show currency strip preview
  - For boolean fields: show `Y → true, N → false` mapping
  - If `is_ambiguous`: show format picker with two options
- **Remove** "Save as template" UI (templates are incompatible with canonical schema; feature superseded)
- **Keep** the transformation panel (date_parse, string_case, etc.) for manual overrides — auto-populate `date_parse.format` from `format_detection.detected_format` when format is detected

Required field blocking:
- Before calling `saveMapping()`, check that all required canonical fields have a non-empty output_column selected
- Show a validation banner listing unmapped required fields with their plain-language descriptions

**B3: Add data quality warnings to `PreviewStep.tsx`**

At the top of the preview, add a dismissible `DataQualityBanner` component:
- Shows only if `data_quality.duplicate_employee_id_count > 0` or any `null_required_field_counts` value > 0 or `compensation_outlier_count > 0`
- Content: "Data quality notice: N duplicate employee IDs (simulation will keep most-recent hire date), N rows with null [field_name]…"
- Dismissible via `×` button; does not block generation

### Phase C — Auto-fingerprint persistence

**C1: Store auto-fingerprint on successful generation**

In `import_service.py`, after successful `generate_parquet()`:
- Compute `SuggestionEngine.get_auto_fingerprint(session.detected_column_names)`
- Save `List[FieldMapping]` (with canonical output_columns) to `templates/imports/_auto_{fingerprint}.json`

**C2: Load auto-fingerprint in suggestions endpoint**

In the suggestions endpoint handler:
- After computing suggestions via `SuggestionEngine.suggest()`, check for fingerprint match
- If exact match: override all suggestions with `reason="prior_mapping"`, confidence="high"
- If partial match (≥80% columns matched): annotate matching columns with `reason="prior_mapping"`

## Complexity Tracking

No constitution violations. No complexity justifications required.

## Testing Strategy

All tests use in-memory DuckDB and filesystem temp dirs (via `pytest tmp_path`). No running server needed for integration tests — use FastAPI `TestClient`.

```bash
# Run new tests only
pytest tests/test_census_schema.py tests/test_suggestion_engine.py tests/test_import_schema_mapping.py -v

# Ensure fast suite still passes
pytest -m fast

# Full suite
pytest --cov=planalign_api --cov-report=term-missing
```
