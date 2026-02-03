# Data Model: Vesting Hours Requirement Toggle

**Feature**: 030-vesting-hours-toggle
**Date**: 2026-01-29

## Overview

This feature uses existing data structures. No new entities or API contracts required.

## Existing Entities (No Changes)

### VestingScheduleConfig (TypeScript - planalign_studio/services/api.ts)

```typescript
export interface VestingScheduleConfig {
  schedule_type: VestingScheduleType;
  name: string;
  require_hours_credit?: boolean;  // Already exists - USED BY THIS FEATURE
  hours_threshold?: number;         // Already exists - USED BY THIS FEATURE
}
```

**Field Details**:
| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `require_hours_credit` | boolean | false | N/A | Toggle for hours requirement |
| `hours_threshold` | number | 1000 | 0-2080 | Minimum annual hours for credit |

### VestingScheduleConfig (Python - planalign_api/models/vesting.py)

```python
class VestingScheduleConfig(BaseModel):
    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    require_hours_credit: bool = Field(
        default=False,
        description="If true, employees must meet hours threshold for vesting credit"
    )
    hours_threshold: int = Field(
        default=1000,
        ge=0,
        le=2080,
        description="Minimum annual hours for vesting credit (default: 1000)"
    )
```

### VestingAnalysisResponse (TypeScript - planalign_studio/services/api.ts)

```typescript
export interface VestingAnalysisResponse {
  scenario_id: string;
  scenario_name: string;
  current_schedule: VestingScheduleConfig;   // Contains hours config
  proposed_schedule: VestingScheduleConfig;  // Contains hours config
  summary: VestingAnalysisSummary;
  by_tenure_band: TenureBandSummary[];
  employee_details: EmployeeVestingDetail[];
}
```

The response already includes the full `VestingScheduleConfig` with hours fields, so results display can access `analysisResult.current_schedule.require_hours_credit` and `analysisResult.current_schedule.hours_threshold`.

## Component State Model

### Current State (VestingAnalysis.tsx:115-116)

```typescript
const [currentSchedule, setCurrentSchedule] = useState<VestingScheduleConfig | null>(null);
const [proposedSchedule, setProposedSchedule] = useState<VestingScheduleConfig | null>(null);
```

### Required State Updates

No new state variables needed. The existing state type (`VestingScheduleConfig | null`) already supports the optional fields.

**State Flow**:
1. User selects schedule type → creates config with `schedule_type` and `name`
2. User toggles hours requirement → adds `require_hours_credit: true`
3. User adjusts threshold → adds `hours_threshold: <value>`
4. User clicks Analyze → full config sent to API
5. API returns response with configs echoed back → display in results

## Validation Rules

| Field | Rule | UI Enforcement |
|-------|------|----------------|
| `hours_threshold` | 0 ≤ value ≤ 2080 | HTML input `min="0" max="2080"` |
| `hours_threshold` | integer only | HTML input `type="number" step="1"` |
| `require_hours_credit` | boolean | Checkbox (inherently boolean) |

## Contracts

No new API contracts required. Existing endpoint already accepts hours fields:

**Endpoint**: `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting`

**Request Body** (unchanged):
```json
{
  "current_schedule": {
    "schedule_type": "graded_5_year",
    "name": "5-Year Graded",
    "require_hours_credit": true,
    "hours_threshold": 1000
  },
  "proposed_schedule": {
    "schedule_type": "cliff_3_year",
    "name": "3-Year Cliff",
    "require_hours_credit": false
  }
}
```

**Response** (unchanged - already includes full config):
```json
{
  "current_schedule": {
    "schedule_type": "graded_5_year",
    "name": "5-Year Graded",
    "require_hours_credit": true,
    "hours_threshold": 1000
  },
  "proposed_schedule": { ... },
  "summary": { ... },
  ...
}
```
