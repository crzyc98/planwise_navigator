# Quickstart: Vesting Year Selector

**Feature**: 040-vesting-year-selector
**Date**: 2026-02-09

## Overview

This feature adds a year selector dropdown to the Vesting Analysis page. The backend already supports year selection — this is primarily a frontend wiring task with one new backend endpoint.

## Prerequisites

```bash
source .venv/bin/activate
planalign health  # Verify environment
```

A completed multi-year simulation is needed for testing (e.g., `planalign simulate 2025-2027`).

## Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `planalign_api/services/vesting_service.py` | Add `get_available_years()` method | 1 |
| `planalign_api/routers/vesting.py` | Add `GET .../vesting/years` endpoint | 2 |
| `planalign_studio/services/api.ts` | Add `getScenarioYears()` function | 3 |
| `planalign_studio/components/VestingAnalysis.tsx` | Add year state, fetch effect, dropdown, wire to request | 4 |
| `tests/integration/test_vesting_api.py` | Add tests for years endpoint | 5 |

## Implementation Order

### Step 1: Backend — Add years query method

In `vesting_service.py`, add a method to `VestingService`:

```python
def get_available_years(self, workspace_id: str, scenario_id: str) -> Optional[dict]:
    """Get available simulation years for a scenario."""
    resolved = self.db_resolver.resolve(workspace_id, scenario_id)
    if not resolved.exists:
        return None
    conn = duckdb.connect(str(resolved.path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year ASC"
        ).fetchall()
        years = [row[0] for row in rows]
        return {"years": years, "default_year": max(years) if years else None}
    finally:
        conn.close()
```

### Step 2: Backend — Add API endpoint

In `vesting.py` router, add the GET endpoint following the existing `analyze_vesting` pattern.

### Step 3: Frontend — Add API client function

In `api.ts`, add `getScenarioYears()` following the existing `analyzeVesting()` pattern.

### Step 4: Frontend — Add year selector to VestingAnalysis.tsx

- Add state: `selectedYear`, `availableYears`, `loadingYears`
- Add `useEffect` to fetch years when `selectedScenarioId` changes
- Add dropdown between scenario row and Analyze button
- Include `simulation_year: selectedYear` in the analysis request

### Step 5: Tests

Add integration tests for the new years endpoint (valid scenario, missing scenario, empty database).

## Verification

```bash
# Start the API
planalign studio --api-only

# Test years endpoint
curl http://localhost:8000/api/workspaces/{ws_id}/scenarios/{sc_id}/analytics/vesting/years

# Test analysis with year parameter
curl -X POST http://localhost:8000/api/workspaces/{ws_id}/scenarios/{sc_id}/analytics/vesting \
  -H "Content-Type: application/json" \
  -d '{"current_schedule":{"schedule_type":"graded_5_year","name":"5-Year Graded"},"proposed_schedule":{"schedule_type":"cliff_3_year","name":"3-Year Cliff"},"simulation_year":2025}'
```
