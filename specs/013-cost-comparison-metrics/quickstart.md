# Quickstart: Employer Cost Ratio Metrics

**Date**: 2026-01-07
**Feature**: 013-cost-comparison-metrics

## Overview

This feature adds employer cost ratio metrics to the scenario cost comparison page. Users can see employer contributions as a percentage of total payroll, both per-year and as an aggregate.

## Implementation Steps

### 1. Backend: Extend Pydantic Models

**File**: `planalign_api/models/analytics.py`

Add two new fields to `ContributionYearSummary`:
```python
total_compensation: float = 0.0
employer_cost_rate: float = 0.0
```

Add two new fields to `DCPlanAnalytics`:
```python
total_compensation: float = 0.0
employer_cost_rate: float = 0.0
```

### 2. Backend: Extend Analytics Query

**File**: `planalign_api/services/analytics_service.py`

Update `_get_contribution_by_year()` SQL query to include:
```sql
COALESCE(SUM(prorated_annual_compensation), 0) as total_compensation
```

Calculate `employer_cost_rate` in Python:
```python
employer_cost_rate = (
    total_employer_cost / total_compensation * 100
    if total_compensation > 0
    else 0.0
)
```

Update `get_dc_plan_analytics()` to calculate aggregate values:
```python
total_compensation = sum(c.total_compensation for c in contribution_by_year)
employer_cost_rate = (
    total_employer_cost / total_compensation * 100
    if total_compensation > 0
    else 0.0
)
```

### 3. Frontend: Extend TypeScript Interfaces

**File**: `planalign_studio/services/api.ts`

Add to `ContributionYearSummary`:
```typescript
total_compensation: number;
employer_cost_rate: number;
```

Add to `DCPlanAnalytics`:
```typescript
total_compensation: number;
employer_cost_rate: number;
```

### 4. Frontend: Add Summary MetricCard

**File**: `planalign_studio/components/ScenarioCostComparison.tsx`

Add new MetricCard in the grid (after existing cards):
```tsx
<MetricCard
  title="Employer Cost Rate"
  icon={<Percent size={20} />}
  baselineValue={formatPercent(baselineAnalytics?.employer_cost_rate ?? 0)}
  comparisonValue={formatPercent(comparisonAnalytics?.employer_cost_rate ?? 0)}
  variance={calculateVariance(
    baselineAnalytics?.employer_cost_rate ?? 0,
    comparisonAnalytics?.employer_cost_rate ?? 0
  )}
  isCost={true}
  formatVariance={(v) => formatPercent(v)}
  loading={loading}
/>
```

### 5. Frontend: Add Year-by-Year Table Row

**File**: `planalign_studio/components/ScenarioCostComparison.tsx`

Add to the `metrics` array in `yearByYearData.map()`:
```typescript
{
  name: 'Employer Cost Rate',
  baseline: yearData.metrics.employerCostRate.baseline,
  comparison: yearData.metrics.employerCostRate.comparison,
  format: formatPercent,
  isCost: true,
}
```

Update the `yearByYearData` memo to extract `employer_cost_rate` from each year.

### 6. Frontend: Update Grand Totals

**File**: `planalign_studio/components/ScenarioCostComparison.tsx`

Add a fourth card in the Grand Totals Summary section:
```tsx
<div className="bg-white/10 rounded-lg p-4">
  <p className="text-sm text-white/80 mb-1">Employer Cost Rate</p>
  <div className="flex items-baseline justify-between">
    <span className="text-2xl font-bold">
      {formatPercent(comparisonAnalytics.employer_cost_rate)}
    </span>
    <span className="text-sm text-white/70">
      vs {formatPercent(baselineAnalytics.employer_cost_rate)}
    </span>
  </div>
</div>
```

## Testing

### Backend Tests

```python
# Test zero compensation handling
def test_employer_cost_rate_zero_compensation():
    result = service._calculate_employer_cost_rate(1000.0, 0.0)
    assert result == 0.0

# Test normal calculation
def test_employer_cost_rate_normal():
    result = service._calculate_employer_cost_rate(5000.0, 100000.0)
    assert result == 5.0  # 5000 / 100000 * 100 = 5%
```

### Manual Testing

1. Run two scenarios with different match formulas
2. Navigate to Compare DC Plan Costs page
3. Verify:
   - New "Employer Cost Rate" card appears
   - Year-by-year table includes "Employer Cost Rate" row
   - Grand Totals shows employer cost rate percentage
   - Variance indicators show correct colors (red for higher cost)

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `planalign_api/models/analytics.py` | Extend | Add 2 fields to 2 models |
| `planalign_api/services/analytics_service.py` | Extend | Add to SQL query, calculate rate |
| `planalign_studio/services/api.ts` | Extend | Add 2 fields to 2 interfaces |
| `planalign_studio/components/ScenarioCostComparison.tsx` | Extend | Add MetricCard, table row, Grand Totals card |
