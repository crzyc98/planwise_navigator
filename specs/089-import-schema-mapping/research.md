# Research: Schema-Aware Import with Predictive Field Mapping

**Feature**: 089-import-schema-mapping
**Date**: 2026-06-03

---

## 1. String Similarity Algorithm for Auto-Suggestion

**Decision**: Use Python stdlib `difflib.SequenceMatcher.ratio()` against canonical field names + all known aliases, taking the highest score across all alias candidates.

**Rationale**: `difflib` is already available (stdlib, no new dependency). `SequenceMatcher.ratio()` returns 0.0–1.0 and handles partial name overlaps well (e.g., "Annual Salary" vs "employee_gross_compensation" scores low, but "Annual Salary" vs alias "annual_salary" scores 1.0). The alias list is where the intelligence lives — not the algorithm.

**Confidence mapping** (clarified in spec):
- Score ≥ 0.85 → **High** (shown in green; no verification nudge)
- Score 0.50–0.84 → **Medium** (shown in amber; analyst should verify)
- Score < 0.50 → **Low** (shown in red; analyst must manually select)

**Implementation note**: Normalize input column names before comparison — lowercase, replace non-alphanumeric with underscore. Compare against canonical field name AND all aliases. Take the max score across all candidates.

**Alternatives considered**:
- `rapidfuzz` (C extension, much faster): unnecessary — import files have at most ~20 columns; `difflib` processes this in microseconds
- Token-set ratio (FuzzyWuzzy): overkill for this domain

---

## 2. Date Format Detection

**Decision**: Try a ranked list of known format strings with `pd.to_datetime(errors='coerce')`. Pick the format with the fewest NaT (null) results on a sample of 20 non-null values. Flag as ambiguous if two or more formats parse equally well.

**Ranked format list** (order matters for ambiguity resolution):
1. `%Y-%m-%d` — ISO 8601 (unambiguous)
2. `%Y/%m/%d` — ISO variant
3. `%m/%d/%Y` — US format
4. `%d/%m/%Y` — European format
5. `%m-%d-%Y` — US with dashes
6. `%d-%m-%Y` — European with dashes
7. `%Y%m%d` — compact numeric
8. Excel serial date (integer days since 1899-12-30) — detect if sample values are all integers in range 1–100000

**Ambiguity rule**: If formats 3 and 4 both parse with 0 NaT (e.g., "01/05/2024" could be Jan 5 or May 1), flag as ambiguous and show both interpretations with parsed sample values for analyst confirmation.

**Alternatives considered**: `dateutil.parser.parse()` (too permissive — parses almost anything, making ambiguity detection impossible)

---

## 3. Decimal / Currency Stripping

**Decision**: Pre-process string values before numeric conversion by stripping: `$`, `€`, `£`, commas (`,`), leading/trailing whitespace, and parenthetical negatives `(123.45)` → `-123.45`.

**Implementation**: Regex `re.sub(r'[$€£,\s]', '', val)` plus parenthetical negative detection `re.match(r'^\((.+)\)$', val)`.

