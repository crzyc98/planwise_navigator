# Quickstart: Vesting Analysis

**Feature Branch**: `025-vesting-analysis`
**Date**: 2026-01-21

## Overview

This quickstart guide provides developers with the essential information to implement the Vesting Analysis feature. For complete specifications, see:
- [spec.md](./spec.md) - Feature requirements
- [data-model.md](./data-model.md) - Data models
- [contracts/openapi.yaml](./contracts/openapi.yaml) - API specification

---

## Implementation Checklist

### Backend (Python/FastAPI)

- [ ] Create `planalign_api/models/vesting.py` with Pydantic models
- [ ] Create `planalign_api/services/vesting_service.py` with calculation logic
- [ ] Create `planalign_api/routers/vesting.py` with API endpoints
- [ ] Register router in `planalign_api/main.py`
- [ ] Add unit tests in `tests/unit/test_vesting_service.py`
- [ ] Add integration tests in `tests/integration/test_vesting_api.py`

### Frontend (TypeScript/React)

- [ ] Add TypeScript types to `planalign_studio/services/api.ts`
- [ ] Add API functions to `planalign_studio/services/api.ts`
- [ ] Create `planalign_studio/components/VestingAnalysis.tsx`
- [ ] Add route in `planalign_studio/App.tsx`
- [ ] Add navigation link in `planalign_studio/components/Layout.tsx`

---

## Key Code Patterns

### 1. Vesting Calculation Core Logic

```python
from decimal import Decimal
from typing import Optional

# Pre-defined schedules (8 total)
VESTING_SCHEDULES = {
    "immediate": {0: 1.0},
    "cliff_2_year": {0: 0.0, 1: 0.0, 2: 1.0},
    "cliff_3_year": {0: 0.0, 1: 0.0, 2: 0.0, 3: 1.0},
    "cliff_4_year": {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 1.0},
    "qaca_2_year": {0: 0.0, 1: 0.0, 2: 1.0},
    "graded_3_year": {0: 0.0, 1: 0.3333, 2: 0.6667, 3: 1.0},
    "graded_4_year": {0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0},
    "graded_5_year": {0: 0.0, 1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 1.0},
}


def get_vesting_percentage(
    schedule_type: str,
    tenure_years: float,
    annual_hours: Optional[int] = None,
    require_hours: bool = False,
    hours_threshold: int = 1000
) -> Decimal:
    """
    Calculate vesting percentage for a given schedule and tenure.

    Args:
        schedule_type: One of the pre-defined schedule types
        tenure_years: Years of service (will be truncated to int)
        annual_hours: Hours worked in final year
        require_hours: If True, check hours threshold
        hours_threshold: Minimum hours for vesting credit

    Returns:
        Vesting percentage as Decimal (0.0 to 1.0)
    """
    schedule = VESTING_SCHEDULES.get(schedule_type)
    if not schedule:
        raise ValueError(f"Unknown schedule type: {schedule_type}")

    # Apply hours credit adjustment
    effective_tenure = int(tenure_years)
    if require_hours and annual_hours is not None:
        if annual_hours < hours_threshold:
            effective_tenure = max(0, effective_tenure - 1)

    # Clamp to max year in schedule
    max_year = max(schedule.keys())
    effective_tenure = min(effective_tenure, max_year)

    return Decimal(str(schedule.get(effective_tenure, schedule[max_year])))


def calculate_forfeiture(
    total_contributions: Decimal,
    vesting_pct: Decimal
) -> Decimal:
    """Calculate forfeiture amount."""
    unvested = Decimal("1.0") - vesting_pct
    return (total_contributions * unvested).quantize(Decimal("0.01"))
```

### 2. SQL Query for Terminated Employees

```sql
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure,
    tenure_band,
    employer_match_amount,
    employer_core_amount,
    total_employer_contributions,
    annual_hours_worked
FROM fct_workforce_snapshot
WHERE simulation_year = :year
  AND UPPER(employment_status) = 'TERMINATED'
  AND total_employer_contributions > 0
ORDER BY total_employer_contributions DESC
```

### 3. Service Pattern (following AnalyticsService)

