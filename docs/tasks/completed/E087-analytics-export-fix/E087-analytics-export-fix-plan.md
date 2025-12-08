# E087: Analytics Dashboard Export Fix & File Path Display

**Issue**: GitHub #77
**Branch**: `feature/E087-analytics-export-fix`
**Last Updated**: 2025-12-08

## Issue Summary
The Analytics Dashboard shows correct scenario data but Export Report fails with "Export file not found for scenario. Run the simulation first to generate results" even when results exist. Additionally, users want to see file paths in the Simulation Control Center.

## Root Cause Analysis

### Export Bug
1. **Export URL Construction** (`api.ts:350-352`): `getResultsExportUrl()` only passes `scenarioId`, not `workspaceId`
2. **Backend Search** (`simulations.py:439`): `_find_scenario_and_workspace()` must search ALL workspaces to find the scenario
3. **File Path Resolution** (`simulations.py:447-448`): Looks for results in `workspaces/{workspace_id}/scenarios/{scenario_id}/results/`
4. **Likely Issue**: The `_find_scenario_and_workspace()` function may fail to find the scenario or find results in wrong location

### Current State Flow
- `AnalyticsDashboard.tsx:83`: Gets `scenarioIdFromUrl` from URL params
- `AnalyticsDashboard.tsx:99-121`: Initializes from URL, fetches `workspace_id` via `getRunDetails()`
- `AnalyticsDashboard.tsx:195-198`: `handleExport()` constructs URL using only `selectedScenarioId`
- Export opens new tab: `window.open(url, '_blank')` - no error handling

## Implementation Plan

### Part 1: Fix Export (Primary Bug)

#### 1.1 Update Frontend Export to Include Workspace ID
**File**: `planalign_studio/services/api.ts`
- Change `getResultsExportUrl(scenarioId, format)` to `getResultsExportUrl(workspaceId, scenarioId, format)`
- Update URL to use workspace-scoped endpoint

#### 1.2 Update AnalyticsDashboard Export Handler
**File**: `planalign_studio/components/AnalyticsDashboard.tsx`
- Update `handleExport()` (line 194-198) to pass `selectedWorkspaceId`

#### 1.3 Add Backend Endpoint with Workspace Context
**File**: `planalign_api/routers/simulations.py`
- Add new endpoint: `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/results/export`
- Keep existing endpoint for backwards compatibility

### Part 2: Display File Paths in UI

#### 2.1 Add Storage Path to RunDetails Response
**File**: `planalign_api/routers/simulations.py`
- In `get_run_details()` endpoint, add `storage_path` field showing scenario directory

#### 2.2 Update Frontend Types
**File**: `planalign_studio/services/api.ts`
- Add `storage_path?: string` to `RunDetails` interface

#### 2.3 Display File Paths in SimulationDetail
**File**: `planalign_studio/components/SimulationDetail.tsx`
- Add a "Storage Location" section showing:
  - Scenario directory path
  - Database file path (from artifacts)
  - Results directory path

## Acceptance Criteria
- [ ] Export Report downloads Excel file successfully
- [ ] No "Export file not found" error when results exist
- [ ] Storage paths displayed in Simulation Control Center
- [ ] Works correctly across multiple workspaces
