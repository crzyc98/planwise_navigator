# dbt Variable Contracts: Tenure-Based and Points-Based Match

**Feature Branch**: `046-tenure-points-match`
**Date**: 2026-02-11

## New dbt Variables

### `employer_match_status` (Extended)

**Type**: string
**Default**: `'deferral_based'`
**Valid values**: `'deferral_based'`, `'graded_by_service'`, `'tenure_based'`, `'points_based'`
**Source**: `dc_plan.match_status` (UI) or `simulation_config.yaml`

### `tenure_match_tiers`

**Type**: array of objects
**Default**: `[]` (empty — only populated when `employer_match_status = 'tenure_based'`)
**Source**: `dc_plan.tenure_match_tiers` (UI) or `simulation_config.yaml`

**Schema**:
```yaml
tenure_match_tiers:
  - min_years: 0        # integer, >= 0
    max_years: 2         # integer or null (null = unbounded)
    rate: 25             # percentage (25 = 25%), converted from UI decimal if needed
    max_deferral_pct: 6  # percentage (6 = 6%), converted from UI decimal if needed
  - min_years: 2
    max_years: 5
    rate: 50
    max_deferral_pct: 6
  - min_years: 5
    max_years: null
    rate: 100
    max_deferral_pct: 6
```

**Field name mapping (UI → dbt)**:
| UI Field | dbt Field | Notes |
|----------|-----------|-------|
| `min_years` | `min_years` | Direct mapping |
| `max_years` | `max_years` | Direct mapping, null = unbounded |
| `match_rate` | `rate` | Converted: if <= 1 → multiply by 100 |
| `max_deferral_pct` | `max_deferral_pct` | Converted: if <= 1 → multiply by 100 |

### `points_match_tiers`

**Type**: array of objects
**Default**: `[]` (empty — only populated when `employer_match_status = 'points_based'`)
**Source**: `dc_plan.points_match_tiers` (UI) or `simulation_config.yaml`

**Schema**:
```yaml
points_match_tiers:
  - min_points: 0        # integer, >= 0
    max_points: 40       # integer or null (null = unbounded)
    rate: 25             # percentage (25 = 25%)
    max_deferral_pct: 6  # percentage (6 = 6%)
  - min_points: 40
    max_points: 60
    rate: 50
    max_deferral_pct: 6
  - min_points: 60
    max_points: 80
    rate: 75
    max_deferral_pct: 6
  - min_points: 80
    max_points: null
    rate: 100
    max_deferral_pct: 6
```

**Field name mapping (UI → dbt)**:
| UI Field | dbt Field | Notes |
|----------|-----------|-------|
| `min_points` | `min_points` | Direct mapping |
| `max_points` | `max_points` | Direct mapping, null = unbounded |
| `match_rate` | `rate` | Converted: if <= 1 → multiply by 100 |
| `max_deferral_pct` | `max_deferral_pct` | Converted: if <= 1 → multiply by 100 |

## New dbt Macros

### `get_points_based_match_rate(points_col, points_schedule, default_rate)`

**File**: `dbt/macros/get_points_based_match_rate.sql`

**Parameters**:
- `points_col`: SQL column expression for points value (e.g., `ec.applied_points`)
- `points_schedule`: Array of tier dicts from `points_match_tiers` variable
- `default_rate`: Fallback rate as decimal (e.g., `0.50`)

**Returns**: SQL CASE expression returning decimal match rate

**Example output**:
```sql
CASE
  WHEN ec.applied_points >= 80 THEN 1.00
  WHEN ec.applied_points >= 60 THEN 0.75
  WHEN ec.applied_points >= 40 THEN 0.50
  WHEN ec.applied_points >= 0 THEN 0.25
  ELSE 0.50
END
```

### `get_points_based_max_deferral(points_col, points_schedule, default_pct)`

**File**: `dbt/macros/get_points_based_match_rate.sql` (same file, second macro)

**Parameters**:
- `points_col`: SQL column expression for points value
- `points_schedule`: Array of tier dicts from `points_match_tiers` variable
- `default_pct`: Fallback max deferral as decimal (e.g., `0.06`)

**Returns**: SQL CASE expression returning decimal max deferral percentage

## Existing Variables (Unchanged)

These variables continue to function identically:
- `match_tiers` — deferral-based tier definitions
- `match_cap_percent` — deferral-based match cap
- `match_template` — deferral-based template name
- `employer_match_graded_schedule` — graded_by_service schedule
