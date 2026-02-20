# Quickstart: Fix DC Plan Workspace Context Persistence

**Branch**: `054-fix-dcplan-workspace-context`
**Primary File**: `planalign_studio/components/DCPlanAnalytics.tsx`

## What This Fix Does

Replaces isolated workspace state management in DCPlanAnalytics with the shared workspace context from Layout, matching the pattern used by ScenarioCostComparison and other pages.

## Changes Summary

### DCPlanAnalytics.tsx

1. **Add** `useOutletContext` import and `LayoutContextType` import
2. **Add** `const { activeWorkspace } = useOutletContext<LayoutContextType>()` at component start
3. **Remove** `useState` for `workspaces` and `selectedWorkspaceId`
4. **Remove** `fetchWorkspaces()` function and its `useEffect` on mount
5. **Remove** workspace dropdown selector UI (lines ~252-268)
6. **Replace** all `selectedWorkspaceId` references with `activeWorkspace.id`
7. **Update** `useEffect` dependencies from `selectedWorkspaceId` to `activeWorkspace?.id`

## Reference Pattern

See `ScenarioCostComparison.tsx` line 156 for the correct `useOutletContext` usage.

## Verification

1. Launch PlanAlign Studio: `planalign studio`
2. Select a workspace on the Analysis page
3. Navigate to DC Plan analytics
4. Verify the workspace is still selected and scenarios load automatically
5. Switch workspaces via header dropdown while on DC Plan
6. Verify scenarios reload for the new workspace
