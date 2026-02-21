# Quickstart: DC Plan Comparison Charts

**Feature Branch**: `057-dc-comparison-charts`

## Prerequisites

- Node.js (for frontend builds)
- Existing PlanAlign Studio development environment
- At least 2 completed simulation scenarios in a workspace

## Setup

```bash
git checkout 057-dc-comparison-charts

# Install frontend dependencies
cd planalign_studio
npm install

# Start development servers
planalign studio --verbose
```

## Files to Modify

| File | Action | Purpose |
|------|--------|---------|
| `planalign_studio/components/ScenarioComparison.tsx` | Modify | Add DC plan data fetch + render new section |
| `planalign_studio/components/DCPlanComparisonSection.tsx` | Create | Extracted chart component (3 line charts, 1 bar chart, 1 table) |

## No Backend Changes Required

The existing API endpoint already provides all needed data:

```
GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare?scenarios=id1,id2
```

Returns `DCPlanComparisonResponse` with year-by-year `ContributionYearSummary` per scenario.

## Key Integration Points

### 1. Fetch DC Plan Data (in ScenarioComparison.tsx)

```typescript
import { compareDCPlanAnalytics, DCPlanComparisonResponse } from '../services/api';

// New state
const [dcPlanData, setDcPlanData] = useState<DCPlanComparisonResponse | null>(null);
const [dcPlanLoading, setDcPlanLoading] = useState(false);
const [dcPlanError, setDcPlanError] = useState<string | null>(null);

// Fetch after scenarios load (derive workspaceId from scenario data)
useEffect(() => {
  if (scenariosWithResults.length >= 2) {
    const workspaceId = scenariosWithResults[0].scenario.workspace_id;
    const ids = scenariosWithResults.map(d => d.scenario.id);
    fetchDCPlanComparison(workspaceId, ids);
  }
}, [scenariosWithResults]);
```

### 2. Transform Data for Charts

```typescript
// Build trend data (one array per metric)
const buildTrendData = (metric: keyof ContributionYearSummary): TrendDataPoint[] => {
  const allYears = new Set<number>();
  dcPlanData.analytics.forEach(a =>
    a.contribution_by_year.forEach(c => allYears.add(c.year))
  );
  return Array.from(allYears).sort().map(year => {
    const point: TrendDataPoint = { year };
    dcPlanData.analytics.forEach(a => {
      const yearData = a.contribution_by_year.find(c => c.year === year);
      point[a.scenario_name] = yearData?.[metric];
    });
    return point;
  });
};
```

### 3. Render Charts

Uses existing Recharts patterns from the same component:
- `COMPARISON_COLORS` for scenario colors
- `ResponsiveContainer` with `height="100%"` inside a `h-80` container
- Standard tooltip styling with `contentStyle` props

## Verification

1. Run two scenarios to completion in a workspace
2. Navigate to scenario comparison page
3. Verify:
   - "DC Plan Comparison" collapsible section appears below workforce charts
   - 3 line charts render (employer cost rate, participation rate, deferral rate)
   - 1 grouped bar chart renders (contribution breakdown)
   - 1 summary table renders with color-coded deltas
   - Tooltips show exact values on hover
   - Charts resize correctly when browser window changes
