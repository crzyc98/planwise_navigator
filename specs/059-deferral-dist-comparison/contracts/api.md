# API Contract: Deferral Distribution Comparison

**Branch**: `059-deferral-dist-comparison` | **Date**: 2026-02-21

## No New Endpoints Required

The existing endpoint already returns all needed data. Only the response schema is extended.

## Modified Endpoint

### `GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare`

**Parameters** (unchanged):
- `scenarios` (query, required): Comma-separated scenario IDs (max 6)
- `active_only` (query, optional, default: false): Filter to active employees only

**Response Schema Change**:

The `DCPlanAnalytics` object within `analytics[]` gains one new field:

```json
{
  "scenarios": ["baseline", "high_match"],
  "scenario_names": {
    "baseline": "Baseline 2025",
    "high_match": "High Match Scenario"
  },
  "analytics": [
    {
      "scenario_id": "baseline",
      "scenario_name": "Baseline 2025",
      "deferral_rate_distribution": [
        {"bucket": "0%", "count": 15, "percentage": 5.0},
        {"bucket": "6%", "count": 120, "percentage": 40.0}
      ],
      "deferral_distribution_by_year": [
        {
          "year": 2025,
          "distribution": [
            {"bucket": "0%", "count": 20, "percentage": 6.7},
            {"bucket": "6%", "count": 100, "percentage": 33.3}
          ]
        },
        {
          "year": 2026,
          "distribution": [
            {"bucket": "0%", "count": 15, "percentage": 5.0},
            {"bucket": "6%", "count": 120, "percentage": 40.0}
          ]
        }
      ]
    }
  ]
}
```

**New Field**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `deferral_distribution_by_year` | `DeferralDistributionYear[]` | Yes | Distribution for each simulation year |

**`DeferralDistributionYear` Schema**:

| Field | Type | Description |
|-------|------|-------------|
| `year` | int | Simulation year |
| `distribution` | `DeferralRateBucket[]` | 11-bucket distribution |

**`DeferralRateBucket` Schema** (existing, unchanged):

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | string | "0%", "1%", ..., "9%", "10%+" |
| `count` | int | Employee count |
| `percentage` | float | Percentage of enrolled (0-100) |

## Backward Compatibility

- `deferral_rate_distribution` (existing final-year field) is **preserved unchanged**
- `deferral_distribution_by_year` is **additive** — existing consumers ignore unknown fields
- No parameters changed, no response fields removed
