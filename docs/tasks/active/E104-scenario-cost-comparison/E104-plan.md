# E104: Scenario Cost Comparison Page

## Overview
Add a new top-level page at `/compare` that allows users to select two scenarios (baseline vs comparison) and view side-by-side DC Plan cost metrics with year-by-year breakdown and variance calculations.

## User Requirements
- New top-level page in sidebar navigation
- Two scenario selectors: Baseline and Comparison
- Side-by-side cards showing metrics with variance
- Year-by-year breakdown plus totals
- Metrics: participation rate, avg deferral rate, employer match cost, employer core cost, total employer cost, variance

---

## Implementation Steps

### Step 1: Backend - Add Average Deferral Rate to Analytics Models

**File:** `/workspace/planalign_api/models/analytics.py`

Add new fields to existing models:

```python
# Add to ContributionYearSummary (line ~17):
average_deferral_rate: float = Field(description="Average deferral rate for enrolled participants")
participation_rate: float = Field(description="Participation rate for this year")
total_employer_cost: float = Field(description="Sum of match and core contributions")

# Add to DCPlanAnalytics (line ~87):
average_deferral_rate: float = Field(description="Average deferral rate across all years")
total_employer_cost: float = Field(description="Grand total employer cost (match + core)")
```

### Step 2: Backend - Update Analytics Service Queries

**File:** `/workspace/planalign_api/services/analytics_service.py`

Modify `_get_contribution_by_year()` (line ~170) to include:
- Average deferral rate per year
- Participation rate per year
- Total employer cost per year

```sql
SELECT
    simulation_year as year,
    COALESCE(SUM(prorated_annual_contributions), 0) as total_employee,
    COALESCE(SUM(employer_match_amount), 0) as total_match,
    COALESCE(SUM(employer_core_amount), 0) as total_core,
    COALESCE(SUM(employer_match_amount) + SUM(employer_core_amount), 0) as total_employer_cost,
    COALESCE(SUM(prorated_annual_contributions) + SUM(employer_match_amount) + SUM(employer_core_amount), 0) as total_all,
    AVG(CASE WHEN is_enrolled_flag THEN current_deferral_rate ELSE NULL END) as avg_deferral_rate,
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as participation_rate,
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) as participant_count
FROM fct_workforce_snapshot
WHERE UPPER(employment_status) = 'ACTIVE'
GROUP BY simulation_year
ORDER BY simulation_year
```

Update `get_dc_plan_analytics()` to compute overall average deferral rate and total employer cost.

### Step 3: Frontend - Update TypeScript Types

**File:** `/workspace/planalign_studio/services/api.ts`

Update interfaces (around line 752):

```typescript
export interface ContributionYearSummary {
  year: number;
  total_employee_contributions: number;
  total_employer_match: number;
  total_employer_core: number;
  total_all_contributions: number;
  participant_count: number;
  // NEW fields:
  average_deferral_rate: number;
  participation_rate: number;
  total_employer_cost: number;
}

export interface DCPlanAnalytics {
  // ... existing fields ...
  // NEW fields:
  average_deferral_rate: number;
  total_employer_cost: number;
}
```

### Step 4: Frontend - Create Comparison Component

**File:** `/workspace/planalign_studio/components/ScenarioCostComparison.tsx` (NEW)

~500-600 lines component with:

1. **Header Section**
   - Title: "Compare DC Plan Costs"
   - Workspace selector dropdown

2. **Scenario Selection Row**
   - Two cards side-by-side
   - Left: "Baseline Scenario" dropdown
   - Right: "Comparison Scenario" dropdown
   - Both filter to completed scenarios only

3. **Summary KPI Cards** (2-column layout, 6 metrics)
   - Participation Rate (baseline | comparison | variance)
   - Average Deferral Rate
   - Employer Match Cost
   - Employer Core Cost
   - Total Employer Cost
   - Each card shows: baseline value, comparison value, delta, delta %

4. **Year-by-Year Breakdown Table**
   - Columns: Year | Metric | Baseline | Comparison | Variance | Variance %
   - Grouped by year, showing all 5 metrics per year
   - Alternating row colors for year groups

5. **Totals Summary Row**
   - Grand totals for cost metrics
   - Highlighted styling

### Step 5: Frontend - Add Route

**File:** `/workspace/planalign_studio/App.tsx`

Add import and route:

```tsx
import ScenarioCostComparison from './components/ScenarioCostComparison';

// In routes:
<Route path="compare" element={<ScenarioCostComparison />} />
```

### Step 6: Frontend - Add Sidebar Navigation

**File:** `/workspace/planalign_studio/components/Layout.tsx`

Add navigation item in navItems array:

```tsx
{ to: '/compare', icon: <Scale size={20} />, label: 'Compare Costs' }
```

Import `Scale` from lucide-react.

---

## Variance Display Logic

| Metric | Positive Change | Interpretation |
|--------|----------------|----------------|
| Participation Rate | Green | Higher is better |
| Avg Deferral Rate | Green | Higher is better |
| Match Cost | Red | Higher = more expense |
| Core Cost | Red | Higher = more expense |
| Total Employer Cost | Red | Higher = more expense |

Format: Show both absolute delta and percentage delta
- Rates: `+3.7%` or `-2.1%`
- Costs: `+$1.2M (+14.3%)` or `-$500K (-8.2%)`
