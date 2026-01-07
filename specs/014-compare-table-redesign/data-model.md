# Data Model: Compare Page Table Redesign

**Feature**: 014-compare-table-redesign
**Date**: 2026-01-07

## Overview

This feature is a frontend-only UI refactor. No new data entities are created. The existing data structures from the API are sufficient.

## Existing Data Structures (No Changes)

### ContributionYearSummary (from api.ts)

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
  total_employer_cost: number;
  total_compensation: number;
  employer_cost_rate: number;
}
```

### DCPlanAnalytics (from api.ts)

```typescript
interface DCPlanAnalytics {
  scenario_id: string;
  scenario_name: string;
  contribution_by_year: ContributionYearSummary[];
  // ... other fields
}
```

## New Frontend-Only Types

### MetricDefinition

```typescript
interface MetricDefinition {
  key: keyof YearMetrics;
  title: string;
  format: (value: number) => string;
  isCost: boolean;
  rawMultiplier?: number; // For variance calculation (e.g., deferral rate * 100)
}
```

### YearMetrics (existing, documented)

```typescript
interface YearMetrics {
  participationRate: { baseline: number; comparison: number };
  avgDeferralRate: { baseline: number; comparison: number };
  employerMatch: { baseline: number; comparison: number };
  employerCore: { baseline: number; comparison: number };
  totalEmployerCost: { baseline: number; comparison: number };
  employerCostRate: { baseline: number; comparison: number };
}
```

### MetricTableProps

```typescript
interface MetricTableProps {
  title: string;
  years: number[];
  getBaselineValue: (year: number) => number | undefined;
  getComparisonValue: (year: number) => number | undefined;
  formatValue: (value: number) => string;
  isCost: boolean;
  baselineLabel: string;
  comparisonLabel: string;
  rawMultiplier?: number;
}
```

## Data Flow

```
API Response (DCPlanAnalytics)
    ↓
yearByYearData memo (existing)
    ↓
METRICS array (new constant)
    ↓
MetricTable component (new) × 6
    ↓
Rendered tables
```

## No Database Changes

This feature does not modify any database schemas, dbt models, or API contracts.
