# API Contract: Comparison Endpoint (Extended)

**Feature**: 048-comparison-dc-metrics
**Date**: 2026-02-12

## Endpoint

**No new endpoints.** The existing comparison endpoint is extended with a new response field.

```
GET /api/workspaces/{workspace_id}/comparison?scenarios={csv}&baseline={id}
```

**Parameters** (unchanged):
- `workspace_id` (path): Workspace identifier
- `scenarios` (query): Comma-separated scenario IDs
- `baseline` (query): Baseline scenario ID

## Response Model: ComparisonResponse (extended)

```json
{
  "scenarios": ["baseline_2025", "high_match_2025"],
  "scenario_names": {
    "baseline_2025": "Baseline",
    "high_match_2025": "High Match"
  },
  "baseline_scenario": "baseline_2025",

  "workforce_comparison": [ ... ],
  "event_comparison": [ ... ],

  "dc_plan_comparison": [
    {
      "year": 2025,
      "values": {
        "baseline_2025": {
          "participation_rate": 72.5,
          "avg_deferral_rate": 0.06,
          "total_employee_contributions": 5400000.00,
          "total_employer_match": 2160000.00,
          "total_employer_core": 810000.00,
          "total_employer_cost": 2970000.00,
          "employer_cost_rate": 3.3,
          "participant_count": 725
        },
        "high_match_2025": {
          "participation_rate": 78.2,
          "avg_deferral_rate": 0.065,
          "total_employee_contributions": 5950000.00,
          "total_employer_match": 2975000.00,
          "total_employer_core": 810000.00,
          "total_employer_cost": 3785000.00,
          "employer_cost_rate": 4.2,
          "participant_count": 782
        }
      },
      "deltas": {
        "baseline_2025": {
          "participation_rate": 0.0,
          "avg_deferral_rate": 0.0,
          "total_employee_contributions": 0.0,
          "total_employer_match": 0.0,
          "total_employer_core": 0.0,
          "total_employer_cost": 0.0,
          "employer_cost_rate": 0.0,
          "participant_count": 0
        },
        "high_match_2025": {
          "participation_rate": 5.7,
          "avg_deferral_rate": 0.005,
          "total_employee_contributions": 550000.00,
          "total_employer_match": 815000.00,
          "total_employer_core": 0.0,
          "total_employer_cost": 815000.00,
          "employer_cost_rate": 0.9,
          "participant_count": 57
        }
      }
    },
    {
      "year": 2026,
      "values": { ... },
      "deltas": { ... }
    }
  ],

  "summary_deltas": {
    "final_headcount": { ... },
    "total_growth_pct": { ... },
    "final_participation_rate": {
      "baseline": 72.5,
      "scenarios": {
        "baseline_2025": 72.5,
        "high_match_2025": 78.2
      },
      "deltas": {
        "baseline_2025": 0.0,
        "high_match_2025": 5.7
      },
      "delta_pcts": {
        "baseline_2025": 0.0,
        "high_match_2025": 7.86
      }
    },
    "final_employer_cost": {
      "baseline": 2970000.00,
      "scenarios": {
        "baseline_2025": 2970000.00,
        "high_match_2025": 3785000.00
      },
      "deltas": {
        "baseline_2025": 0.0,
        "high_match_2025": 815000.00
      },
      "delta_pcts": {
        "baseline_2025": 0.0,
        "high_match_2025": 27.44
      }
    }
  }
}
```

## Pydantic Models

### DCPlanMetrics (new)

```python
class DCPlanMetrics(BaseModel):
    participation_rate: float = Field(default=0.0, description="Participation rate (%)")
    avg_deferral_rate: float = Field(default=0.0, description="Average deferral rate")
    total_employee_contributions: float = Field(default=0.0, description="Total employee contributions")
    total_employer_match: float = Field(default=0.0, description="Total employer match")
    total_employer_core: float = Field(default=0.0, description="Total employer core")
    total_employer_cost: float = Field(default=0.0, description="Total employer cost (match + core)")
    employer_cost_rate: float = Field(default=0.0, description="Employer cost rate (%)")
    participant_count: int = Field(default=0, description="Number of enrolled employees")
```

### DCPlanComparisonYear (new)

```python
class DCPlanComparisonYear(BaseModel):
    year: int = Field(description="Simulation year")
    values: Dict[str, DCPlanMetrics] = Field(description="Metrics by scenario ID")
    deltas: Dict[str, DCPlanMetrics] = Field(description="Delta from baseline by scenario ID")
```

### ComparisonResponse (extended)

```python
class ComparisonResponse(BaseModel):
    # ... existing fields unchanged ...
    dc_plan_comparison: List[DCPlanComparisonYear] = Field(
        default_factory=list,
        description="Year-by-year DC plan comparison"
    )
```

## Backward Compatibility

- **Non-breaking change**: The new `dc_plan_comparison` field has a default value (`[]`), so existing clients that don't expect it will receive an empty list and can safely ignore it.
- **Summary deltas**: New keys (`final_participation_rate`, `final_employer_cost`) are added to the existing dictionary; existing keys (`final_headcount`, `total_growth_pct`) are unchanged.

## Error Handling

| Scenario | Behavior |
| -------- | -------- |
| Missing fct_workforce_snapshot | DC plan data returns empty list; existing workforce data unaffected |
| Zero active employees in a year | participation_rate = 0, avg_deferral_rate = 0 |
| NULL contribution columns | Treated as 0 via COALESCE |
| Mismatched year ranges | Only overlapping years included in comparison |
| Zero baseline metric | delta_pcts = 0.0 (no division by zero) |
