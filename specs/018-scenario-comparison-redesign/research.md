# Research: Scenario Cost Comparison Redesign

**Feature**: 018-scenario-comparison-redesign
**Date**: 2026-01-12

## Research Areas

### 1. Chart Type Switching Pattern (recharts)

**Decision**: Use conditional rendering with ResponsiveContainer for chart type switching.

**Rationale**: The `CostComparison.tsx` reference implementation demonstrates this pattern effectively at lines 282-327. When `viewMode === 'annual'`, render a `BarChart`; when `viewMode === 'cumulative'`, render an `AreaChart`. Both share the same `processedData` but display differently.

**Pattern from CostComparison.tsx**:
```tsx
<ResponsiveContainer width="100%" height="100%">
  {viewMode === 'annual' ? (
    <BarChart data={processedData}>
      {/* Bar configuration */}
    </BarChart>
  ) : (
    <AreaChart data={processedData}>
      {/* Area configuration */}
    </AreaChart>
  )}
</ResponsiveContainer>
```

**Alternatives Considered**:
- Single chart type with style changes: Rejected - BarChart and AreaChart have different visual semantics
- Two separate chart components: Rejected - Adds unnecessary complexity when data structure is identical

---

### 2. Multi-Select Scenario State Management

**Decision**: Use React `useState` with an array of selected IDs, plus a separate `baselineId` state for the anchor.

**Rationale**: The `CostComparison.tsx` implementation at lines 27-31 demonstrates this pattern:
```tsx
const [selectedIds, setSelectedIds] = useState<string[]>(
  workspaceConfigs.slice(0, 3).map(c => c.id)
);
const [baselineId, setBaselineId] = useState<string>(workspaceConfigs[0]?.id || '');
```

The toggle function (lines 34-46) handles deselection edge cases including preventing deselection of the last item and reassigning baseline when the baseline is deselected.

**Key Behaviors**:
1. Minimum 1 scenario must remain selected (guard in toggleSelection)
2. When anchor is deselected, auto-assign to first remaining selected scenario
3. On initial load, use smart detection: find "baseline" scenario or default to first two

**Alternatives Considered**:
- Single `Map<string, boolean>` for selection: Rejected - Makes baseline tracking awkward
- Reducer pattern: Rejected - Overkill for 2-3 pieces of state with simple transitions

---

### 3. Sidebar Layout Pattern

**Decision**: Use flexbox with fixed-width sidebar (`w-80`) and flexible main content area.

**Rationale**: The `CostComparison.tsx` implementation at line 110-206 demonstrates a clean sidebar pattern:
```tsx
<div className="flex h-full gap-6 animate-fadeIn">
  {/* Sidebar Selector - fixed width */}
  <aside className="w-80 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden flex-shrink-0">
    {/* Header with search */}
    {/* Scrollable scenario list */}
    {/* Footer with download button */}
  </aside>

  {/* Main Content Area - flexible width */}
  <div className="flex-1 space-y-6 overflow-y-auto pr-2 pb-8">
    {/* Charts and tables */}
  </div>
</div>
```

**Key Design Elements**:
- `flex-shrink-0` on sidebar prevents shrinking
- `overflow-y-auto` on main content for scrolling
- Three-part sidebar: header (search), scrollable list, footer (actions)

**Alternatives Considered**:
- Grid layout: Rejected - Flexbox is simpler for this two-column case
- CSS sidebar with position:fixed: Rejected - Complicates scroll behavior

---

### 4. API Integration Pattern

**Decision**: Retain existing `compareDCPlanAnalytics` API for multi-scenario data fetching.

**Rationale**: The existing `ScenarioCostComparison.tsx` already has working API integration with:
- `listWorkspaces()` - Get available workspaces
- `listScenarios(workspaceId)` - Get scenarios for selected workspace
- `compareDCPlanAnalytics(workspaceId, scenarioIds)` - Fetch comparison data

The API already supports multi-scenario comparison (accepts array of scenario IDs), which aligns with the redesign requirements.

**Key API Response Structure** (from `api.ts` lines 772-832):
```typescript
interface DCPlanComparisonResponse {
  scenarios: string[];
  scenario_names: Record<string, string>;
  analytics: DCPlanAnalytics[];  // One per scenario
}

interface ContributionYearSummary {
  year: number;
  total_employer_match: number;
  total_employer_core: number;
  total_employer_cost: number;
  participation_rate: number;
  average_deferral_rate: number;
  employer_cost_rate: number;
}
```

**Alternatives Considered**:
- New API endpoint for redesign: Rejected - Existing endpoint provides all needed data
- GraphQL: Rejected - Not part of current architecture

---

### 5. Variance Calculation Pattern

**Decision**: Calculate variance in `useMemo` during data processing, storing both absolute delta and percentage delta.

**Rationale**: The `CostComparison.tsx` implementation at lines 62-97 shows the `processedData` memoization pattern:
```tsx
const processedData = useMemo(() => {
  const data = RETIREMENT_COST_DATA.map((yearRow: any) => {
    const row: any = { year: yearRow.year };

    selectedIds.forEach(id => {
      row[id] = yearRow[id] || 0;
      if (baselineId && id !== baselineId) {
        row[`${id}_delta`] = (yearRow[id] || 0) - (yearRow[baselineId] || 0);
      }
    });

    return row;
  });
  // Cumulative calculation if needed...
}, [selectedIds, baselineId, viewMode]);
```

This pattern computes deltas inline during data transformation, avoiding recalculation on each render.

**Alternatives Considered**:
- Calculate in render: Rejected - Performance issue with large datasets
- Separate variance state: Rejected - Derived data should be computed, not stored

---

### 6. Color Palette for Multi-Scenario Charts

**Decision**: Use existing `COLORS.charts` array from `constants.ts`, with anchor scenario rendered in dark gray (`#1e293b`).

**Rationale**: From `CostComparison.tsx` lines 298, 320:
```tsx
fill={id === baselineId ? '#1e293b' : COLORS.charts[idx % COLORS.charts.length]}
```

This ensures:
1. Anchor is always visually distinct (dark color)
2. Other scenarios cycle through a predefined palette
3. Consistency with other charts in the application

**Alternatives Considered**:
- Dynamic color generation: Rejected - Could produce clashing colors
- User-selectable colors: Rejected - Scope creep, adds complexity

---

### 7. Copy-to-Clipboard Integration

**Decision**: Reuse existing `useCopyToClipboard` hook from `hooks/useCopyToClipboard.ts`.

**Rationale**: The existing hook at `planalign_studio/hooks/useCopyToClipboard.ts` provides:
- `copy(text)`: Async function to copy text
- `copied`: Boolean for visual feedback
- `error`: Error message if copy fails

Already integrated in current `ScenarioCostComparison.tsx` with TSV export format. Will retain this functionality.

**Alternatives Considered**:
- Native clipboard API directly: Rejected - Hook provides better UX with feedback state
- Third-party clipboard library: Rejected - Unnecessary dependency

---

## Summary

All research areas resolved. No NEEDS CLARIFICATION items remain. The redesign will:

1. Adopt sidebar selection pattern from `CostComparison.tsx`
2. Use conditional chart rendering for Annual/Cumulative views
3. Retain existing API integration (`compareDCPlanAnalytics`)
4. Use memoized variance calculations
5. Apply consistent color palette with anchor distinction
6. Preserve copy-to-clipboard functionality