```python
from typing import Optional
import duckdb

from ..models.vesting import VestingAnalysisRequest, VestingAnalysisResponse
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver


class VestingService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def analyze_vesting(
        self,
        workspace_id: str,
        scenario_id: str,
        scenario_name: str,
        request: VestingAnalysisRequest
    ) -> Optional[VestingAnalysisResponse]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return None

        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            # Get final year if not specified
            year = request.simulation_year or self._get_final_year(conn)

            # Query terminated employees
            employees = self._get_terminated_employees(conn, year)

            # Calculate vesting for each employee
            details = self._calculate_employee_details(
                employees, request.current_schedule, request.proposed_schedule
            )

            # Aggregate results
            summary = self._build_summary(details, year)
            by_tenure_band = self._aggregate_by_tenure_band(details)

            return VestingAnalysisResponse(
                scenario_id=scenario_id,
                scenario_name=scenario_name,
                current_schedule=request.current_schedule,
                proposed_schedule=request.proposed_schedule,
                summary=summary,
                by_tenure_band=by_tenure_band,
                employee_details=details
            )
        finally:
            conn.close()
```

### 4. FastAPI Router

```python
from fastapi import APIRouter, Depends, HTTPException

from ..models.vesting import (
    VestingAnalysisRequest,
    VestingAnalysisResponse,
    VestingScheduleListResponse,
)
from ..services.vesting_service import VestingService

router = APIRouter()


@router.get("/vesting/schedules", response_model=VestingScheduleListResponse)
async def list_vesting_schedules():
    """List all pre-defined vesting schedules."""
    return VestingService.get_schedule_list()


@router.post(
    "/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting",
    response_model=VestingAnalysisResponse
)
async def analyze_vesting(
    workspace_id: str,
    scenario_id: str,
    request: VestingAnalysisRequest,
    vesting_service: VestingService = Depends(get_vesting_service)
):
    """Run vesting analysis comparing two schedules."""
    # Get scenario name
    scenario = await get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    result = vesting_service.analyze_vesting(
        workspace_id, scenario_id, scenario.name, request
    )
    if not result:
        raise HTTPException(status_code=404, detail="Simulation data not found")

    return result
```

### 5. Frontend API Functions

```typescript
// Add to planalign_studio/services/api.ts

export async function listVestingSchedules(): Promise<VestingScheduleListResponse> {
  const response = await fetch(`${API_BASE}/api/vesting/schedules`);
  return handleResponse<VestingScheduleListResponse>(response);
}

export async function analyzeVesting(
  workspaceId: string,
  scenarioId: string,
  request: VestingAnalysisRequest
): Promise<VestingAnalysisResponse> {
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/scenarios/${scenarioId}/analytics/vesting`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  );
  return handleResponse<VestingAnalysisResponse>(response);
}
```

---

## Testing Commands

```bash
# Run backend unit tests
pytest tests/unit/test_vesting_service.py -v

# Run backend integration tests
pytest tests/integration/test_vesting_api.py -v

# Run all vesting-related tests
pytest -k vesting -v

# Test API manually
curl -X GET "http://localhost:8000/api/vesting/schedules"

curl -X POST "http://localhost:8000/api/workspaces/ws_123/scenarios/baseline/analytics/vesting" \
  -H "Content-Type: application/json" \
  -d '{
    "current_schedule": {"schedule_type": "graded_5_year", "name": "5-Year Graded"},
    "proposed_schedule": {"schedule_type": "cliff_3_year", "name": "3-Year Cliff"}
  }'
```

---

## Navigation Updates

### Add Route (App.tsx)

```tsx
import VestingAnalysis from './components/VestingAnalysis';

// Inside Routes
<Route path="analytics/vesting" element={<VestingAnalysis />} />
```

### Add Nav Link (Layout.tsx)

```tsx
// Add to imports
import { Scale } from 'lucide-react';

// Add to navigation section (after DC Plan)
<NavItem to="/analytics/vesting" icon={<Scale size={20} />} label="Vesting" />
```

---

## Reference Files

| Purpose | File |
|---------|------|
| API Pattern | `planalign_api/services/analytics_service.py` |
| Router Pattern | `planalign_api/routers/analytics.py` |
| Model Pattern | `planalign_api/models/analytics.py` |
| Component Pattern | `planalign_studio/components/DCPlanAnalytics.tsx` |
| API Client Pattern | `planalign_studio/services/api.ts` |
