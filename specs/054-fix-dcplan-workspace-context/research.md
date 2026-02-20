# Research: Fix DC Plan Workspace Context Persistence

**Date**: 2026-02-19
**Branch**: `054-fix-dcplan-workspace-context`

## Research Findings

### 1. Root Cause Analysis

**Decision**: DCPlanAnalytics.tsx uses isolated `useState` for workspace management instead of the shared outlet context from Layout.tsx.

**Rationale**: Code inspection confirms:
- `DCPlanAnalytics.tsx` lines 91-94: Has its own `useState<Workspace[]>([])`, `useState<string>('')` for `selectedWorkspaceId`
- `DCPlanAnalytics.tsx` lines 133-143: Has its own `fetchWorkspaces()` function that independently calls `listWorkspaces()` API
- `DCPlanAnalytics.tsx` lines 107-109: `useEffect` fetches workspaces on mount, ignoring any previously selected workspace
- No `useOutletContext` import or usage anywhere in the file

**Alternatives considered**:
- URL-based workspace persistence (query params): Rejected - other pages don't use this pattern, would be inconsistent
- localStorage workspace persistence: Rejected - Layout already manages this centrally
- Custom context provider for DC Plan: Rejected - outlet context already exists and works

### 2. Established Pattern (ScenarioCostComparison.tsx)

**Decision**: Follow the exact pattern from ScenarioCostComparison.tsx, which correctly uses shared workspace context.

**Rationale**: ScenarioCostComparison.tsx demonstrates the working pattern:
- Line 156: `const { activeWorkspace } = useOutletContext<LayoutContextType>()`
- Lines 469-477: `useEffect` watches `activeWorkspace?.id` and calls `fetchScenarios(activeWorkspace.id)`
- No `useState` for workspace selection
- No workspace dropdown UI (uses global header selector)

**Alternatives considered**:
- ConfigContext pattern (separate React context): Rejected - adds unnecessary complexity for simple state consumption
- Props drilling from Layout: Rejected - outlet context is the established approach for route children

### 3. Route Structure Verification

**Decision**: DCPlanAnalytics is confirmed as a child route of Layout, meaning `useOutletContext` will work.

**Rationale**: `App.tsx` lines 80-92 show:
```
<Route path="/" element={<Layout />}>
  ...
  <Route path="analytics/dc-plan" element={<DCPlanAnalytics />} />
  ...
</Route>
```

### 4. Scope Boundary

**Decision**: This feature focuses exclusively on DCPlanAnalytics.tsx. Other components with similar issues (VestingAnalysis.tsx, AnalyticsDashboard.tsx) are out of scope.

**Rationale**: The spec and user request specifically target the DC Plan page. While VestingAnalysis.tsx has the same isolated workspace state pattern and AnalyticsDashboard.tsx has a hybrid approach, fixing those should be tracked as separate issues to keep changes focused and reviewable.

**Alternatives considered**:
- Fix all three components in one change: Rejected - increases blast radius and makes review harder
- Fix VestingAnalysis alongside DCPlan (both have identical pattern): Deferred - separate feature/PR

### 5. Redundant UI Removal

**Decision**: Remove the workspace dropdown selector from DCPlanAnalytics.tsx (lines 252-268).

**Rationale**: The Layout header already provides a global workspace selector visible on every page. Having a second selector on DC Plan is confusing and creates state synchronization issues. ScenarioCostComparison.tsx has no workspace selector, confirming the pattern.
