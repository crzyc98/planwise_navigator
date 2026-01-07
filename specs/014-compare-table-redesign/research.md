# Research: Compare Page Table Redesign

**Feature**: 014-compare-table-redesign
**Date**: 2026-01-07

## Research Summary

This is a straightforward frontend UI refactor with no unknowns. All required information is available in the existing codebase.

## Findings

### 1. Current Implementation Analysis

**Decision**: The existing `ScenarioCostComparison.tsx` component already has all the data structures and utility functions needed.

**Key Existing Assets**:
- `yearByYearData` memo (lines 319-368): Already aggregates data by year with all 6 metrics
- `calculateVariance()` function (lines 48-52): Reusable for variance calculation
- `VarianceDisplay` component (lines 91-128): Reusable for colored variance display
- `formatCurrency()`, `formatPercent()`, `formatDeferralRate()`: All formatters exist

**Rationale**: No new data fetching or API changes needed. The refactor is purely presentational.

### 2. Table Layout Pattern

**Decision**: Use a simple HTML table per metric with Tailwind styling consistent with existing MetricCard design.

**Pattern**:
```tsx
<div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-6">
  <div className="px-6 py-4 border-b border-gray-200">
    <h3 className="text-md font-semibold text-gray-900">{metricTitle}</h3>
  </div>
  <table className="w-full">
    <thead className="bg-gray-50">
      <tr>
        <th className="..."></th>
        {years.map(year => <th key={year}>{year}</th>)}
      </tr>
    </thead>
    <tbody>
      <tr>{/* Baseline row */}</tr>
      <tr>{/* Comparison row */}</tr>
      <tr>{/* Variance row */}</tr>
    </tbody>
  </table>
</div>
```

**Rationale**: Matches existing component styling (MetricCard, Grand Totals). Simple and maintainable.

### 3. Component Extraction Strategy

**Decision**: Create an inline `MetricTable` component within `ScenarioCostComparison.tsx` rather than a separate file.

**Rationale**:
- Single use case (only used in this component)
- Keeps related code together
- Avoids file proliferation for a small component
- Can be extracted later if reuse is needed

### 4. Metric Definitions

**Decision**: Define metrics array with all formatting and behavior config.

```typescript
const METRICS = [
  { key: 'participationRate', title: 'Participation Rate', format: formatPercent, isCost: false },
  { key: 'avgDeferralRate', title: 'Avg Deferral Rate', format: formatDeferralRate, isCost: false },
  { key: 'employerMatch', title: 'Employer Match', format: formatCurrency, isCost: true },
  { key: 'employerCore', title: 'Employer Core', format: formatCurrency, isCost: true },
  { key: 'totalEmployerCost', title: 'Total Employer Cost', format: formatCurrency, isCost: true },
  { key: 'employerCostRate', title: 'Employer Cost Rate', format: formatPercent, isCost: true },
];
```

**Rationale**: Centralizes metric configuration, makes it easy to add/remove metrics, DRY principle.

### 5. Edge Case Handling

**Decision**: Handle missing data with "-" display.

**Implementation**:
```typescript
const formatValue = (value: number | undefined) =>
  value !== undefined ? formatter(value) : '-';
```

**Rationale**: Consistent with spec requirement, graceful degradation.

## Alternatives Considered

### Alternative 1: CSS Grid Instead of HTML Table
- **Rejected**: HTML tables are semantically correct for tabular data and have better accessibility support.

### Alternative 2: Separate MetricTable File
- **Rejected**: Overkill for a single-use component. Can be extracted later if needed.

### Alternative 3: Virtualized Table for Large Year Ranges
- **Rejected**: Simulations typically have 3-10 years. Virtualization adds complexity without benefit.

## No Clarifications Needed

All requirements are clear from the spec. No NEEDS CLARIFICATION markers.
