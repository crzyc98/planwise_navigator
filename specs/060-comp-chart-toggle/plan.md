# Implementation Plan: Compensation Chart Toggle (Average/Total) with CAGR

**Branch**: `060-comp-chart-toggle` | **Date**: 2026-03-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/060-comp-chart-toggle/spec.md`

## Summary

Add a toggle to the "Average Compensation - All Employees" chart on the Analytics Dashboard that switches between average and total compensation views, with the CAGR percentage displayed in the chart title. This is a frontend-only change — the backend already returns all required data (`total_compensation` in `workforce_progression` and pre-computed CAGR in `cagr_metrics`).

## Technical Context

**Language/Version**: TypeScript 5.x (React 18 frontend)
**Primary Dependencies**: React 18, Recharts 3.5.0, Lucide-react, Tailwind CSS
**Storage**: N/A (frontend reads from existing API; no database changes)
**Testing**: Manual verification (frontend component, no automated test framework in planalign_studio)
**Target Platform**: Web browser (PlanAlign Studio frontend at localhost:5173)
**Project Type**: Web application (frontend-only change)
**Performance Goals**: Chart toggle updates instantly (no API calls on toggle)
**Constraints**: Single file modification (`AnalyticsDashboard.tsx`); no new dependencies
**Scale/Scope**: 1 component, ~50 lines of changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only, no event store changes |
| II. Modular Architecture | PASS | Change is within a single existing component; no new modules needed |
| III. Test-First Development | N/A | Frontend component; no Python test infrastructure applies. Manual verification plan provided. |
| IV. Enterprise Transparency | PASS | CAGR display enhances transparency by surfacing growth metrics directly on the chart |
| V. Type-Safe Configuration | PASS | Toggle state uses TypeScript literal types (`'average' | 'total'`) |
| VI. Performance & Scalability | PASS | No additional API calls; toggle is pure client-side state switch |

**Post-Phase 1 Re-check**: All gates still pass. No new architectural concerns from the design.

## Project Structure

### Documentation (this feature)

```text
specs/060-comp-chart-toggle/
├── plan.md              # This file
├── research.md          # Phase 0 output - data availability findings
├── data-model.md        # Phase 1 output - entity/state documentation
├── quickstart.md        # Phase 1 output - developer getting-started guide
├── contracts/
│   └── ui-contract.md   # Phase 1 output - UI behavior contract
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_studio/
└── components/
    └── AnalyticsDashboard.tsx   # MODIFY: lines 86 (state), 223-227 (data transform), 504-528 (chart card)
```

**Structure Decision**: Single-file modification within the existing frontend component structure. No new files or directories needed.

## Implementation Approach

### Changes to `AnalyticsDashboard.tsx`

1. **Add state** (near line 104):
   ```typescript
   const [compMetric, setCompMetric] = useState<'average' | 'total'>('average');
   ```

2. **Extend data transform** (line 223-227):
   - Add `totalCompensation` field derived from `row.total_compensation`
   - Scale to millions (`/ 1_000_000`) for readability

3. **Add CAGR lookup helper**:
   - Find matching metric from `results.cagr_metrics` based on toggle state
   - Handle missing/single-year data gracefully

4. **Replace static chart card** (lines 504-528):
   - Add segmented toggle button in the card header
   - Dynamic chart title with CAGR
   - Switch `dataKey` between `avgCompensation` and `totalCompensation`
   - Dynamic Y-axis formatter (`$K` vs `$M`)
   - Dynamic tooltip formatter
   - Dynamic legend label

## Complexity Tracking

No violations. This is a minimal frontend change within a single component.
