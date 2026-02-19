# Data Model: Core Contribution Tier Validation & Points-Based Mode

**Branch**: `053-core-contribution-tiers` | **Date**: 2026-02-19

## Entities

### PointsCoreTier (New)

Represents a single tier in the points-based core contribution schedule.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| minPoints | integer | >= 0 | Lower bound of points range (inclusive) |
| maxPoints | integer or null | > minPoints when set; null = unbounded | Upper bound of points range (exclusive) |
| rate | float | >= 0, <= 100 | Core contribution rate as percentage of compensation |

**Lifecycle**: Created/edited/deleted in the UI tier editor. Persisted as part of plan design config. Read by simulation engine at runtime.

**Validation Rules**:
- First tier should start at minPoints = 0 (warning if not)
- No gaps between consecutive tiers (warning)
- No overlaps between consecutive tiers (warning)
- At least one tier required when points_based mode is active

### CoreContributionConfig (Extended)

The overall core contribution configuration for a plan design.

| Field | Type | Current Values | New Values |
|-------|------|----------------|------------|
| dcCoreStatus | string | `'flat'`, `'graded_by_service'` | + `'points_based'` |
| dcCoreGradedSchedule | CoreGradedTier[] | Existing | No change |
| dcCorePointsSchedule | PointsCoreTier[] | N/A (new) | Array of point-range tiers |

## Data Flow

```
UI (FormData)                    API Payload (dc_plan)              dbt Variables
─────────────                    ────────────────────               ──────────────
dcCoreStatus: 'points_based' → core_status: 'points_based'    → employer_core_status: 'points_based'
dcCorePointsSchedule: [        → core_points_schedule: [        → employer_core_points_schedule: [
  {minPoints, maxPoints, rate}     {min_points, max_points,         {min_points, max_points,
]                                   contribution_rate (decimal)}      rate (percentage)}
                                 ]                                ]
```

**Unit conversions**:
- UI `rate` (percentage, e.g., 3.0) → API `contribution_rate` (decimal, e.g., 0.03) → dbt `rate` (percentage, e.g., 3.0)
- The API-to-dbt conversion multiplies by 100 to restore percentage format for the dbt macro

## Relationships

- `PointsCoreTier` is a child of `CoreContributionConfig` (1:N, ordered list)
- `CoreContributionConfig` is part of `FormData` / plan design settings
- Points formula references employee `age_as_of_december_31` and `current_tenure` from `fct_workforce_snapshot`
