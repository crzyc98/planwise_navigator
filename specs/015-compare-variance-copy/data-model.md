# Data Model: Compare Variance Alignment & Copy Button

**Feature**: 015-compare-variance-copy
**Date**: 2026-01-08

## Overview

This feature is frontend-only and does not introduce new persistent data models. It modifies the presentation layer and adds transient UI state for clipboard operations.

## Component Props (Existing, Modified)

### MetricTableProps

The existing `MetricTableProps` interface will be extended:

```typescript
interface MetricTableProps {
  // Existing props
  title: string;
  years: number[];
  baselineData: Map<number, number>;
  comparisonData: Map<number, number>;
  formatValue: (val: number) => string;
  isCost: boolean;
  comparisonLabel: string;
  rawMultiplier?: number;
  loading?: boolean;

  // New props for copy functionality
  onCopy?: () => void;           // Optional callback after successful copy
  disableCopy?: boolean;         // Disable copy when no data
}
```

### VarianceDisplayProps

No changes needed to the interface, only styling adjustments:

```typescript
interface VarianceDisplayProps {
  delta: number;
  deltaPct: number;
  isCost?: boolean;
  formatValue?: (val: number) => string;
}
```

## New Hook: useCopyToClipboard

```typescript
interface UseCopyToClipboardReturn {
  copy: (text: string) => Promise<boolean>;
  copied: boolean;         // True for ~2 seconds after successful copy
  error: string | null;    // Error message if copy failed
}

function useCopyToClipboard(resetDelay?: number): UseCopyToClipboardReturn;
```

**State Transitions**:
1. Initial: `{ copied: false, error: null }`
2. On copy success: `{ copied: true, error: null }` → after `resetDelay` (default 2000ms) → `{ copied: false, error: null }`
3. On copy failure: `{ copied: false, error: "Clipboard access denied" }`

## Data Transformation: Table to TSV

### Input: MetricTable Data

```typescript
interface TableData {
  title: string;
  years: number[];
  baselineData: Map<number, number>;
  comparisonData: Map<number, number>;
  formatValue: (val: number) => string;
  comparisonLabel: string;
  isCost: boolean;
  rawMultiplier?: number;
}
```

### Output: TSV String

```typescript
function tableToTSV(data: TableData): string;
```

**Transformation Rules**:
1. Header row: `"Scenario\t{year1}\t{year2}\t..."`
2. Baseline row: `"Baseline\t{formatted_value1}\t{formatted_value2}\t..."`
3. Comparison row: `"{label}\t{formatted_value1}\t{formatted_value2}\t..."`
4. Variance row: `"Variance\t{delta1} (pct1)\t{delta2} (pct2)\t..."`

### Copy All Tables

```typescript
function allTablesToTSV(tables: TableData[]): string;
```

**Transformation Rules**:
1. For each table: `"{title}\n{tableToTSV(table)}\n\n"`
2. Join all with double newlines

## Relationships

```
ScenarioCostComparison
├── MetricTable (x6)
│   ├── useCopyToClipboard hook
│   ├── tableToTSV utility
│   └── VarianceDisplay (per year cell)
└── "Copy All" button
    └── allTablesToTSV utility
```

## Validation Rules

| Rule | Validation |
|------|------------|
| Empty table | If `years.length === 0`, disable copy button |
| Missing data | If `baselineData` or `comparisonData` empty, show "-" in cells, exclude from variance calculation |
| Clipboard unavailable | If `navigator.clipboard` undefined, show error and disable copy |

## No Persistent Storage Changes

This feature does not modify:
- DuckDB database schema
- API contracts
- Backend services
- Configuration files
