# Quick Start: NDT 401(a)(4) & 415 Tests

**Branch**: `051-ndt-401a4-415-tests` | **Date**: 2026-02-19

## Prerequisites

- Completed simulation with at least 1 year of data
- `config_irs_limits` seed with `annual_additions_limit` column populated
- Workspace with at least one scenario in "completed" status

## Run 401(a)(4) Test

### Via API

```bash
# Basic ratio test (NEC-only, default)
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/401a4?scenarios={scenario_id}&year=2025"

# Include match in contribution rate
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/401a4?scenarios={scenario_id}&year=2025&include_match=true"

# With employee-level detail
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/401a4?scenarios={scenario_id}&year=2025&include_employees=true"

# Multi-scenario comparison
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/401a4?scenarios=baseline,high_growth&year=2025"
```

### Via PlanAlign Studio

1. Launch: `planalign studio`
2. Open workspace → Navigate to "NDT Testing"
3. Select test type: "401(a)(4) General Test"
4. Choose scenario(s) and year
5. Click "Run Test"

## Run 415 Test

### Via API

```bash
# Default 95% warning threshold
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/415?scenarios={scenario_id}&year=2025"

# Custom warning threshold (90%)
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/415?scenarios={scenario_id}&year=2025&warning_threshold=0.90"

# With per-participant detail
curl "http://localhost:8000/api/workspaces/{workspace_id}/analytics/ndt/415?scenarios={scenario_id}&year=2025&include_employees=true"
```

## Expected Output

### 401(a)(4) — Passing Example

```json
{
  "test_type": "401a4",
  "year": 2025,
  "results": [{
    "scenario_id": "baseline",
    "test_result": "pass",
    "applied_test": "ratio",
    "hce_average_rate": 0.08,
    "nhce_average_rate": 0.06,
    "ratio": 0.75,
    "margin": 0.05,
    "service_risk_flag": false
  }]
}
```

### 415 — With Breach Example

```json
{
  "test_type": "415",
  "year": 2025,
  "results": [{
    "scenario_id": "baseline",
    "test_result": "fail",
    "breach_count": 2,
    "at_risk_count": 5,
    "max_utilization_pct": 1.014,
    "annual_additions_limit": 70000
  }]
}
```

## Key Files

| Component | Path |
|-----------|------|
| API endpoints | `planalign_api/routers/ndt.py` |
| Service logic | `planalign_api/services/ndt_service.py` |
| IRS limits seed | `dbt/seeds/config_irs_limits.csv` |
| Frontend component | `planalign_studio/components/NDTTesting.tsx` |
| API client | `planalign_studio/services/api.ts` |
| Unit tests | `tests/test_ndt_401a4.py`, `tests/test_ndt_415.py` |
