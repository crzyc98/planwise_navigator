# E104: Context and Key Files

## Last Updated
2024-12-11

## Key Files

### Backend (planalign_api/)
| File | Purpose | Action |
|------|---------|--------|
| `models/analytics.py` | Pydantic models for DC Plan analytics | Add fields |
| `services/analytics_service.py` | Database queries for analytics | Update queries |
| `routers/analytics.py` | API endpoints | No changes needed |

### Frontend (planalign_studio/)
| File | Purpose | Action |
|------|---------|--------|
| `services/api.ts` | TypeScript API types | Update interfaces |
| `components/ScenarioCostComparison.tsx` | Main comparison page | NEW |
| `App.tsx` | React Router routes | Add route |
| `components/Layout.tsx` | Sidebar navigation | Add nav item |

### Database Schema
| Table | Columns Used |
|-------|--------------|
| `fct_workforce_snapshot` | `current_deferral_rate`, `is_enrolled_flag`, `employer_match_amount`, `employer_core_amount`, `employment_status`, `simulation_year` |

## Existing API Endpoint
The backend already has a comparison endpoint that we'll use:
```
GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare?scenarios=id1,id2
```

Returns `DCPlanComparisonResponse` with analytics for each scenario.

## Key Decisions

1. **Navigation**: New top-level page at `/compare` (not under /analytics)
2. **Display**: Side-by-side cards with variance highlighting
3. **Granularity**: Year-by-year breakdown with totals
4. **Missing Data**: Need to add `average_deferral_rate` to existing models

## Styling Patterns (from existing components)
- Cards: `bg-white rounded-xl shadow-sm border border-gray-200 p-6`
- Headers: `text-lg font-semibold text-gray-800`
- Positive variance: `text-green-600`
- Negative variance: `text-red-600`
- Fidelity green: `#00853F`

## Dependencies
- lucide-react: For `Scale` icon in navigation
- Existing `compareDCPlanAnalytics()` API function
