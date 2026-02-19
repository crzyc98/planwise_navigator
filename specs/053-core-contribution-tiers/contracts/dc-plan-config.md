# API Contract: DC Plan Core Contribution Configuration

**Branch**: `053-core-contribution-tiers` | **Date**: 2026-02-19

## Extended Fields in dc_plan Payload

The existing `PUT /{workspace_id}/scenarios/{scenario_id}` endpoint's `config_overrides.dc_plan` object gains one new field.

### New Field: `core_points_schedule`

Added alongside existing `core_status`, `core_graded_schedule`:

```json
{
  "dc_plan": {
    "core_enabled": true,
    "core_status": "points_based",
    "core_contribution_rate_percent": 1.0,
    "core_points_schedule": [
      {
        "min_points": 0,
        "max_points": 40,
        "contribution_rate": 0.01
      },
      {
        "min_points": 40,
        "max_points": 75,
        "contribution_rate": 0.02
      },
      {
        "min_points": 75,
        "max_points": null,
        "contribution_rate": 0.03
      }
    ]
  }
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `core_status` | string | Yes (when core_enabled) | `"flat"`, `"graded_by_service"`, or `"points_based"` |
| `core_points_schedule` | array | When core_status = "points_based" | Ordered list of point-range tiers |
| `core_points_schedule[].min_points` | integer | Yes | Lower bound (inclusive), >= 0 |
| `core_points_schedule[].max_points` | integer or null | Yes | Upper bound (exclusive), null = unbounded |
| `core_points_schedule[].contribution_rate` | float | Yes | Decimal rate (0.03 = 3%) |

### Extended `core_status` Enum

**Before**: `"flat"` | `"graded_by_service"`
**After**: `"flat"` | `"graded_by_service"` | `"points_based"`

### dbt Variable Mapping

When `core_status = "points_based"`, the export function produces:

```yaml
employer_core_status: "points_based"
employer_core_points_schedule:
  - min_points: 0
    max_points: 40
    rate: 1.0      # Percentage format for dbt macro
  - min_points: 40
    max_points: 75
    rate: 2.0
  - min_points: 75
    max_points: null
    rate: 3.0
```

Note: `contribution_rate` (decimal in API) is converted to `rate` (percentage in dbt) by multiplying by 100.
