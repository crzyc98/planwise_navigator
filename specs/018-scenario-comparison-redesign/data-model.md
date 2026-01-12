# Data Model: Scenario Cost Comparison Redesign

**Feature**: 018-scenario-comparison-redesign
**Date**: 2026-01-12

## Component State Model

### Primary State

```typescript
interface ScenarioCostComparisonState {
  // Workspace/Scenario Selection
  workspaces: Workspace[];               // From listWorkspaces() API
  scenarios: Scenario[];                 // From listScenarios() API
  selectedWorkspaceId: string;           // Currently selected workspace
  selectedScenarioIds: string[];         // Multi-select scenario IDs (1-5)
  anchorScenarioId: string;              // Baseline for variance calculations

  // View Configuration
  viewMode: 'annual' | 'cumulative';     // Chart display mode
  searchQuery: string;                   // Scenario filter text

  // API Data
  comparisonData: DCPlanComparisonResponse | null;  // From compareDCPlanAnalytics()

  // UI State
  loading: boolean;                      // API call in progress
  loadingScenarios: boolean;             // Scenario list loading
  error: string | null;                  // API error message
}
```

### Derived Data (Computed via useMemo)

```typescript
interface ProcessedChartData {
  year: number;
  [scenarioId: string]: number;          // Cost value per scenario
  [scenarioIdDelta: string]: number;     // Delta from anchor (e.g., "scenario1_delta")
}

interface YearByYearMetricData {
  years: number[];                        // Sorted year array
  comparisonScenarioName: string;         // Display name
  // Per-metric Maps: year -> value
  participationRate: MetricMaps;
  avgDeferralRate: MetricMaps;
  employerMatch: MetricMaps;
  employerCore: MetricMaps;
  totalEmployerCost: MetricMaps;
  employerCostRate: MetricMaps;
}

interface MetricMaps {
  baselineMap: Map<number, number>;       // anchor scenario values
  comparisonMap: Map<number, number>;     // comparison scenario values
}
```

## Entity Relationships

```
Workspace (1) ──────< Scenario (many)
                          │
                          │ selectedScenarioIds[]
                          ▼
              DCPlanComparisonResponse
                          │
                          │ analytics[]
                          ▼
              DCPlanAnalytics (per scenario)
                          │
                          │ contribution_by_year[]
                          ▼
              ContributionYearSummary (per year)
```

## State Transitions

### Initial Load
```
Empty → Workspaces loaded → Scenarios loaded → Auto-select scenarios → Fetch comparison
```

### Scenario Selection
```
User clicks scenario → Toggle selection → If anchor deselected, reassign → Fetch comparison
```

### Anchor Change
```
User clicks anchor icon → Update anchorScenarioId → Recalculate variances (no API call)
```

### View Mode Toggle
```
User clicks Annual/Cumulative → Update viewMode → Recalculate processedData (no API call)
```

## Validation Rules

| Field | Rule | Error Handling |
|-------|------|----------------|
| selectedScenarioIds | Length >= 1 | Prevent deselection of last scenario |
| selectedScenarioIds | Length <= 5 | Disable additional selections |
| anchorScenarioId | Must be in selectedScenarioIds | Auto-reassign on mismatch |
| searchQuery | No validation | Filter is client-side, tolerant |

## API Contracts (Existing - No Changes)

The component uses existing API endpoints from `planalign_studio/services/api.ts`:

1. **listWorkspaces()** → `Workspace[]`
2. **listScenarios(workspaceId)** → `Scenario[]`
3. **compareDCPlanAnalytics(workspaceId, scenarioIds[])** → `DCPlanComparisonResponse`

See `api.ts` lines 772-861 for full type definitions.

## Key Type Imports

```typescript
import {
  Workspace,
  Scenario,
  DCPlanComparisonResponse,
  DCPlanAnalytics,
  ContributionYearSummary,
  listWorkspaces,
  listScenarios,
  compareDCPlanAnalytics,
} from '../services/api';
```
