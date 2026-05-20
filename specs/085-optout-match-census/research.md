# Research: Match Census for Opt-Out Rate Configuration

**Branch**: `085-optout-match-census` | **Phase**: 0 Research

## Decision Log

### D-001: Census Enrollment Detection Column

**Decision**: Use `employee_deferral_rate > 0` as the enrollment indicator for the opt-out rate calculation.

**Rationale**: The census staging model (`stg_census_data.sql` line 141-145) derives enrollment date from `employee_deferral_rate > 0`. This is the canonical source of truth for whether a census employee is actively deferring into the plan. A deferral rate of 0 or NULL means the employee is not enrolled.

**Alternatives considered**:
- `participation_status` column: Not present in the raw census file; only available after simulation post-processing (`fct_workforce_snapshot`).
- `is_enrolled_flag`: Derived field in simulation output, not in census input.
- Separate enrollment status column: Not defined in census schema; would require users to have non-standard census files.

---

### D-002: API Endpoint Placement

**Decision**: Add the new endpoint to the existing `planalign_api/routers/bands.py` router, which already handles all census analysis endpoints (`analyze-turnover`, `analyze-age-bands`, `analyze-tenure-bands`).

**Rationale**: All census analysis endpoints are co-located in `bands.py`. Adding a new endpoint there keeps all census analysis in one router and avoids creating a new router file for a single endpoint.

**Alternatives considered**:
- New `enrollment.py` router: Unnecessary fragmentation for one endpoint.
- `files.py` router: Already handles file upload and age/compensation analysis but does not handle band-style census analysis.

---

### D-003: Service Implementation Location

**Decision**: Create a new `OptOutAnalysisService` class in a new file `planalign_api/services/opt_out_service.py`.

**Rationale**: Follows the existing one-class-per-service pattern (`turnover_service.py`, `band_service.py`). Keeps service files focused and under ~300 lines. The opt-out analysis logic is distinct enough from turnover and band analysis to warrant its own module.

**Alternatives considered**:
- Extending `TurnoverAnalysisService`: Opt-out analysis has different census columns (deferral rate vs. termination date) and different calculation logic. Combining would violate single responsibility.
- Adding to `file_service.py`: Already large; co-location with compensation analysis is not thematically close.

---

### D-004: Lookback Years Behavior

**Decision**: Filter census employees to those whose hire date is within `lookback_years` of the maximum hire date found in the census file (not today's date). Default lookback is 3 years.

**Rationale**: Census files are point-in-time snapshots and may be years old. Using the maximum hire date in the census as the reference point ensures the lookback window is relative to the census snapshot, not the current date. This matches how `analyze_compensation_by_level` handles its lookback in `file_service.py` (line 1016).

**Alternatives considered**:
- Relative to today's date: Would exclude all employees in an older census, producing misleading empty results.
- Fixed calendar year: Less flexible; forces the concept of a "census year" that may not be provided.

---

### D-005: SQL Security for Deferral Column

**Decision**: Add `employee_deferral_rate` and `deferral_rate` to `ALL_CENSUS_COLUMNS` in `sql_security.py` as a new `CENSUS_DEFERRAL_COLUMNS` frozenset.

**Rationale**: The SQL security module (`sql_security.py`) validates column names used in dynamic SQL against an allowlist. `employee_deferral_rate` is a known census column used by the dbt staging model and must be explicitly registered. Following the existing pattern of named frozensets (e.g., `CENSUS_HIRE_DATE_COLUMNS`, `CENSUS_COMPENSATION_COLUMNS`).

---

### D-006: Frontend Preview Pattern

**Decision**: Follow `TurnoverSection.tsx` pattern: `analyzing`/`analysis`/`analysisError` state, inline preview panel with "Apply" and "Dismiss" buttons, button disabled when `censusDataPath` is absent.

**Rationale**: This pattern is already implemented and tested in `TurnoverSection.tsx`. Reusing it gives analysts a consistent UX across all "Match Census" features. The preview shows statistics before applying, preventing accidental overwrites.

**Alternatives considered**:
- Modal dialog: Higher implementation complexity; inline preview matches existing patterns.
- Auto-apply without preview: Prevents analyst review; contradicts feature spec requirement for preview-before-apply.

---

### D-007: Tenure Lookback Input (UI)

**Decision**: Provide a numeric stepper input (integer, min=1, max=50, default=3) directly in the preview panel, matching the compensation analysis lookback UI pattern in `NewHireSection.tsx`.

**Rationale**: The lookback years input must be easy to change for exploratory analysis (FR-005). The numeric stepper pattern from `NewHireSection.tsx` (lines 23-26) is already familiar to users.

---

## Key Files Reference

| Purpose | Path |
|---------|------|
| Opt-out rate UI (current) | `planalign_studio/components/config/DCPlanSection.tsx:99-136` |
| TurnoverSection match-census pattern | `planalign_studio/components/config/TurnoverSection.tsx:1-55` |
| Frontend API service | `planalign_studio/services/api.ts` |
| Census analysis router | `planalign_api/routers/bands.py` |
| Turnover service (template) | `planalign_api/services/turnover_service.py` |
| Turnover Pydantic models | `planalign_api/models/turnover.py` |
| SQL security column allowlists | `planalign_api/services/sql_security.py:258-306` |
| Census enrollment in staging | `dbt/models/staging/stg_census_data.sql:141-145` |
| Config: opt-out rates | `planalign_orchestrator/config/workforce.py:23-30` |
