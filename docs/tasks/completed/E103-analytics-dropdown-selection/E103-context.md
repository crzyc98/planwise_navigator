# E103: Context and Key Files

## Key Files

| File | Purpose |
|------|---------|
| `planalign_studio/components/AnalyticsDashboard.tsx` | Analytics page with workspace/scenario dropdowns |
| `planalign_studio/components/SimulationDetail.tsx` | Results page with "View Analytics" button |
| `planalign_studio/services/api.ts` | API calls including `getRunDetails()` |

## Data Flow

1. **SimulationDetail.tsx** - Button passes `?scenario={scenario_id}` to analytics
2. **AnalyticsDashboard.tsx** - Reads URL param, calls `getRunDetails()` to get workspace_id
3. **API** - Returns `RunDetails` with `workspace_id` and `workspace_name`
4. **State Updates** - Sets workspace and scenario selections
5. **fetchWorkspaces()** - Loads workspace list for dropdown

## Related Tasks

- **E094** (PR #88) - Previous fix for analytics workspace selection (context fallback)

## Decisions

- Used `skipAutoSelect` boolean parameter approach (simpler than passing workspace ID)
- Preserves backward compatibility - default behavior unchanged
