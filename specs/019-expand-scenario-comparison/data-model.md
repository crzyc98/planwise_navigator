# Data Model: Expand Scenario Comparison Limit

**Feature**: 019-expand-scenario-comparison
**Date**: 2026-01-20

## Overview

This feature is a frontend-only change. No backend data model changes are required.

## Existing Entities (Unchanged)

### Scenario Selection State

The component manages selection state using React hooks:

```typescript
// Current state shape (unchanged)
const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
const [anchorScenarioId, setAnchorScenarioId] = useState<string | null>(null);
```

- `selectedScenarioIds`: Array of scenario IDs currently selected for comparison
  - **Current constraint**: `length <= 5`
  - **New constraint**: `length <= 6`
- `anchorScenarioId`: The baseline scenario for variance calculations (must be in `selectedScenarioIds`)

### API Response (Unchanged)

The `compareDCPlanAnalytics` API response structure remains unchanged:

```typescript
interface DCPlanComparisonResponse {
  scenarios: Record<string, DCPlanAnalytics>;
  // ... other fields
}
```

The API accepts any number of scenario IDs and returns comparison data for all requested scenarios.

## New Constants

### MAX_SCENARIO_SELECTION

```typescript
// In constants.ts
export const MAX_SCENARIO_SELECTION = 6;
```

### Extended Color Palette

```typescript
// In constants.ts
export const COLORS = {
  // ... existing properties
  charts: ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#E91E63']
};
```

## State Transitions

### Selection State Machine

```
┌─────────────────────┐
│ selected.length < 6 │ ←──────────────────────┐
└─────────────────────┘                        │
         │                                      │
         │ select scenario                      │ deselect scenario
         ▼                                      │
┌─────────────────────┐                        │
│ selected.length = 6 │ ────────────────────────┘
│ (unchecked disabled)│
└─────────────────────┘
         │
         │ attempt to select 7th
         ▼
┌─────────────────────┐
│ No-op (disabled)    │
│ Tooltip shown       │
└─────────────────────┘
```

## Validation Rules

| Rule | Current | New |
|------|---------|-----|
| Max scenarios | 5 | 6 |
| Min scenarios | 1 | 1 (unchanged) |
| Anchor must be selected | Yes | Yes (unchanged) |
| All scenarios must be completed | Yes | Yes (unchanged) |

## No Database Changes

This feature does not modify:
- DuckDB schema
- dbt models
- Backend API endpoints
- Event store structure
