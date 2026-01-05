# Research: Fix Service-Based Core Contribution Calculation

**Date**: 2026-01-05
**Feature Branch**: `009-fix-service-based-core-contribution`

## Executive Summary

The graded-by-service core contribution feature is non-functional. The UI and configuration export work correctly, but the dbt SQL model that calculates employer core contributions ignores the service tier configuration and always applies a flat rate.

---

## Bug Investigation

### Primary Bug Location

**File**: `/workspace/dbt/models/intermediate/int_employer_core_contributions.sql`

### Root Cause Analysis

| Issue | Location | Description |
|-------|----------|-------------|
| Variables not read | Lines 38-47 | `employer_core_status` and `employer_core_graded_schedule` never declared |
| Tenure data missing | Lines 193-199 | `snapshot_flags` CTE doesn't include `current_tenure` |
| Hardcoded flat rate | Lines 246, 274 | Always uses `{{ employer_core_contribution_rate }}` |

### Configuration Export (Working Correctly)

**File**: `/workspace/planalign_orchestrator/config/export.py` (lines 621-631)

The configuration system correctly exports:
- `employer_core_status`: 'none', 'flat', or 'graded_by_service'
- `employer_core_graded_schedule`: List of tier objects

```python
# Lines 621-631 - Export working correctly
if dc_plan_dict.get("core_status") is not None:
    core_top_level["status"] = str(dc_plan_dict["core_status"])
    dbt_vars["employer_core_status"] = str(dc_plan_dict["core_status"])

if dc_plan_dict.get("core_graded_schedule") is not None:
    graded_schedule = dc_plan_dict["core_graded_schedule"]
    if isinstance(graded_schedule, list) and len(graded_schedule) > 0:
        core_top_level["graded_schedule"] = graded_schedule
        dbt_vars["employer_core_graded_schedule"] = graded_schedule
```

### Tenure Data Availability

**File**: `/workspace/dbt/models/intermediate/int_workforce_snapshot_optimized.sql`

The `current_tenure` field is already calculated and available:
- Computed from `employee_hire_date`
- Represents years of service as a decimal
- Used for status classification but NOT for core contribution tier lookup

---

## Data Flow Analysis

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER CONFIGURATION                           │
│  PlanAlign Studio UI → dc_plan.core_status = 'graded_by_service'   │
│                      → dc_plan.core_graded_schedule = [...]         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CONFIGURATION EXPORT                           │
│  planalign_orchestrator/config/export.py (lines 621-631)            │
│  → dbt_vars["employer_core_status"] = 'graded_by_service'          │
│  → dbt_vars["employer_core_graded_schedule"] = [{...}, {...}]      │
│  STATUS: ✅ WORKING                                                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DBT MODEL (BROKEN)                             │
│  dbt/models/intermediate/int_employer_core_contributions.sql        │
│  ❌ Does NOT read employer_core_status                              │
│  ❌ Does NOT read employer_core_graded_schedule                     │
│  ❌ Does NOT join current_tenure from snapshot                      │
│  ❌ Always applies flat rate: {{ employer_core_contribution_rate }} │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INCORRECT OUTPUT                               │
│  All employees receive 8% (flat rate)                               │
│  Service tiers completely ignored                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Approach

### Decision: Jinja-Generated SQL CASE Statement

**Rationale**:
1. DuckDB executes CASE statements efficiently with vectorized processing
2. Matches existing patterns for hazard band assignment (e.g., `assign_age_band` macro)
3. Avoids runtime complexity - SQL is generated at compile time
4. Easy to debug - can inspect compiled SQL

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **SQL CASE statement** | Simple, efficient, debuggable | Static generation | ✅ Selected |
| Jinja for-loop | Dynamic | Complex, harder to debug | ❌ Rejected |
| Python preprocessing | Flexible | Adds orchestrator coupling | ❌ Rejected |
| Lookup table join | Normalized | Requires new seed/model | ❌ Rejected |

### Tier Matching Convention

