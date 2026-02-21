# Data Model: Deferral Rate Distribution Comparison

**Branch**: `059-deferral-dist-comparison` | **Date**: 2026-02-21

## Entities

### DeferralRateBucket (existing — no changes)

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | string | Rate label: "0%", "1%", "2%", ..., "9%", "10%+" |
| `count` | int | Number of enrolled employees in this bucket |
| `percentage` | float | Percentage of enrolled employees (0-100) |

**Uniqueness**: `(bucket)` within a single distribution. Always 11 buckets, ordered by rate.

### DeferralDistributionYear (new)

| Field | Type | Description |
|-------|------|-------------|
| `year` | int | Simulation year |
| `distribution` | List[DeferralRateBucket] | 11-bucket distribution for this year |

**Uniqueness**: `(year)` within a scenario's distribution list.

### DCPlanAnalytics (existing — extended)

New field added:

| Field | Type | Description |
|-------|------|-------------|
| `deferral_distribution_by_year` | List[DeferralDistributionYear] | Per-year deferral distributions for all simulation years |

Existing field retained for backward compatibility:

| Field | Type | Description |
|-------|------|-------------|
| `deferral_rate_distribution` | List[DeferralRateBucket] | Final-year distribution (unchanged) |

## Relationships

```
DCPlanComparisonResponse
  └── analytics: List[DCPlanAnalytics]        (1 per scenario)
        ├── deferral_rate_distribution          (final year, existing)
        └── deferral_distribution_by_year       (all years, new)
              └── DeferralDistributionYear
                    └── distribution: List[DeferralRateBucket]  (11 buckets)
```

## Data Source

All distribution data is derived from `fct_workforce_snapshot`:
- Filtered to `UPPER(employment_status) = 'ACTIVE'` and `is_enrolled_flag = true`
- Grouped by simulation year
- `current_deferral_rate` mapped to 11 buckets using CASE expression
- Percentage calculated as `count / total_enrolled_in_year * 100`

## Validation Rules

- Each distribution MUST contain exactly 11 buckets (including zero-count buckets)
- Bucket percentages MUST sum to 100% (±0.1% rounding tolerance)
- Years in `deferral_distribution_by_year` MUST match years in `contribution_by_year`
- Counts MUST be non-negative integers
