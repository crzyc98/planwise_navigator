# E103: Analytics Page Dropdown Selection Fix

## Problem Summary

When clicking "View Analytics" button from the simulation results page, the analytics page dropdowns don't show the correct workspace and scenario selected, even though the URL contains `?scenario={scenario_id}`.

## Root Cause Analysis

### React State Race Condition in `AnalyticsDashboard.tsx`

The initialization flow in `useEffect` (lines 107-129):

```tsx
const initFromUrl = async () => {
  if (scenarioIdFromUrl && !initializedFromUrl) {
    const details = await getRunDetails(scenarioIdFromUrl);  // Async call
    if (details.workspace_id) {
      setSelectedWorkspaceId(details.workspace_id);  // State update 1
      setSelectedScenarioId(scenarioIdFromUrl);      // State update 2
      setInitializedFromUrl(true);                   // State update 3
      fetchWorkspaces();  // BUG: Not awaited, reads stale state
      return;
    }
  }
  fetchWorkspaces();
};
```

The problem is in `fetchWorkspaces()` (lines 151-163):

```tsx
const fetchWorkspaces = async () => {
  const data = await listWorkspaces();
  setWorkspaces(data);
  // This check uses STALE closure value of selectedWorkspaceId
  if (data.length > 0 && !selectedWorkspaceId) {  // BUG: Sees '' not the new ID
    setSelectedWorkspaceId(preferredWorkspace?.id || data[0].id);  // Overwrites!
  }
};
```

**Due to React's batched state updates**, when `fetchWorkspaces()` executes, `selectedWorkspaceId` in its closure is still the old value (empty string), not the newly set workspace ID.

## Fix Implementation

Add `skipAutoSelect` parameter to `fetchWorkspaces()` and pass `true` when initializing from URL.

## Files Modified

| File | Change |
|------|--------|
| `planalign_studio/components/AnalyticsDashboard.tsx` | Add skipAutoSelect param, pass true from URL init |
