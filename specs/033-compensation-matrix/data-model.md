# Data Model: Multi-Year Compensation Matrix

**Feature**: 033-compensation-matrix
**Date**: 2026-02-03

## Overview

This feature uses existing data structures - no new entities or schema changes required.

## Existing Entities (Referenced)

### ContributionYearSummary

**Location**: `planalign_studio/services/api.ts:795-809`

```typescript
interface ContributionYearSummary {
  year: number;
  total_employee_contributions: number;
  total_employer_match: number;
  total_employer_core: number;
  total_all_contributions: number;
  participant_count: number;
  average_deferral_rate: number;
  participation_rate: number;
  total_employer_cost: number;      // Used by cost matrix
  total_compensation: number;        // ← USED BY THIS FEATURE
  employer_cost_rate: number;
}
```

### DCPlanAnalytics

**Location**: `planalign_studio/services/api.ts:834-855`

```typescript
interface DCPlanAnalytics {
  scenario_id: string;
  scenario_name: string;
  contribution_by_year: ContributionYearSummary[];  // Contains compensation data
  // ... other fields
  total_compensation: number;  // Aggregate across all years
}
```

### DCPlanComparisonResponse

**Location**: `planalign_studio/services/api.ts:857-861`

```typescript
interface DCPlanComparisonResponse {
  scenarios: string[];
  scenario_names: Record<string, string>;
  analytics: DCPlanAnalytics[];  // Contains per-scenario, per-year compensation
}
```

## Data Access Pattern

### Reading Compensation Data

```typescript
// Get compensation for a specific scenario and year
const yearData = analytics.contribution_by_year.find(y => y.year === targetYear);
const compensation = yearData?.total_compensation ?? 0;

// Get total compensation for a scenario (sum across years)
const total = analytics.contribution_by_year.reduce(
  (sum, y) => sum + y.total_compensation,
  0
);

// Get anchor scenario's total for variance calculation
const anchorTotal = anchorAnalytics.contribution_by_year.reduce(
  (sum, y) => sum + y.total_compensation,
  0
);
const variance = total - anchorTotal;
```

## Display Transformations

### Currency Formatting

Uses existing `formatCurrency()` function (lines 45-52):

```typescript
const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};
```

### TSV Export Format

For clipboard copy functionality:

```
Scenario\t2025\t2026\t2027\tTotal\tVariance
Baseline\t$1.2M\t$1.3M\t$1.4M\t$3.9M\t--
High Growth\t$1.5M\t$1.7M\t$1.9M\t$5.1M\t+$1.2M
```

## Schema Changes

**None required.** All data structures already exist and contain the necessary fields.
