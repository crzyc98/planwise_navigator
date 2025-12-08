# E087: Context & Key Files

**Last Updated**: 2025-12-08

## Key Files

### Frontend
| File | Purpose | Key Lines |
|------|---------|-----------|
| `planalign_studio/services/api.ts` | API service layer | 350-352: `getResultsExportUrl()` |
| `planalign_studio/components/AnalyticsDashboard.tsx` | Analytics page | 83-141: State init, 194-198: `handleExport()` |
| `planalign_studio/components/SimulationDetail.tsx` | Scenario detail view | Displays artifacts, run details |

### Backend
| File | Purpose | Key Lines |
|------|---------|-----------|
| `planalign_api/routers/simulations.py` | Simulation endpoints | 428-485: `export_results()` endpoint |
| `planalign_api/services/workspace_storage.py` | File storage management | Scenario path resolution |

## Architecture Decisions

### Decision 1: Workspace-Scoped Export Endpoint
**Choice**: Add new endpoint `/api/workspaces/{workspace_id}/scenarios/{scenario_id}/results/export`
**Rationale**:
- Eliminates ambiguity in multi-workspace environments
- Avoids searching all workspaces to find scenario
- Matches pattern used by other workspace-scoped endpoints

### Decision 2: Keep Existing Endpoint for Backwards Compatibility
**Choice**: Don't remove `/api/scenarios/{scenario_id}/results/export`
**Rationale**:
- May be used by other integrations
- Can deprecate later once all callers updated

### Decision 3: Display Storage Paths in SimulationDetail
**Choice**: Add storage path info to SimulationDetail.tsx rather than AnalyticsDashboard
**Rationale**:
- SimulationDetail already shows artifacts with paths
- More contextually appropriate for file system information
- Keeps AnalyticsDashboard focused on analytics

## State Flow

```
URL: /analytics?scenario={id}
       ↓
AnalyticsDashboard.tsx
       ↓
useEffect → getRunDetails(scenarioId) → gets workspace_id
       ↓
setSelectedWorkspaceId(workspace_id)
setSelectedScenarioId(scenarioId)
       ↓
Export Button Click → handleExport('excel')
       ↓
getResultsExportUrl(workspaceId, scenarioId, 'excel')
       ↓
window.open(url, '_blank')
       ↓
Backend: /api/workspaces/{workspace_id}/scenarios/{scenario_id}/results/export
       ↓
FileResponse with Excel file
```

## File Storage Structure

```
workspaces_root/
├── {workspace_id}/
│   ├── workspace.json
│   ├── base_config.yaml
│   └── scenarios/
│       └── {scenario_id}/
│           ├── scenario.json
│           ├── scenario_config.yaml
│           └── results/
│               ├── {scenario_name}_results.xlsx
│               ├── run_metadata.json
│               └── config.yaml
```
