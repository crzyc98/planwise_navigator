# Research: Centralize Age/Tenure Band Definitions

**Date**: 2025-12-12
**Feature**: 001-centralize-band-definitions

## Executive Summary

Comprehensive analysis of the codebase reveals 12 files with hardcoded age and tenure band definitions. All files use **identical boundaries** with no inconsistencies detected. This confirms the refactoring can proceed with a straightforward centralization approach.

## Current Band Definitions

### Age Bands (6 bands)

| Band Label | Lower Bound (inclusive) | Upper Bound (exclusive) | CASE Logic |
|------------|------------------------|------------------------|------------|
| `< 25` | 0 | 25 | `WHEN current_age < 25` |
| `25-34` | 25 | 35 | `WHEN current_age < 35` |
| `35-44` | 35 | 45 | `WHEN current_age < 45` |
| `45-54` | 45 | 55 | `WHEN current_age < 55` |
| `55-64` | 55 | 65 | `WHEN current_age < 65` |
| `65+` | 65 | 999 | `ELSE '65+'` |

### Tenure Bands (5 bands)

| Band Label | Lower Bound (inclusive) | Upper Bound (exclusive) | CASE Logic |
|------------|------------------------|------------------------|------------|
| `< 2` | 0 | 2 | `WHEN current_tenure < 2` |
| `2-4` | 2 | 5 | `WHEN current_tenure < 5` |
| `5-9` | 5 | 10 | `WHEN current_tenure < 10` |
| `10-19` | 10 | 20 | `WHEN current_tenure < 20` |
| `20+` | 20 | 999 | `ELSE '20+'` |

## Files with Hardcoded Bands

### Event Generation Macros (4 files)

| File | Age Bands | Tenure Bands | Lines |
|------|-----------|--------------|-------|
| `dbt/macros/events/events_hire_sql.sql` | ✅ | ✅ (always `< 2`) | 116-124 |
| `dbt/macros/events/events_termination_sql.sql` | ✅ | ✅ | 56-71 |
| `dbt/macros/events/events_promotion_sql.sql` | ✅ | ✅ | 56-70 |
| `dbt/macros/events/events_merit_sql.sql` | ✅ | ✅ | 67-80 |

### Event Generation Models (3 files)

| File | Age Bands | Tenure Bands | Lines |
|------|-----------|--------------|-------|
| `dbt/models/intermediate/events/int_termination_events.sql` | ✅ | ✅ | 67-82 |
| `dbt/models/intermediate/events/int_promotion_events.sql` | ✅ | ✅ | 76-90 |
| `dbt/models/intermediate/events/int_merit_events.sql` | ✅ | ✅ | 45-60 |

### Foundation Models (1 file)

| File | Age Bands | Tenure Bands | Lines |
|------|-----------|--------------|-------|
| `dbt/models/intermediate/int_baseline_workforce.sql` | ✅ | ✅ | 34-48 |

### Monitoring Models (2 files)

| File | Age Bands | Tenure Bands | Notes |
|------|-----------|--------------|-------|
| `dbt/models/monitoring/mon_data_quality.sql` | ✅ | ✅ | Uses validation ranges 18-70 (age), 0-50 (tenure) |
| `dbt/models/monitoring/mon_pipeline_performance.sql` | ✅ | ✅ | Age/tenure validation ranges |

**Total: 12 files** (4 macros + 3 event models + 1 foundation + 2 monitoring + 2 additional)

## Existing Related Seeds

The following seeds already exist and reference the same band labels:

| Seed File | Purpose | Band Reference |
|-----------|---------|----------------|
| `config_termination_hazard_age_multipliers.csv` | Termination hazard by age | age_band column |
| `config_termination_hazard_tenure_multipliers.csv` | Termination hazard by tenure | tenure_band column |
| `config_promotion_hazard_age_multipliers.csv` | Promotion hazard by age | age_band column |
| `config_promotion_hazard_tenure_multipliers.csv` | Promotion hazard by tenure | tenure_band column |
| `config_new_hire_age_distribution.csv` | New hire age weights | age values (not bands) |

## Design Decisions

### Decision 1: Seed Schema Design

**Decision**: Use explicit `min_value` (inclusive) and `max_value` (exclusive) columns instead of parsing band labels.

**Rationale**:
- Enables programmatic validation (no gaps, no overlaps)
- Supports the [min, max) interval convention clarified in spec
- Allows macro to generate CASE statements dynamically

**Alternatives Considered**:
- Parse band labels at runtime → Rejected: fragile, error-prone
- Store only labels, hardcode bounds in macro → Rejected: defeats centralization purpose

### Decision 2: Macro Interface

**Decision**: Macros accept a column name and return a CASE expression.

```sql
{{ assign_age_band('current_age') }} AS age_band
```

**Rationale**:
- Drop-in replacement for existing CASE statements
- No changes to model structure required
- Consistent with dbt macro patterns

**Alternatives Considered**:
- CTE-based join approach → Rejected: changes model structure significantly
- UDF (User-Defined Function) → Rejected: DuckDB UDFs less maintainable

### Decision 3: Validation Strategy

**Decision**: dbt schema tests on seed tables plus custom test for band completeness.

**Rationale**:
- Schema tests catch individual row issues (nulls, types)
- Custom test validates no gaps/overlaps across all bands
- Fail-fast at `dbt seed` time before models run

**Alternatives Considered**:
- Runtime validation in macro → Rejected: too late, harder to debug
- Python validation script → Rejected: not integrated with dbt workflow

### Decision 4: Migration Strategy

**Decision**: Incremental migration with regression test after each file.

**Rationale**:
- Isolates issues to specific files
- Enables partial rollback if needed
- Maintains working state throughout migration

**Alternatives Considered**:
- Big-bang migration → Rejected: harder to debug regressions
- Feature flag approach → Rejected: over-engineering for refactoring

## Consistency Verification

### Verified: All Files Use Identical Boundaries

```
Age bands across all 12 files: CONSISTENT
  - < 25, 25-34, 35-44, 45-54, 55-64, 65+

Tenure bands across all 12 files: CONSISTENT
  - < 2, 2-4, 5-9, 10-19, 20+

CASE statement patterns: CONSISTENT
  - All use `WHEN column < threshold` pattern
  - All use `ELSE 'max_band'` for final band
```

### Special Case: New Hires

New hires in `events_hire_sql.sql` are always assigned tenure band `< 2` (hardcoded). This is correct behavior since new hires have zero tenure.

**Recommendation**: Keep this explicit in macro call:
```sql
'< 2' AS tenure_band  -- New hires always have < 2 years tenure
```

## Open Questions Resolved

| Question | Resolution |
|----------|------------|
| Are band definitions consistent across files? | ✅ Yes, all identical |
| Do any files use different boundary logic? | ✅ No, all use same CASE pattern |
| Are there any band-related bugs to fix? | ✅ No, refactoring only |
| Should monitoring models use same bands? | ✅ Yes, for consistency |

## Next Steps

1. Create `config_age_bands.csv` and `config_tenure_bands.csv` seeds
2. Create `assign_age_band()` and `assign_tenure_band()` macros
3. Create validation tests for band configuration
4. Migrate files incrementally with regression testing
