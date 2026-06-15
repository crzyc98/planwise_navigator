# Interface Contract: DC Plan Analytics API

## Changed Endpoint: GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan

No new query parameters. The response schema changes to include `total_eligible_count` per year.

### Response — `DCPlanAnalytics` (changed fields shown)

```json
{
  "scenario_id": "string",
  "scenario_name": "string",
  "total_eligible": 1000,
  "total_enrolled": 650,
  "participation_rate": 65.0,
  "contribution_by_year": [
    {
      "year": 2025,
      "total_employee_contributions": 1250000.00,
      "total_employer_match": 625000.00,
      "total_employer_core": 200000.00,
      "total_all_contributions": 2075000.00,
      "participant_count": 620,
      "total_eligible_count": 980,
      "participation_rate": 63.27,
      "average_deferral_rate": 0.052,
      "..."
    }
  ],
  "deferral_rate_distribution": [
    { "bucket": "0%",   "count": 350, "percentage": 35.0 },
    { "bucket": "1%",   "count": 12,  "percentage": 1.2  },
    { "bucket": "2%",   "count": 28,  "percentage": 2.8  },
    { "bucket": "3%",   "count": 35,  "percentage": 3.5  },
    { "bucket": "4%",   "count": 41,  "percentage": 4.1  },
    { "bucket": "5%",   "count": 195, "percentage": 19.5 },
    { "bucket": "6%",   "count": 148, "percentage": 14.8 },
    { "bucket": "7%",   "count": 62,  "percentage": 6.2  },
    { "bucket": "8%",   "count": 54,  "percentage": 5.4  },
    { "bucket": "9%",   "count": 30,  "percentage": 3.0  },
    { "bucket": "10%+", "count": 45,  "percentage": 4.5  }
  ],
  "deferral_distribution_by_year": [
    {
      "year": 2025,
      "distribution": [
        { "bucket": "0%", "count": 360, "percentage": 36.0 },
        "..."
      ]
    }
  ]
}
```

### Key Contract Changes

1. **`deferral_rate_distribution[*].percentage`**: Now computed as `count / total_active_eligible * 100` (not `count / total_enrolled * 100`). The 0% bucket will now have a non-zero count when non-enrolled active employees exist. The sum of all bucket percentages always equals 100% of active eligible employees.

2. **`contribution_by_year[*].total_eligible_count`**: New field. Integer. Total number of eligible employees (regardless of enrollment status) for that simulation year. Allows UI to display "X enrolled of Y eligible" for any selected year.

3. **`deferral_distribution_by_year`**: Same structural change as `deferral_rate_distribution` — 0% buckets now include non-enrolled active employees.

### Backward Compatibility

- Adding `total_eligible_count` to `ContributionYearSummary` is additive; existing consumers that don't read this field are unaffected.
- The change to `deferral_rate_distribution` semantics (including non-enrolled in 0% bucket) is a **behavioral change**, not a schema change. Any consumer rendering the distribution chart will show more employees in the 0% bucket after this fix.

---

## Unchanged Endpoint: GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare

No changes to this endpoint. The comparison response already includes full `DCPlanAnalytics` per scenario (including `contribution_by_year`), so year filtering in comparison mode is handled client-side.
