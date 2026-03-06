# API Contract: Winners & Losers

## Endpoint

```
GET /api/workspaces/{workspace_id}/analytics/winners-losers?plan_a={scenario_id}&plan_b={scenario_id}
```

## Parameters

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| workspace_id | path | string | yes | Workspace identifier |
| plan_a | query | string | yes | Scenario ID for Plan A (reference) |
| plan_b | query | string | yes | Scenario ID for Plan B (alternative) |

## Response: 200 OK

```json
{
  "plan_a_scenario_id": "baseline_2025",
  "plan_b_scenario_id": "high_match_2025",
  "final_year": 2027,
  "total_compared": 450,
  "total_excluded": 12,
  "total_winners": 180,
  "total_losers": 120,
  "total_neutral": 150,
  "age_band_results": [
    {
      "band_label": "< 25",
      "winners": 15,
      "losers": 8,
      "neutral": 12,
      "total": 35
    }
  ],
  "tenure_band_results": [
    {
      "band_label": "< 2",
      "winners": 22,
      "losers": 18,
      "neutral": 20,
      "total": 60
    }
  ],
  "heatmap": [
    {
      "age_band": "< 25",
      "tenure_band": "< 2",
      "winners": 5,
      "losers": 3,
      "neutral": 4,
      "total": 12,
      "net_pct": 16.67
    }
  ]
}
```

## Error Responses

| Status | Condition |
|--------|-----------|
| 400 | plan_a or plan_b missing, or same scenario for both |
| 404 | Workspace not found, or scenario not found |
| 422 | Scenario not completed (no results available) |
| 500 | Database query failure |
