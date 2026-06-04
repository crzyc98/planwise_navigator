# Tasks: Schema-Aware Import with Predictive Field Mapping

**Input**: Design documents from `/specs/089-import-schema-mapping/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in same batch)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup

**Purpose**: No new project structure needed — new files slot into existing `planalign_api/services/`, `planalign_api/models/`, `planalign_api/routers/`, and `planalign_studio/` directories.

- [x] T001 Verify `difflib` is available (stdlib, no pip install needed) and confirm `pandas`, `duckdb` versions in `pyproject.toml` meet requirements (pandas ≥2.0, DuckDB 1.0.0)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The canonical schema definition and new Pydantic/TypeScript models are required by every user story. Nothing else can start until these exist.

**⚠️ CRITICAL**: All user story work depends on T002–T006 being complete.

- [x] T002 Create `planalign_api/services/census_schema.py` — define `CensusFieldDefinition` frozen dataclass (fields: `field_name: str`, `required: bool`, `data_type: Literal["string","date","decimal","boolean"]`, `description: str`, `aliases: tuple[str,...]`) and the module-level `FIELDS: tuple[CensusFieldDefinition, ...]` singleton with all 16 canonical census entries from `data-model.md` (employee_id through eligibility_entry_date); also add `CANONICAL_NAMES: frozenset[str]`, `is_canonical(name: str) -> bool`, `get_required_fields() -> list[str]`, and `get_field(name: str) -> CensusFieldDefinition | None` helpers

- [x] T003 [P] Add new Pydantic models to `planalign_api/models/imports.py` — append (do not remove any existing models): `ConfidenceLevel = Literal["high", "medium", "low"]`; `FormatDetectionResult(BaseModel)` with fields `detected_format: Optional[str]`, `parsed_sample_values: List[str]`, `is_ambiguous: bool`, `format_options: Optional[List[str]]`; `ColumnSuggestion(BaseModel)` with fields `input_column: str`, `suggested_canonical_field: Optional[str]`, `confidence: ConfidenceLevel`, `confidence_score: float`, `reason: Literal["name_match","alias_match","value_pattern","prior_mapping","no_match"]`, `format_detection: Optional[FormatDetectionResult]`; `DataQualityResult(BaseModel)` with fields `duplicate_employee_id_count: int = 0`, `null_required_field_counts: Dict[str, int] = Field(default_factory=dict)`, `compensation_outlier_count: int = 0`; `SuggestionsResponse(BaseModel)` with fields `import_id: str`, `suggestions: List[ColumnSuggestion]`, `data_quality: DataQualityResult`, `canonical_schema: List[dict]`

- [x] T004 [P] Add new TypeScript types to `planalign_studio/services/importService.ts` — append after existing interfaces: `export type ConfidenceLevel = 'high' | 'medium' | 'low'`; `export interface CensusField { field_name: string; required: boolean; data_type: 'string' | 'date' | 'decimal' | 'boolean'; description: string; }`; `export interface FormatDetectionResult { detected_format: string | null; parsed_sample_values: string[]; is_ambiguous: boolean; format_options: string[] | null; }`; `export interface ColumnSuggestion { input_column: string; suggested_canonical_field: string | null; confidence: ConfidenceLevel; confidence_score: number; reason: 'name_match' | 'alias_match' | 'value_pattern' | 'prior_mapping' | 'no_match'; format_detection: FormatDetectionResult | null; }`; `export interface DataQualityResult { duplicate_employee_id_count: number; null_required_field_counts: Record<string, number>; compensation_outlier_count: number; }`; `export interface SuggestionsResponse { import_id: string; suggestions: ColumnSuggestion[]; data_quality: DataQualityResult; canonical_schema: CensusField[]; }`

- [x] T005 [P] Write unit tests for `census_schema.py` in `tests/test_census_schema.py` — use `pytest`, mark `@pytest.mark.fast`; test: (a) `len(FIELDS) == 16`; (b) exactly 5 required fields: employee_id, employee_hire_date, employee_birth_date, employee_gross_compensation, active; (c) `is_canonical("employee_id")` returns True; `is_canonical("salary")` returns False; `is_canonical("EmpID")` returns False; (d) `get_field("employee_hire_date")` returns a `CensusFieldDefinition` with `required=True` and `data_type="date"`; (e) `get_required_fields()` returns a list of exactly 5 field names; (f) `CANONICAL_NAMES` is a frozenset containing all 16 field_name values

- [x] T006 Run `pytest tests/test_census_schema.py -v` and confirm all pass before proceeding

**Checkpoint**: Census schema defined, models ready — user story work can now begin.

---

## Phase 3: User Story 1 — Auto-Mapped Census Upload (Priority: P1) 🎯 MVP

**Goal**: Upload a CSV/Excel with non-standard column names; the system auto-suggests canonical field mappings with confidence levels; the mapping wizard shows a canonical dropdown pre-populated from suggestions.

**Independent Test**: Upload a CSV with headers "EmpID", "DOB", "Hire Date", "Annual Salary", "Active". Call `GET .../suggestions`. Verify response contains: `employee_id` (High), `employee_birth_date` (High), `employee_hire_date` (High), `employee_gross_compensation` (High), `active` (High). Verify frontend dropdown for each row is pre-selected to the correct canonical field.

- [x] T007 Create `planalign_api/services/suggestion_engine.py` with `SuggestionEngine` class — implement `suggest(detected_columns: list[DetectedColumn]) -> list[ColumnSuggestion]`: for each input column, normalize name (lowercase, replace `[^a-z0-9]` with `_`); score against each canonical field's `field_name` and all aliases using `difflib.SequenceMatcher(None, normalized_input, normalized_candidate).ratio()`; take max score across all candidates; map score to confidence (≥0.85 → "high", 0.50–0.84 → "medium", <0.50 → "low"); if score ≥0.50 set `suggested_canonical_field` else set to None and reason to "no_match"; handle duplicate canonical targets — if two input columns both score ≥0.50 for same canonical field, keep the higher-scoring one and downgrade the other to Low/no_match; also implement `get_auto_fingerprint(column_names: list[str]) -> str` using `hashlib.sha256`

- [x] T008 [P] Write unit tests for suggestion engine (core matching only) in `tests/test_suggestion_engine.py` — mark `@pytest.mark.fast`; test: (a) "EmpID" → `employee_id` confidence High; (b) "Staff ID" → `employee_id` confidence Medium or Low (score between 0.4–0.7); (c) "Department Code" → no_match (suggested_canonical_field is None); (d) two inputs both matching `employee_id` — higher scorer wins, lower is no_match; (e) alias match — "Hire Date" scores ≥0.85 against employee_hire_date alias; (f) `get_auto_fingerprint(["A","B"])` returns a 64-char hex string; same inputs always return same fingerprint; different inputs return different fingerprints

- [x] T009 Add `GET /{workspace_id}/imports/{import_id}/suggestions` endpoint to `planalign_api/routers/imports.py` — load session via `_check_session()`; instantiate `SuggestionEngine()`; call `engine.suggest(session.detected_columns)` → suggestions list; for each suggestion, set `format_detection=None` (format detection added in Phase 5); call a stub `DataQualityResult()` (populated in Phase 7); serialize `FIELDS` as list of dicts for `canonical_schema`; return `SuggestionsResponse`; handle 404 (workspace/session not found)

- [x] T010 [P] Add `getSuggestions()` API function to `planalign_studio/services/importService.ts` — `export async function getSuggestions(workspaceId: string, importId: string): Promise<SuggestionsResponse> { const res = await fetch(\`\${API_BASE}/api/workspaces/\${workspaceId}/imports/\${importId}/suggestions\`); return handleResponse<SuggestionsResponse>(res); }`

- [x] T011 Redesign `planalign_studio/components/imports/FieldMappingStep.tsx` — add state: `suggestions: ColumnSuggestion[]`, `canonicalSchema: CensusField[]`, `isLoadingSuggestions: boolean`; on mount call `getSuggestions(workspaceId, session.import_id)` and store results; initialize mapping rows from suggestions: for each detected column, find matching suggestion and pre-select `suggested_canonical_field` if confidence is "high" or "medium" (pre-select but highlight "low" suggestions in amber); replace the free-text `<input type="text" ... output_column>` with a `<select>` dropdown: first option is `<option value="">— not mapped —</option>`, then required canonical fields (sorted, each with `* ` prefix in label), then optional canonical fields; add confidence badge per row: green chip for "high", amber for "medium", gray for "low" or no suggestion; keep the "Exclude" checkbox and transforms panel (these are unchanged from 087); remove the "Save as template" UI block and `showSaveTemplate` state entirely

- [x] T012 Run the studio (`planalign studio`) and manually test the happy path: upload a CSV with "EmpID,DOB,Hire Date,Annual Salary,Active" headers; confirm dropdown is pre-populated correctly with High-confidence suggestions

---

## Phase 4: User Story 2 — Required Field Validation (Priority: P1)

**Goal**: Mapping wizard blocks generation when any required canonical field is unmapped; save-mapping endpoint rejects non-canonical output column names; generate endpoint rejects if required fields are missing.

**Independent Test**: (a) PUT mapping with `output_column: "my_custom_field"` → 422 with message naming the invalid field. (b) Attempt to save mappings with `employee_hire_date` unmapped → UI shows blocking banner listing the unmapped required field and its description. (c) POST generate with required field missing from mapping → 422.

- [x] T013 Update `_validate_mapping()` in `planalign_api/routers/imports.py` — after the existing duplicate-output-column check, add: `from ..services.census_schema import is_canonical, CANONICAL_NAMES` (move import to top of file); for each non-excluded mapping, if `not is_canonical(m.output_column)` append `MappingValidationError(field="output_column", input_column=m.input_column, message=f"Output column {m.output_column!r} is not a recognized census field. Valid fields: {', '.join(sorted(CANONICAL_NAMES))}")` — keep all existing validations unchanged

- [x] T014 [P] Update `generate_parquet()` in `planalign_api/services/import_service.py` — before calling `self._engine.apply(df, mappings)`, add: `from .census_schema import get_required_fields`; `mapped_outputs = {m.output_column for m in mappings if not m.is_excluded}`; `missing = [f for f in get_required_fields() if f not in mapped_outputs]`; `if missing: raise ValueError(f"Required census fields not mapped: {', '.join(missing)}")` — place this check after the existing `if not mappings: raise ValueError(...)` guard

- [x] T015 Add required-field blocking to `planalign_studio/components/imports/FieldMappingStep.tsx` — in `handleSave()`, before calling `saveMapping()`: compute `mappedCanonicalFields = new Set(mappings.filter(m => !m.is_excluded && m.output_column).map(m => m.output_column))`; `const unmappedRequired = canonicalSchema.filter(f => f.required && !mappedCanonicalFields.has(f.field_name))`; if `unmappedRequired.length > 0`, set a `requiredFieldError` state and return early (do not call API); display a red error banner listing each unmapped required field with its `description` property; also show a tooltip on hover over each required-field `*` label using the field's `description` from `canonicalSchema`

- [x] T016 [P] Write integration tests covering US1 + US2 in `tests/test_import_schema_mapping.py` — use FastAPI `TestClient`; `@pytest.mark.fast` where in-memory only; test: (a) GET suggestions on a valid session returns 200 with `suggestions` list and `canonical_schema` list; (b) GET suggestions on unknown session returns 404; (c) PUT mapping with canonical field names returns 200; (d) PUT mapping with non-canonical `output_column` returns 422 with error message containing the invalid field name; (e) POST generate after mapping without all required fields returns 422 with message listing missing fields

- [x] T017 Run `pytest tests/test_import_schema_mapping.py -v` and verify T016 cases all pass

---

## Phase 5: User Story 3 — Data Formatting Guidance (Priority: P1)

**Goal**: Date formats detected from sample values; currency strings stripped automatically; boolean text patterns identified. Format detection result shown in the mapping wizard so analysts see parsed samples before committing.

**Independent Test**: Upload a CSV where "Hire Date" contains "03/15/2018" (US format), "Salary" contains "$95,000.00", and "Active" contains "Y"/"N". Call `GET .../suggestions`. Verify: `employee_hire_date` suggestion has `format_detection.detected_format = "%m/%d/%Y"` with 3 parsed ISO samples. `employee_gross_compensation` suggestion has `format_detection.detected_format = "currency_string"` with stripped numeric samples. `active` suggestion has `format_detection` showing `Y → true, N → false` alias map.

- [x] T018 Add `detect_format(column: DetectedColumn, canonical_field: CensusFieldDefinition) -> Optional[FormatDetectionResult]` to `planalign_api/services/suggestion_engine.py` — for `data_type == "date"`: try ranked format list `["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y%m%d"]` against `column.sample_values` using `pd.to_datetime(errors='coerce')`; pick format with fewest NaT on first 20 non-null samples; if two+ formats tie → set `is_ambiguous=True` and populate `format_options`; return `FormatDetectionResult` with `detected_format`, `parsed_sample_values` (ISO 8601 strings), `is_ambiguous`; for `data_type == "decimal"`: check if sample_values contain `$`, `€`, `£`, or `,` — if yes, strip with `re.sub(r'[$€£,\s]', '', v)` and handle `(123.45)` as `-123.45`; return `FormatDetectionResult(detected_format="currency_string", parsed_sample_values=[stripped values], is_ambiguous=False, format_options=None)`; for `data_type == "boolean"`: TRUTHY = `{"y","yes","true","1","active","enrolled","eligible","employed"}`; FALSY = `{"n","no","false","0","inactive","terminated","separated","ineligible"}`; check all sample_values (lowercased) fall in TRUTHY ∪ FALSY; if ≥95% match, return `FormatDetectionResult(detected_format="boolean_alias", parsed_sample_values=["true"/"false" mapping shown], is_ambiguous=False)`

- [x] T019 [P] Add currency-stripping utility to `planalign_api/services/mapping_engine.py` — add `_strip_currency(series: pd.Series) -> pd.Series`: apply `re.sub(r'[$€£,\s]', '', str(v))` to each element; handle parenthetical negatives via `re.match(r'^\((.+)\)$', v)` → prepend `-`; call `_strip_currency(col)` automatically in `MappingEngine.apply()` when `mapping.output_type == "decimal"` and `col.dtype == object` (i.e., source values are strings — already the case when `dtype=object` pandas read is used)

- [x] T020 Update `GET .../suggestions` endpoint in `planalign_api/routers/imports.py` — after calling `engine.suggest()`, for each suggestion where `suggested_canonical_field is not None`: get the `CensusFieldDefinition` via `get_field(suggestion.suggested_canonical_field)`; call `engine.detect_format(column, field_def)`; attach result to `suggestion.format_detection`

- [x] T021 [P] Add format detection tests to `tests/test_suggestion_engine.py` — `@pytest.mark.fast`; create mock `DetectedColumn` instances with `sample_values`; test: (a) US date "03/15/2018" → detected_format "%m/%d/%Y", parsed_sample has "2018-03-15"; (b) ISO date "2018-03-15" → detected_format "%Y-%m-%d"; (c) ambiguous "01/05/2024" → is_ambiguous=True, two format_options; (d) "$95,000.00" → detected_format "currency_string", parsed_sample "95000.00"; (e) "(1500.00)" → currency strip → "-1500.00"; (f) Y/N sample → detected_format "boolean_alias"; (g) mixed unrecognized values → returns None

- [x] T022 Add format detection panel to `planalign_studio/components/imports/FieldMappingStep.tsx` — below each mapping row (using existing expand/collapse mechanism or a new inline panel), when `suggestion.format_detection` is non-null: show a gray info box; for `detected_format` starting with `%`: show `Detected date format: {detected_format}` + 3 sample parsed values; if `is_ambiguous`: show two radio buttons with the format_options labeled with parsed samples, require analyst to pick one before "Save"; for `"currency_string"`: show `Currency symbols and commas will be stripped automatically` + 3 numeric samples; for `"boolean_alias"`: show `Y → true, N → false` (or detected mapping); when format is detected, auto-inject a `date_parse` transform with `format: detected_format` into the mapping's `transformations` array so the existing `MappingEngine` handles it at generation time

- [x] T023 Run `planalign studio` and manually verify: date column shows format panel with correct parsed samples; currency column shows strip preview; boolean column shows alias map; ambiguous date presents format picker

---

## Phase 6: User Story 4 — Predictive Mapping from Prior Imports (Priority: P2)

**Goal**: After a successful import, the column mapping is fingerprinted and cached. On the next upload with the same column headers, all mappings are auto-applied with "Previously mapped" confidence — zero manual steps needed.

**Independent Test**: Complete a full import (upload → map → generate). Upload the same CSV a second time. Call `GET .../suggestions`. Verify all `ColumnSuggestion` entries have `reason = "prior_mapping"` and `confidence = "high"`.

- [x] T024 Update `generate_parquet()` in `planalign_api/services/import_service.py` — after successful parquet generation (after `self.save_parquet_record()`), add: `from .suggestion_engine import SuggestionEngine`; `fingerprint = SuggestionEngine.get_auto_fingerprint([c.name for c in session.detected_columns])`; `auto_path = self._templates_path(workspace_id) / f"_auto_{fingerprint}.json"`; `auto_path.parent.mkdir(parents=True, exist_ok=True)`; `auto_path.write_text(json.dumps([m.model_dump(mode="json") for m in mappings], indent=2))`

- [x] T025 Update `GET .../suggestions` endpoint handler in `planalign_api/routers/imports.py` — after computing suggestions from `engine.suggest()`, compute `fingerprint = engine.get_auto_fingerprint([c.name for c in session.detected_columns])`; check `service._templates_path(workspace_id) / f"_auto_{fingerprint}.json"` exists; if yes: load stored mappings; for each stored mapping, find the corresponding suggestion by `input_column` and override: set `confidence="high"`, `confidence_score=1.0`, `reason="prior_mapping"`, `suggested_canonical_field` = stored `output_column`; if the fingerprint file doesn't exist, proceed with normal suggestions unchanged

- [x] T026 [P] Add prior-mapping integration tests to `tests/test_import_schema_mapping.py` — test: (a) after successful generate, fingerprint file exists at `_auto_{fingerprint}.json`; (b) second upload with same column headers + GET suggestions → all suggestions have `reason="prior_mapping"`; (c) second upload with different column headers → normal suggestions (no prior_mapping)

---

## Phase 7: User Story 5 — Mapped Preview with Data Quality Warnings (Priority: P2)

**Goal**: Before generating, analysts see a summary of data quality issues: duplicate employee IDs (with deduplication rule explained), nulls in required fields, compensation outliers. Issues are shown as a dismissible banner on the preview step.

**Independent Test**: Upload a CSV with 3 duplicate employee IDs and 2 null hire dates. After mapping, the suggestions response `data_quality` shows `duplicate_employee_id_count: 3` and `null_required_field_counts: {"employee_hire_date": 2}`. In the frontend, a data quality banner is visible on the preview step showing both issues.

- [x] T027 Add `scan_data_quality(session: ImportSession, suggestions: list[ColumnSuggestion]) -> DataQualityResult` to `planalign_api/services/suggestion_engine.py` — determine which input column maps to `employee_id` and `employee_gross_compensation` from the suggestions list; for `duplicate_employee_id_count`: find the employee_id candidate column name; count duplicate non-null values in `session.preview_rows` (note: preview is 100 rows max — result is a sample, not full-file count); for `null_required_field_counts`: for each required canonical field, find its mapped input column via suggestions; look up `DetectedColumn.null_count` for that column from `session.detected_columns` (this is full-file null count from upload); if the required field has no suggestion, set count to the total row count (entire column is unmapped); for `compensation_outlier_count`: find employee_gross_compensation candidate column; scan `session.preview_rows` for values that after currency stripping parse to float < 1000 or > 10_000_000; return `DataQualityResult`

- [x] T028 Update `GET .../suggestions` endpoint in `planalign_api/routers/imports.py` — replace the stub `DataQualityResult()` with a real call: `data_quality = engine.scan_data_quality(session, suggestions)` and include in `SuggestionsResponse`

- [x] T029 [P] Add data quality scan tests to `tests/test_suggestion_engine.py` — `@pytest.mark.fast`; construct mock `ImportSession` with `preview_rows` containing 3 rows with duplicate employee IDs and `detected_columns` with null_count=2 for hire date column; call `scan_data_quality()`; assert `duplicate_employee_id_count == 3`; assert `null_required_field_counts["employee_hire_date"] == 2`; assert `compensation_outlier_count == 0` (or correct count if outlier rows added)

- [x] T030 Add `DataQualityBanner` display to `planalign_studio/components/imports/PreviewStep.tsx` — accept `dataQuality: DataQualityResult | null` as a prop (pass it from the parent `ImportWizard` component which already calls `getSuggestions`); render the banner only when `duplicate_employee_id_count > 0` or any value in `null_required_field_counts > 0` or `compensation_outlier_count > 0`; content: amber warning box with `×` dismiss button; show: "N duplicate employee IDs detected — the simulation engine will automatically keep the row with the most recent hire date" (if duplicates); "N rows have null {field description} — required field" (for each required field with nulls > 0); "N rows have unusual compensation values (< $1,000 or > $10M)" (if outliers); does NOT block the Generate button

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Wire up the passing of `dataQuality` through the wizard, run the full test suite, verify end-to-end, and clean up any remaining 087 template UI references.

- [x] T031 Thread `dataQuality` from suggestions response through the import wizard — in whichever parent component manages wizard step state (likely `DataSourcesSection.tsx` or a wizard container), store `suggestionsData: SuggestionsResponse | null` in state; pass `suggestionsData?.data_quality ?? null` as the `dataQuality` prop to `PreviewStep`; ensure `getSuggestions()` is called once after upload and the result stored (not re-called on every step render)

- [x] T032 [P] Audit and remove 087 template-save UI references — in `FieldMappingStep.tsx`: confirm `showSaveTemplate` state, `templateName`, `templateDesc`, `isSavingTemplate`, the `handleSaveTemplate` function, and the "Save as template" `<div>` block are all removed (done in T011; verify nothing re-introduced); confirm `listTemplates`, `saveTemplate`, `applyTemplate` imports are removed from `FieldMappingStep.tsx` (these can stay in `importService.ts` for backward compatibility but must not be called from the new wizard)

- [x] T033 Run the full fast test suite: `pytest -m fast` — all tests must pass in < 10 seconds; fix any failures before proceeding

- [x] T034 [P] Run `pytest tests/test_census_schema.py tests/test_suggestion_engine.py tests/test_import_schema_mapping.py -v` — confirm all integration tests pass with no skips

- [x] T035 End-to-end smoke test in `planalign studio` — (a) upload a CSV with "EmpID, DOB, Hire Date, Annual Salary, Active, Department" headers where "Hire Date" is MM/DD/YYYY format, "Annual Salary" has `$` and commas, "Active" is Y/N; (b) verify: all 5 canonical fields auto-populated with High confidence; date format panel shows `%m/%d/%Y`; currency panel shows strip preview; boolean panel shows Y/N → true/false; "Department" has no suggestion (Low/no_match); required-field block triggers if "Department" mapped to a canonical field and a required field cleared; (c) click through to preview, verify data quality banner absent (if no duplicates/nulls); (d) generate parquet; (e) run `duckdb :memory: "SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet('<path>'))"` and verify only canonical column names appear

---

## Dependency Graph

```
T001 (verify deps)
  └── T002 (census_schema.py)
        ├── T003 (Pydantic models)     ──┐
        ├── T004 (TS types)            ──┤ All unblocked after T002
        └── T005 (schema tests)        ──┘
              └── T006 (run schema tests) ← gate before US work

T006 ──────────────────────────────────────────────────────────
  Phase 3 (US1):                        Phase 5 (US3):
  T007 (suggestion engine core)         T018 (detect_format — extends T007)
  T008 (suggestion tests)     [P]       T019 (currency strip) [P]
  T009 (suggestions endpoint)           T020 (wire format detection into endpoint)
  T010 (getSuggestions TS)    [P]       T021 (format tests)   [P]
  T011 (FieldMappingStep UI)            T022 (format panel UI)
  T012 (manual smoke test)              T023 (manual format test)

  Phase 4 (US2):                        Phase 6 (US4):
  T013 (canonical validation)           T024 (save fingerprint on generate)
  T014 (required field guard) [P]       T025 (load fingerprint in suggestions)
  T015 (UI required blocking)           T026 (fingerprint tests)   [P]
  T016 (integration tests)    [P]
  T017 (run integration tests)

  Phase 7 (US5):
  T027 (scan_data_quality)
  T028 (wire DQ into endpoint)
  T029 (DQ scan tests) [P]
  T030 (DataQualityBanner UI)

T030 → T031 (thread dataQuality)
T031 → T032 (cleanup) [P] → T033 (full suite) → T034 [P] → T035 (e2e)
```

## Parallel Execution Examples

**After T006**, these groups can proceed in parallel:

| Group A (Backend US1) | Group B (Models/Types) | Group C (US2 enforcement) |
|---|---|---|
| T007 suggestion engine | — | T013 router validation |
| T009 endpoint | — | T014 service guard |
| — | T008 unit tests | T016 integration tests |

**After Phase 3 (T012)**:
| Group D (US3 backend) | Group E (US4) | Group F (US5) |
|---|---|---|
| T018 detect_format | T024 save fingerprint | T027 scan_data_quality |
| T019 currency strip | T025 load fingerprint | T028 wire DQ |
| T021 format tests | T026 fingerprint tests | T029 DQ tests |

## Implementation Strategy

**MVP** (deliver US1 + US2 first — covers the core complaint):
→ T001 → T002 → T003–T005 in parallel → T006 → T007–T011 → T012 (smoke test US1)
→ T013–T015 in parallel → T016 → T017 (US2 validated)

**Increment 2** (add formatting guidance — US3):
→ T018–T022 in parallel → T023

**Increment 3** (add persistence + DQ warnings — US4 + US5):
→ T024–T026 in parallel with T027–T029 → T030–T031

**Polish**:
→ T032–T035

Total tasks: **35**
Tasks per story: US1=6, US2=5, US3=6, US4=3, US5=4, Foundational=5, Setup=1, Polish=5
Parallel opportunities: 16 tasks marked [P]
