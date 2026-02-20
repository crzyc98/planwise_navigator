# Data Model: Fix DC Plan Workspace Context Persistence

**Date**: 2026-02-19
**Branch**: `054-fix-dcplan-workspace-context`

## Overview

This is a frontend state management fix. No database, API, or backend data model changes are required. The data model below documents the **frontend state transitions** affected by this change.

## Entities

### Workspace (unchanged)

Managed by Layout.tsx. Shared via outlet context.

| Attribute | Type | Source |
|-----------|------|--------|
| id | string | API (`listWorkspaces`) |
| name | string | API |
| description | string | API |
| created_at | string | API |

### Active Workspace State

**Before (broken)**: Two independent sources of truth

| Component | State Variable | Source | Sync |
|-----------|---------------|--------|------|
| Layout.tsx | `activeWorkspace` | Context provider | Global |
| DCPlanAnalytics.tsx | `selectedWorkspaceId` | Local useState | Isolated |

**After (fixed)**: Single source of truth

| Component | State Variable | Source | Sync |
|-----------|---------------|--------|------|
| Layout.tsx | `activeWorkspace` | Context provider | Global |
| DCPlanAnalytics.tsx | reads `activeWorkspace` | useOutletContext | Shared |

### DCPlanAnalytics Local State (retained)

These state variables remain as local component state since they are page-specific UI state, not cross-page shared state:

| Variable | Type | Purpose |
|----------|------|---------|
| scenarios | Scenario[] | Scenarios for the active workspace |
| selectedScenarioIds | string[] | User's scenario selection within DC Plan |
| analytics | DCPlanAnalyticsData | null | Single-scenario analytics response |
| comparisonData | DCPlanComparisonResponse | null | Multi-scenario comparison response |
| loading | boolean | Analytics loading state |
| loadingScenarios | boolean | Scenario list loading state |
| error | string | null | Error message display |
| comparisonMode | boolean | Single vs comparison mode toggle |

## State Transitions

### Workspace Change Event

```
Layout: setActiveWorkspace(newWorkspace)
  └─► DCPlanAnalytics: useEffect detects activeWorkspace.id change
       ├─► Clear selectedScenarioIds → []
       ├─► Clear analytics → null
       ├─► Clear comparisonData → null
       └─► fetchScenarios(activeWorkspace.id)
            └─► setScenarios(result)
```

### Page Navigation (to DC Plan)

```
User navigates to /analytics/dc-plan
  └─► DCPlanAnalytics mounts
       └─► useOutletContext reads activeWorkspace (already set)
            └─► useEffect fires with activeWorkspace.id
                 └─► fetchScenarios(activeWorkspace.id)
```
