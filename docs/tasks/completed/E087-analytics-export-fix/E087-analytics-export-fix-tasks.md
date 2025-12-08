# E087: Task Checklist

**Last Updated**: 2025-12-08

## Part 1: Fix Export Bug

- [x] 1.1 Update `getResultsExportUrl()` in `api.ts` to accept `workspaceId`
  - Changed signature from `(scenarioId, format)` to `(workspaceId, scenarioId, format)`
  - Updated URL to use workspace-scoped endpoint
- [x] 1.2 Update `handleExport()` in `AnalyticsDashboard.tsx` to pass workspace ID
  - Already completed in previous session (line 196-197)
- [x] 1.3 Add workspace-scoped export endpoint in `scenarios.py`
  - Added `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/results/export`
  - Endpoint verifies workspace and scenario exist before export
  - Searches multiple file naming patterns for results
- [x] 1.4 Test export functionality
  - Verified endpoint appears in OpenAPI schema
  - Frontend builds successfully

## Part 2: Display File Paths

- [x] 2.1 Add `storage_path` to `RunDetails` response in backend
  - Added field to `RunDetails` model in `simulation.py`
  - Updated `get_run_details()` in `simulations.py` to include path
- [x] 2.2 Update `RunDetails` interface in `api.ts`
  - Added `storage_path: string | null` field
- [x] 2.3 Add storage location display to `SimulationDetail.tsx`
  - Added FolderOpen icon import
  - Added "Storage Location" section after Run Info

## Part 3: Finalize

- [x] 3.1 Create PR
  - PR #78 created: https://github.com/crzyc98/planwise_navigator/pull/78
- [ ] 3.2 Manual testing in UI
- [ ] 3.3 Merge PR

---

## Progress Notes

### 2025-12-08
- Created task documentation files
- Completed 1.1: Updated `getResultsExportUrl()` in `api.ts`
- Completed 1.2: `handleExport()` was already passing workspace ID
- Completed 1.3: Added new workspace-scoped export endpoint to `scenarios.py`
- Completed 2.1-2.3: Added storage_path to backend and frontend
- All code changes complete, verified with API schema check and frontend build

### 2025-12-08 (Session 2)
- Fixed export endpoint to search `runs/{run_id}/` directory (not just legacy `results/`)
- Improved export filename: `{workspace}_{scenario}_results_{YYYYMMDD}.xlsx`
- Fixed blank UI values (Total Events, Completed timestamp) by updating `get_run_details()` to search:
  1. `runs/{last_run_id}/run_metadata.json` (by run ID)
  2. Most recent `runs/*/run_metadata.json` (fallback)
  3. Legacy `results/run_metadata.json` (migration path)
- API verification:
  - Completed timestamp: ✅ Now shows from run_metadata
  - Total Events: ✅ Now shows `events_generated` from run_metadata
  - Storage Path: ✅ Displays correctly
  - Export: ✅ Works with descriptive filename
- Note: Final Headcount still shows `--` because `run_metadata.json` doesn't include this field
  (would require simulation service update to write `final_headcount` - separate issue)
