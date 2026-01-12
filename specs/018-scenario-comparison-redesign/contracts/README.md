# API Contracts: Scenario Cost Comparison Redesign

**Feature**: 018-scenario-comparison-redesign

## No New Contracts Required

This feature uses existing API endpoints defined in `planalign_studio/services/api.ts`. No new API contracts are needed.

### Existing Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workspaces` | GET | List all workspaces |
| `/api/workspaces/{id}/scenarios` | GET | List scenarios in workspace |
| `/api/workspaces/{id}/analytics/dc-plan/compare` | GET | Compare DC plan analytics |

### TypeScript Types

See `planalign_studio/services/api.ts` lines 772-861 for:
- `DCPlanComparisonResponse`
- `DCPlanAnalytics`
- `ContributionYearSummary`
- `Workspace`
- `Scenario`
