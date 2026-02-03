# API Contracts: Vesting Hours Requirement Toggle

**Feature**: 030-vesting-hours-toggle
**Date**: 2026-01-29

## No New Contracts Required

This feature uses existing API contracts. No modifications to backend API needed.

### Existing Endpoint Used

**Endpoint**: `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting`

**Existing Request Schema** (already supports hours fields):
```json
{
  "current_schedule": {
    "schedule_type": "string (VestingScheduleType enum)",
    "name": "string",
    "require_hours_credit": "boolean (optional, default: false)",
    "hours_threshold": "integer (optional, default: 1000, range: 0-2080)"
  },
  "proposed_schedule": {
    "schedule_type": "string (VestingScheduleType enum)",
    "name": "string",
    "require_hours_credit": "boolean (optional, default: false)",
    "hours_threshold": "integer (optional, default: 1000, range: 0-2080)"
  },
  "simulation_year": "integer (optional)"
}
```

**Response** includes full `VestingScheduleConfig` for both schedules, enabling UI to display the hours configuration used in the analysis.

### TypeScript Types (Already Exist)

Located in `planalign_studio/services/api.ts:1033-1038`:

```typescript
export interface VestingScheduleConfig {
  schedule_type: VestingScheduleType;
  name: string;
  require_hours_credit?: boolean;
  hours_threshold?: number;
}
```

### Backend Model (Already Exists)

Located in `planalign_api/models/vesting.py:38-52`:

```python
class VestingScheduleConfig(BaseModel):
    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    require_hours_credit: bool = Field(default=False)
    hours_threshold: int = Field(default=1000, ge=0, le=2080)
```

## Conclusion

All necessary API infrastructure is in place. This feature only requires frontend UI changes to expose the existing fields.
