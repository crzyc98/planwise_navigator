# Quickstart: Compare Page Table Redesign

**Feature**: 014-compare-table-redesign
**Date**: 2026-01-07

## Quick Reference

### What's Changing

The year-by-year breakdown table at the bottom of the Compare DC Plan Costs page is being redesigned:

| Before | After |
|--------|-------|
| Single dense table | 6 separate tables (one per metric) |
| Years as rows | Years as columns |
| Metrics as columns | Baseline/Comparison/Variance as rows |
| Metrics grouped by year | Metrics grouped by type |

### Files to Modify

```
planalign_studio/components/ScenarioCostComparison.tsx
```

### No API Changes

The backend API remains unchanged. All data is already available.

## Development Steps

### 1. Add MetricTable Component

Insert before the main component (after VarianceDisplay):

```tsx
interface MetricTableProps {
  title: string;
  years: number[];
  baselineData: Map<number, number>;
  comparisonData: Map<number, number>;
  formatValue: (val: number) => string;
  isCost: boolean;
  comparisonLabel: string;
  rawMultiplier?: number;
}

const MetricTable = ({
  title,
  years,
  baselineData,
  comparisonData,
  formatValue,
  isCost,
  comparisonLabel,
  rawMultiplier = 1,
}: MetricTableProps) => {
  // ... implementation
};
```

### 2. Define Metrics Array

Add constant before the main component:

```tsx
const METRICS = [
  { key: 'participationRate', title: 'Participation Rate', format: formatPercent, isCost: false },
  { key: 'avgDeferralRate', title: 'Avg Deferral Rate', format: formatDeferralRate, isCost: false, rawMultiplier: 100 },
  { key: 'employerMatch', title: 'Employer Match', format: formatCurrency, isCost: true },
  { key: 'employerCore', title: 'Employer Core', format: formatCurrency, isCost: true },
  { key: 'totalEmployerCost', title: 'Total Employer Cost', format: formatCurrency, isCost: true },
  { key: 'employerCostRate', title: 'Employer Cost Rate', format: formatPercent, isCost: true },
];
```

### 3. Replace Year-by-Year Table Section

Replace lines 588-714 (the current table) with:

```tsx
{/* Year-by-Year Breakdown - Metric Tables */}
<div className="space-y-6">
  <div className="flex items-center justify-between">
    <div>
      <h2 className="text-lg font-semibold text-gray-900">Year-by-Year Breakdown</h2>
      <p className="text-sm text-gray-500 mt-1">
        Detailed comparison of metrics for each simulation year
      </p>
    </div>
  </div>

  {METRICS.map(metric => (
    <MetricTable
      key={metric.key}
      title={metric.title}
      years={sortedYears}
      baselineData={baselineByMetric.get(metric.key)}
      comparisonData={comparisonByMetric.get(metric.key)}
      formatValue={metric.format}
      isCost={metric.isCost}
      comparisonLabel={comparisonScenarioName}
      rawMultiplier={metric.rawMultiplier}
    />
  ))}
</div>
```

## Testing Checklist

- [ ] Select two scenarios with 3+ years of data
- [ ] Verify 6 separate tables appear (one per metric)
- [ ] Verify columns are years in chronological order
- [ ] Verify rows are Baseline, [Scenario Name], Variance
- [ ] Verify variance colors are correct (red for cost increases, green for decreases)
- [ ] Verify formatting (currency for $ amounts, % for rates)
- [ ] Test with 1-year simulation (single column)
- [ ] Test with missing data (should show "-")

## Rollback

If issues arise, revert to the commit before this feature branch was merged.
