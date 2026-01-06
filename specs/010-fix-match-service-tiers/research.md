# Research: Service-Based Match Contribution Tiers

**Feature**: 010-fix-match-service-tiers
**Date**: 2026-01-05

## Research Topics

### 1. Existing Service-Based Rate Pattern (get_tiered_core_rate)

**Decision**: Reuse the existing `get_tiered_core_rate` macro pattern for match calculations

**Rationale**:
- The core rate macro (`dbt/macros/get_tiered_core_rate.sql`) already implements:
  - Service tier lookup via CASE expression
  - [min, max) interval convention
  - Rate percentage conversion (UI percentage → decimal)
  - Descending sort for correct CASE evaluation
- Match service tiers have identical structure (min_years, max_years, rate)
- Only difference: match also needs `max_deferral_pct` per tier

**Alternatives Considered**:
- Create entirely new macro: Rejected - would duplicate logic
- Generalize get_tiered_core_rate to handle both: Rejected - different output (core returns rate, match needs rate + cap)

**Implementation**: Create `get_tiered_match_rate` macro that returns BOTH rate and max_deferral_pct for the tier

### 2. Config Export Field Transformation Pattern

**Decision**: Follow the core contribution export pattern from `_export_core_contribution_vars`

**Rationale**:
- Core export (lines 626-645 in export.py) demonstrates the pattern:
  ```python
  # UI uses: service_years_min, service_years_max, contribution_rate
  # Macro expects: min_years, max_years, rate (as percentage)
  transformed_tier = {
      "min_years": tier.get("service_years_min", tier.get("min_years", 0)),
      "max_years": tier.get("service_years_max", tier.get("max_years")),
      "rate": (tier.get("contribution_rate", tier.get("rate", 0)) * 100)
  }
  ```
- Match service tiers need same transformation plus `max_deferral_pct`

**Alternatives Considered**:
- Use same field names in UI and dbt: Rejected - breaks UI/backend separation
- No transformation, fix in macro: Rejected - inconsistent with core pattern

**Implementation**: Add `match_graded_schedule` transformation in `_export_employer_match_vars`

### 3. Frontend Match Configuration Pattern

**Decision**: Add "Service-Based" option to existing match template dropdown

**Rationale**:
- Current UI (`ConfigStudio.tsx`) has `dcMatchTemplate` with presets: simple, tiered, stretch, safe_harbor, qaca
- Each preset has `tiers: MatchTier[]` with deferral-based fields
- Service-based needs different tier fields: `min_years`, `max_years`, `rate`, `max_deferral_pct`

**Alternatives Considered**:
- Separate page/modal for service-based: Rejected - inconsistent UX
- Radio button toggle: Acceptable - but dropdown more scalable

**Implementation**:
- Add `dcMatchStatus` field: 'deferral_based' | 'graded_by_service'
- When 'graded_by_service', show service tier editor (similar to core contribution tiers)
- When 'deferral_based', show existing match template dropdown

### 4. Match Calculation Logic Integration

**Decision**: Add conditional branch in `int_employee_match_calculations.sql` based on `employer_match_status`

**Rationale**:
- Current model uses `match_tiers` (deferral-based) exclusively
- Need to preserve existing logic when `employer_match_status = 'deferral_based'`
- Add new branch when `employer_match_status = 'graded_by_service'`

**Code Structure**:
```sql
{% if employer_match_status == 'graded_by_service' %}
-- Service-based match calculation
-- Join with snapshot for years_of_service
-- Use get_tiered_match_rate macro
{% else %}
-- Existing deferral-based match calculation
-- Current CROSS JOIN with match_tiers
{% endif %}
```

**Alternatives Considered**:
- Separate model for service-based: Rejected - duplicates eligibility/cap logic
- Always apply both: Rejected - spec says mutually exclusive

### 5. Audit Trail Field Location

**Decision**: Add `applied_years_of_service` to `int_employee_match_calculations.sql` output

**Rationale**:
- Core contributions already has `applied_years_of_service` in output
- Provides compliance traceability
- Only populated when service-based mode is active (NULL for deferral-based)

**Implementation**: Add column with CASE expression based on mode

### 6. Years of Service Data Source

**Decision**: Use `int_workforce_snapshot_optimized.years_of_service` (same as core contributions)

**Rationale**:
- Core contributions model (`int_employer_core_contributions.sql`) uses:
  ```sql
  snapshot_flags AS (
      SELECT
          employee_id,
          FLOOR(COALESCE(current_tenure, 0))::INT AS years_of_service
      FROM {{ ref('int_workforce_snapshot_optimized') }}
  )
  ```
- Ensures consistency between core and match calculations
- Already handles NULL tenure with COALESCE

**Alternatives Considered**:
- Use fct_yearly_events hire date: Rejected - current_tenure is more accurate
- Add years_of_service to int_employee_contributions: Rejected - unnecessary propagation

## Summary of Key Decisions

| Topic | Decision |
|-------|----------|
| Rate macro | Create `get_tiered_match_rate` following core pattern |
| Config export | Follow `_export_core_contribution_vars` transformation pattern |
| UI structure | Add `dcMatchStatus` toggle, show different tier editor per mode |
| dbt model | Conditional branch based on `employer_match_status` |
| Audit field | Add `applied_years_of_service` column |
| Tenure source | Use `int_workforce_snapshot_optimized.current_tenure` |

## No Outstanding NEEDS CLARIFICATION

All technical decisions resolved through codebase analysis.
