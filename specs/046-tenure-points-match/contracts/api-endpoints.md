# API Contracts: Tenure-Based and Points-Based Match

**Feature Branch**: `046-tenure-points-match`
**Date**: 2026-02-11

## Extended Endpoints

### PUT /api/workspaces/{workspace_id}/scenarios/{scenario_id}/config

Existing endpoint for saving scenario configuration overrides. Extended to accept new match mode fields.

**Request body** (relevant fields only):
```json
{
  "dc_plan": {
    "match_status": "points_based",
    "points_match_tiers": [
      {
        "min_points": 0,
        "max_points": 40,
        "match_rate": 0.25,
        "max_deferral_pct": 0.06
      },
      {
        "min_points": 40,
        "max_points": 60,
        "match_rate": 0.50,
        "max_deferral_pct": 0.06
      },
      {
        "min_points": 60,
        "max_points": 80,
        "match_rate": 0.75,
        "max_deferral_pct": 0.06
      },
      {
        "min_points": 80,
        "max_points": null,
        "match_rate": 1.00,
        "max_deferral_pct": 0.06
      }
    ]
  }
}
```

**Validation errors** (422):
```json
{
  "detail": [
    {
      "loc": ["body", "dc_plan", "points_match_tiers"],
      "msg": "Gap detected between tier 1 (max_points=40) and tier 2 (min_points=45)",
      "type": "value_error"
    }
  ]
}
```

**Tenure-based variant**:
```json
{
  "dc_plan": {
    "match_status": "tenure_based",
    "tenure_match_tiers": [
      {
        "min_years": 0,
        "max_years": 2,
        "match_rate": 0.25,
        "max_deferral_pct": 0.06
      }
    ]
  }
}
```

### GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/config

Returns scenario configuration including new match fields.

**Response** (relevant fields):
```json
{
  "dc_plan": {
    "match_status": "points_based",
    "points_match_tiers": [...],
    "tenure_match_tiers": [],
    "match_template": "tiered",
    "match_tiers": [...],
    "match_cap_percent": 0.04
  }
}
```

## Validation Contract

Both `tenure_match_tiers` and `points_match_tiers` share the same validation rules:

1. **Non-empty**: At least 1 tier when the corresponding mode is active
2. **Start at zero**: First tier's min value must be 0
3. **Contiguous**: tier[N].max == tier[N+1].min (no gaps, no overlaps — contiguity implies both)
4. **Valid ranges**: max > min (or max is null for unbounded last tier)
5. **Valid rates**: 0 <= match_rate <= 1.0 (API accepts decimals; Pydantic stores as percentage 0-100; export handles conversion)
6. **Valid deferral**: 0 <= max_deferral_pct <= 1.0 (API accepts decimals; 0 is valid — effectively disables match for that tier)