**Applied when**: Input column is mapped to a `decimal` field AND `inferred_type` is `string` (meaning pandas couldn't auto-parse it as numeric). If `inferred_type` is already `decimal` or `integer`, no stripping needed.

---

## 4. Boolean Text Pattern Detection

**Decision**: Server-side pattern detection against a curated alias table. Map detected values to Python `bool` at generation time.

**Canonical truthy/falsy aliases**:
| Truthy | Falsy |
|--------|-------|
| Y, Yes, True, 1, Active, Enrolled, Eligible, Employed | N, No, False, 0, Inactive, Terminated, Separated, Ineligible |

**Detection logic**: Sample 20 non-null values, normalize to lowercase, check that all values fall within the union of truthy + falsy. If >95% match, report detected mapping. If mixed/unrecognized, flag as Low confidence and require analyst to map manually.

**UX**: Show the detected alias map in the format panel (e.g., "Y → true, N → false") so analysts can verify at a glance.

---

## 5. Prior-Mapping Persistence (Repeat Uploads)

**Decision**: After successful parquet generation, serialize the complete `List[FieldMapping]` (canonical output columns + transforms) keyed by a fingerprint of the input column header set. Store in the workspace's templates directory as a system-managed "last successful mapping" file (distinct from analyst-named templates).

**Fingerprint**: `sha256(sorted(input_column_names).join(","))` → hex string → stored as `_auto_{fingerprint}.json` in `templates/imports/`.

**Match rule**: On new upload, compute fingerprint of detected column headers. If an exact match exists, auto-apply with "Previously mapped" confidence label. If no exact match but an existing mapping covers ≥80% of the new headers, offer it as a suggestion with Medium confidence.

**Relationship to 087 templates**: 087 analyst-named templates stored free-form output column names. These are structurally incompatible with canonical-only output. The auto-mapping system ignores them; analyst-named templates from 087 are no longer shown in the UI.

---

## 6. Canonical Schema Enforcement Architecture

**Decision**: `CensusSchema` is a module-level singleton — a frozen list of `CensusFieldDefinition` dataclass instances loaded once at Python process startup. No database, no file I/O at runtime.

**Enforcement points** (layered defense):
1. **Router** (`routers/imports.py`): `_validate_mapping()` checks that every non-excluded `output_column` is a known canonical field name. Returns HTTP 422 with field-level errors if not.
2. **Service** (`import_service.py`): `generate_parquet()` asserts all required canonical fields are present in mappings before calling `MappingEngine.apply()`. Raises `ValueError` if any required field is missing.
3. **Model** (`models/imports.py`): No change needed — `FieldMapping.output_column` remains a free string at the model level (validation is at the router layer, not the model layer).

**Why not at the model level**: Pydantic model validation would require importing `CensusSchema` into `models/imports.py`, creating a circular dependency risk. Router-layer validation is the right place.

---

## 7. New API Endpoint Design

**`GET /{workspace_id}/imports/{import_id}/suggestions`**

Returns auto-suggestions for all detected columns, plus format detection results for date/decimal/boolean columns, plus initial data quality scan results.

Response payload:
```json
{
  "import_id": "...",
  "suggestions": [
    {
      "input_column": "Hire Date",
      "suggested_canonical_field": "employee_hire_date",
      "confidence": "high",
      "confidence_score": 0.91,
      "reason": "name_match",
      "format_detection": {
        "detected_format": "%m/%d/%Y",
        "parsed_sample_values": ["2018-03-15", "2019-07-22"],
        "is_ambiguous": false,
        "format_options": null
      }
    }
  ],
  "data_quality": {
    "duplicate_employee_id_count": 3,
    "null_required_field_counts": {"employee_id": 0, "employee_hire_date": 2},
    "compensation_outlier_count": 1
  },
  "canonical_schema": [
    {"field_name": "employee_id", "required": true, "data_type": "string", "description": "Unique employee identifier"}
  ]
}
```

This single endpoint gives the frontend everything it needs to render the mapping wizard in one round trip.

---

## 8. Frontend Mapping Wizard Redesign

**Decision**: Replace the free-text `output_column` input in `FieldMappingStep.tsx` with a `<select>` dropdown populated from the canonical schema. Required fields listed first with a `*` indicator.

**Auto-population**: On component mount, call `getSuggestions()`. For each suggestion with confidence ≥ Medium, pre-select the canonical field in the dropdown. Low-confidence suggestions are pre-selected but the row is highlighted amber to indicate analyst review needed.

**Format detection display**: Below each row mapped to a date/decimal/boolean field, show a collapsed inline panel with:
- Detected format string (e.g., `%m/%d/%Y`)
- 3 parsed sample values
- "Confirm" / "Change format" actions

**Data quality panel**: At the top of `PreviewStep.tsx`, a dismissible banner that summarizes: N duplicate employee IDs, N null required fields. Clicking expands to show the specific rows/columns affected.

**Transformation panel**: Keep the existing transform panel (date_parse, string_case, null_replace, etc.) — it's still needed for manual overrides. The format detection auto-populates the `date_parse` transform params when a format is detected.
