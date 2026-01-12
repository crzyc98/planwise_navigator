# Quickstart: Scenario Cost Comparison Redesign

**Feature**: 018-scenario-comparison-redesign
**Date**: 2026-01-12

## Overview

This task redesigns the `ScenarioCostComparison.tsx` component to adopt design patterns from `CostComparison.tsx`. The redesigned component will replace the existing one entirely at the `/compare` route.

## Prerequisites

- Node.js (for planalign_studio frontend)
- Running PlanAlign API backend (`planalign studio --api-only`)
- At least one workspace with 2+ completed scenarios

## File Locations

| File | Purpose |
|------|---------|
| `planalign_studio/components/ScenarioCostComparison.tsx` | **TARGET**: Replace entirely |
| `planalign_studio/components/CostComparison.tsx` | **REFERENCE**: Design patterns |
| `planalign_studio/services/api.ts` | API client (no changes) |
| `planalign_studio/hooks/useCopyToClipboard.ts` | Clipboard hook (reuse) |
| `planalign_studio/constants.ts` | Color palette (reuse) |
| `planalign_studio/App.tsx` | Router (no changes) |

## Development Workflow

### 1. Start the Development Environment

```bash
# Terminal 1: Start API backend
cd /workspace
source .venv/bin/activate
planalign studio --api-only

# Terminal 2: Start frontend dev server
cd /workspace/planalign_studio
npm run dev
```

### 2. Access the Component

Open browser to `http://localhost:5173/#/compare`

### 3. Implementation Order

1. **Scaffold component structure** (sidebar + main layout)
2. **Implement sidebar scenario selection** (multi-select, search, anchor)
3. **Implement workspace/scenario data fetching** (reuse existing patterns)
4. **Implement chart section** (Annual/Cumulative toggle, BarChart/AreaChart)
5. **Implement Incremental Costs chart** (variance lines)
6. **Implement Multi-Year Cost Matrix table** (rows per scenario)
7. **Implement methodology footer panels**
8. **Preserve copy-to-clipboard functionality**
9. **Test edge cases** (single scenario, anchor deselection, API errors)

## Key Patterns to Adopt

### From CostComparison.tsx

```tsx
// Sidebar layout (line 110-206)
<div className="flex h-full gap-6">
  <aside className="w-80 flex-shrink-0">...</aside>
  <div className="flex-1 overflow-y-auto">...</div>
</div>

// Multi-select state (lines 27-46)
const [selectedIds, setSelectedIds] = useState<string[]>([...]);
const [baselineId, setBaselineId] = useState<string>('');

// View mode toggle (lines 260-278)
<div className="flex bg-gray-100 p-1 rounded-lg">
  <button onClick={() => setViewMode('annual')}>Annual Spend</button>
  <button onClick={() => setViewMode('cumulative')}>Cumulative Cost</button>
</div>

// Conditional chart rendering (lines 282-327)
{viewMode === 'annual' ? <BarChart .../> : <AreaChart .../>}

// Variance calculation in useMemo (lines 62-97)
row[`${id}_delta`] = (yearRow[id] || 0) - (yearRow[baselineId] || 0);
```

### From Existing ScenarioCostComparison.tsx (Preserve)

```tsx
// API integration (lines 565-635)
const fetchWorkspaces = async () => {...};
const fetchScenarios = async (workspaceId: string) => {...};
const fetchComparison = async () => {...};

// Copy to clipboard (lines 263-281)
const { copy, copied, error } = useCopyToClipboard();
```

## Testing Checklist

- [ ] Sidebar displays all completed scenarios
- [ ] Multi-select works (up to 5 scenarios)
- [ ] Search filters scenarios by name
- [ ] Anchor icon changes anchor scenario
- [ ] Annual/Cumulative toggle switches chart type
- [ ] Variance values recalculate on anchor change
- [ ] Copy-to-clipboard works for table data
- [ ] Loading states display during API calls
- [ ] Error states display on API failure
- [ ] Single scenario shows guidance message

## API Endpoints Used

```
GET  /api/workspaces
GET  /api/workspaces/{id}/scenarios
GET  /api/workspaces/{id}/analytics/dc-plan/compare?scenarios=id1,id2,id3
```

## Success Criteria Validation

| Criterion | How to Verify |
|-----------|--------------|
| SC-001: Compare up to 5 scenarios | Select 5 scenarios, verify all display |
| SC-002: View toggle <1s | Toggle Annual/Cumulative, observe instant switch |
| SC-003: Anchor change <2s | Change anchor, observe variance update |
| SC-004: Identify costs in 5s | Load page, verify chart is readable |
| SC-005: Search in 3s | Type search term, verify instant filter |
