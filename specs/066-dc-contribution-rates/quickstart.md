# Quickstart: Trended Contribution Percentage Rates

**Feature**: 066-dc-contribution-rates
**Estimated effort**: Small (3 files modified, ~80 lines added)

## Prerequisites

- Working PlanAlign Studio dev environment (`planalign studio --verbose`)
- At least one completed multi-year simulation with DC plan data

## Implementation Order

### Step 1: Backend Model (5 min)

**File**: `planalign_api/models/analytics.py`

Add 4 fields to `ContributionYearSummary`:
```python
employee_contribution_rate: float = 0.0
match_contribution_rate: float = 0.0
core_contribution_rate: float = 0.0
total_contribution_rate: float = 0.0
```

Add same 4 fields to `DCPlanAnalytics` (aggregate level).

### Step 2: Backend Service (15 min)

**File**: `planalign_api/services/analytics_service.py`

In `_get_contribution_by_year()`, after `employer_cost_rate` computation (~line 252), add:
```python
employee_contribution_rate = round(total_employee / total_compensation * 100, 2) if total_compensation > 0 else 0.0
match_contribution_rate = round(total_match / total_compensation * 100, 2) if total_compensation > 0 else 0.0
core_contribution_rate = round(total_core / total_compensation * 100, 2) if total_compensation > 0 else 0.0
total_contribution_rate = round(employee_contribution_rate + match_contribution_rate + core_contribution_rate, 2)
```

In `_compute_grand_totals()`, add the same computation using cross-year totals.

### Step 3: TypeScript Interface (2 min)

**File**: `planalign_studio/services/api.ts`

Add to `ContributionYearSummary` interface:
```typescript
employee_contribution_rate: number;
match_contribution_rate: number;
core_contribution_rate: number;
total_contribution_rate: number;
```

### Step 4: Frontend Chart (20 min)

**File**: `planalign_studio/components/DCPlanComparisonSection.tsx`

Add a "Contribution Rate Trends" section using the same pattern as the Employer Cost Rate chart. For multi-series rendering (4 lines per scenario), build chart data with keys like `Employee (%)`, `Match (%)`, `Core (%)`, `Total (%)`.

### Step 5: Summary Table (10 min)

Add 4 new `SummaryMetricRow` entries to the summary table for the contribution rates.

## Verification

```bash
# Start studio
planalign studio --verbose

# Verify API returns new fields
curl http://localhost:8000/api/workspaces/{id}/scenarios/{id}/analytics/dc-plan | jq '.contribution_by_year[0] | {employee_contribution_rate, match_contribution_rate, core_contribution_rate, total_contribution_rate}'

# Open browser to DC Plan comparison page and verify chart renders
```

## Key Patterns to Follow

- **Rate computation**: Copy `employer_cost_rate` pattern (division guard, round to 2 decimals)
- **Chart rendering**: Copy Employer Cost Rate Trends chart pattern (ResponsiveContainer + LineChart)
- **Colors**: Use contribution type colors: Employee `#0088FE`, Match `#00C49F`, Core `#FFBB28`, Total `#FF8042`
- **Tooltip**: Use shared `tooltipStyle` object
