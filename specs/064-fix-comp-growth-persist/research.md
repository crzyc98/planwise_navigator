# Research: Fix Target Compensation Growth Persistence

**Feature**: 064-fix-comp-growth-persist
**Date**: 2026-03-09

## Research Tasks

### R1: Root Cause Analysis — Why the slider value is not persisted

**Decision**: The slider uses local `useState(5.0)` in CompensationSection.tsx (line 10) instead of reading from the shared `formData` state managed by ConfigContext. The `FormData` interface in types.ts lacks a `targetCompensationGrowth` field entirely, so no layer of the stack can persist or hydrate this value.

**Rationale**: The original implementation likely focused on making "Calculate Settings" work (which uses the slider value to derive COLA/merit/promo rates) without considering that the input itself needs to survive across sessions.

**Alternatives Considered**: None — this is a clear omission, not a design trade-off.

### R2: Data Flow — How existing compensation fields are persisted

**Decision**: Follow the established pattern used by all other compensation fields (meritBudget, colaRate, promoIncrease, etc.):

1. **FormData interface** (types.ts) — declares the field with TypeScript type
2. **DEFAULT_FORM_DATA** (constants.ts) — provides default value
3. **buildConfigPayload** (buildConfigPayload.ts) — maps `formData.fieldName` → `compensation.snake_case_field` for API
4. **ConfigContext useEffect** (ConfigContext.tsx) — hydrates from `cfg.compensation?.snake_case_field ?? prev.fieldName` on load
5. **Component** — reads from `formData.fieldName` and updates via `setFormData`

**Rationale**: Consistency with existing patterns minimizes risk and code review effort.

**Alternatives Considered**:
- Separate API endpoint for this field — rejected (over-engineering for a single field)
- Local storage persistence — rejected (wouldn't survive cross-device/browser scenarios)

### R3: Field Naming Convention

**Decision**:
- TypeScript (FormData): `targetCompensationGrowth` (camelCase, matches existing pattern)
- API payload key: `target_compensation_growth_percent` (snake_case with `_percent` suffix, matches `merit_budget_percent`, `cola_rate_percent`, etc.)
- Default value: `5.0` (percentage, matching the current hardcoded `useState(5.0)`)

**Rationale**: Follows exact naming conventions already in use across the compensation section.

**Alternatives Considered**:
- `targetGrowthRate` — rejected (less specific, doesn't match existing naming pattern)
- Store as decimal (0.05 instead of 5.0) — rejected (all existing compensation fields use percentage form in FormData)

### R4: Unit Conversion Between Frontend and API

**Decision**: The slider displays and stores values as percentages (e.g., 7.5 for 7.5%). The API payload should also use percentage form (matching `merit_budget_percent: 3.5`, `cola_rate_percent: 2.0`). No conversion needed.

**Rationale**: Existing compensation fields in buildConfigPayload.ts use `Number(formData.field)` directly without division by 100. The `/100` conversion happens inside the solver function, not at the API boundary.

**Alternatives Considered**:
- Store as decimal in API — rejected (inconsistent with how other `_percent` fields are stored)

### R5: Backward Compatibility Strategy

**Decision**: Use null-coalescing (`??`) during hydration to default to `5.0` when loading scenarios that lack the field. This is the exact pattern used for all other compensation fields.

**Rationale**: `cfg.compensation?.target_compensation_growth_percent ?? prev.targetCompensationGrowth` gracefully handles: (a) old scenarios without the field, (b) scenarios where compensation section is null, (c) new scenarios with the field set.

**Alternatives Considered**:
- Schema migration for old scenarios — rejected (unnecessary since `Dict[str, Any]` is flexible and null-coalescing handles missing fields)

### R6: Backend Changes Assessment

**Decision**: Minimal backend changes needed. The backend uses `config_overrides: Dict[str, Any]` which accepts arbitrary fields. No Pydantic model changes are strictly required. Optionally, document the field in ScenarioConfig for API documentation completeness.

**Rationale**: The flexible dict pattern means the backend will store and return the field without code changes. Adding it to the Pydantic model is good practice but not blocking.

**Alternatives Considered**:
- Strict schema validation on backend — deferred (would be a separate enhancement, not part of this bug fix)

## Summary

All research tasks resolved. No NEEDS CLARIFICATION items remain. The fix follows established patterns with zero architectural risk.
