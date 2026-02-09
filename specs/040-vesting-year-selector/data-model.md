# Data Model: Vesting Year Selector

**Feature**: 040-vesting-year-selector
**Date**: 2026-02-09

## Entities

### Simulation Year (existing — no changes)

The simulation year is an integer column already present in `fct_workforce_snapshot`. No schema changes are needed.

| Attribute | Type | Source | Notes |
|-----------|------|--------|-------|
| `simulation_year` | `INTEGER` | `fct_workforce_snapshot` | Range: 2020-2050 (validated by Pydantic) |

### VestingAnalysisRequest (existing — no changes)

Already includes `simulation_year` as an optional field.

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| `current_schedule` | `VestingScheduleConfig` | Yes | — | Must be valid schedule type |
| `proposed_schedule` | `VestingScheduleConfig` | Yes | — | Must be valid schedule type |
| `simulation_year` | `int` | No | `None` (→ final year) | `ge=2020, le=2050` |

### Available Years Response (new)

Simple response model for the years endpoint.

| Field | Type | Description |
|-------|------|-------------|
| `years` | `List[int]` | Sorted ascending list of available simulation years |
| `default_year` | `int` | The most recent (final) year — recommended default |

## State Transitions

No state transitions. This feature is read-only.

## Query Pattern

```sql
-- Get available simulation years for a scenario's database
SELECT DISTINCT simulation_year
FROM fct_workforce_snapshot
ORDER BY simulation_year ASC
```

This returns 1-N rows (one per simulated year). The `default_year` is `MAX(simulation_year)` from the same result set.
