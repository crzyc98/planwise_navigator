# E094: Analytics Page Workspace Selection - Plan

## Problem
When clicking the Analytics nav link in the sidebar after running a simulation, the page defaults to the first workspace in the environment with no simulation selected. Users expect it to show the workspace/simulation they were just working with.

## Solution
Extend the Layout context to track `lastRunScenarioId`, set it when a simulation completes, and have AnalyticsDashboard use it as a fallback when no URL parameter is present.

## Implementation
1. **Layout.tsx** - Add `lastRunScenarioId` and `setLastRunScenarioId` to context
2. **SimulationControl.tsx** - Set `lastRunScenarioId` when simulation completes
3. **AnalyticsDashboard.tsx** - Read from context, prefer context workspace

## Edge Cases
- URL parameter always takes precedence over context (preserves "View Analytics" button flow)
- Page refresh clears context (falls back to defaults - acceptable)
- Context workspace preferred over first workspace in list