Following the project's `[min, max)` interval convention (minimum inclusive, maximum exclusive):

```sql
-- Example: 0-9 years → 6%, 10+ years → 8%
CASE
  WHEN years_of_service >= 10 THEN 0.08  -- 10+ years
  WHEN years_of_service >= 0 THEN 0.06   -- 0-9 years
  ELSE 0.08  -- Fallback to highest tier for edge cases
END
```

**Key Rules**:
- Sort tiers by `min_years` descending for correct evaluation order
- Use integer years (FLOOR of decimal tenure)
- Highest tier applies when tenure exceeds all defined ranges
- Rate conversion: UI sends percentage (6.0), divide by 100 for decimal (0.06)

---

## Implementation Checklist

### 1. Read Variables (Lines 38-47)

```sql
{% set employer_core_status = var('employer_core_status', 'flat') %}
{% set employer_core_graded_schedule = var('employer_core_graded_schedule', []) %}
```

### 2. Add Tenure to snapshot_flags CTE (Lines 193-199)

```sql
snapshot_flags AS (
    SELECT
        employee_id,
        detailed_status_code,
        FLOOR(current_tenure) AS years_of_service
    FROM {{ ref('int_workforce_snapshot_optimized') }}
    WHERE simulation_year = {{ simulation_year }}
),
```

### 3. Create Tier Lookup Macro

**Option A**: Inline in model (simpler for single use)
**Option B**: New macro file `macros/get_tiered_core_rate.sql` (reusable)

```sql
{% macro get_tiered_core_rate(years_of_service_col, graded_schedule, flat_rate) %}
CASE
  {% for tier in graded_schedule | sort(attribute='min_years', reverse=true) %}
  WHEN {{ years_of_service_col }} >= {{ tier.min_years }} THEN {{ tier.rate / 100.0 }}
  {% endfor %}
  ELSE {{ flat_rate }}
END
{% endmacro %}
```

### 4. Update Contribution Calculation (Line 246)

Replace:
```sql
ROUND(... * {{ employer_core_contribution_rate }}, 2)
```

With:
```sql
ROUND(... *
  CASE
    WHEN '{{ employer_core_status }}' = 'graded_by_service' THEN
      {{ get_tiered_core_rate('COALESCE(snap.years_of_service, 0)', employer_core_graded_schedule, employer_core_contribution_rate) }}
    ELSE {{ employer_core_contribution_rate }}
  END
, 2)
```

### 5. Update Rate Output Field (Line 274)

Mirror the logic for `core_contribution_rate` output field.

### 6. Add Audit Fields

```sql
-- In final SELECT
COALESCE(snap.years_of_service, 0) AS applied_years_of_service,
-- The applied_core_rate is already captured in core_contribution_rate
```

---

## Test Scenarios

| Scenario | Config | Employee Tenure | Expected Rate |
|----------|--------|-----------------|---------------|
| 2-tier graded | 0-9: 6%, 10+: 8% | 5 years | 6% |
| 2-tier graded | 0-9: 6%, 10+: 8% | 15 years | 8% |
| 2-tier graded | 0-9: 6%, 10+: 8% | 10 years exactly | 8% |
| 2-tier graded | 0-9: 6%, 10+: 8% | 0 years (new hire) | 6% |
| Flat rate | 8% flat | Any tenure | 8% |
| Disabled | none | Any tenure | 0% |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Regression in flat-rate scenarios | Low | High | Add test for flat-rate behavior |
| Tenure null values | Medium | Medium | Use COALESCE with 0 default |
| Rate precision issues | Low | Low | Use DECIMAL(5,4) for rates |
| Performance degradation | Low | Low | CASE is efficient in DuckDB |

---

## References

- Epic E084: Comprehensive DC Plan Configuration (where graded_schedule was added)
- `int_employer_core_contributions.sql`: Current model (321 lines)
- `config/export.py`: Configuration export logic
- `config_age_bands.csv` / `assign_age_band` macro: Similar pattern for band assignment
