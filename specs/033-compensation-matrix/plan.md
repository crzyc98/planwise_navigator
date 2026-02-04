# Implementation Plan: Multi-Year Compensation Matrix

**Branch**: `033-compensation-matrix` | **Date**: 2026-02-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/033-compensation-matrix/spec.md`

## Summary

Add a "Multi-Year Compensation Matrix" table to the scenario cost comparison page (`ScenarioCostComparison.tsx`), positioned directly below the existing "Multi-Year Cost Matrix". The new table displays `total_compensation` data (already present in the API response) for each scenario and simulation year, with total/variance columns matching the cost matrix design patterns.

**Technical Approach**: Frontend-only change in a single React component. No backend modifications required as `total_compensation` data is already included in `ContributionYearSummary` interface (line 807 of `api.ts`).

## Technical Context

**Language/Version**: TypeScript 5.x (frontend)
**Primary Dependencies**: React 18, Recharts, Lucide-react, Tailwind CSS
**Storage**: N/A (frontend-only; uses existing API response data)
**Testing**: Manual testing via browser (no unit test infrastructure for this component)
**Target Platform**: Web browser (PlanAlign Studio frontend at `http://localhost:5173`)
**Project Type**: Web application (frontend enhancement)
**Performance Goals**: No additional API calls; renders within existing page load time
**Constraints**: Match existing Multi-Year Cost Matrix visual design exactly
**Scale/Scope**: Single component modification (~100-150 lines added)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only; no event store changes |
| II. Modular Architecture | PASS | Single component modification; no new modules |
| III. Test-First Development | DEFERRED | Component lacks unit test infrastructure; manual testing acceptable for UI-only changes |
| IV. Enterprise Transparency | PASS | Uses existing audit-logged API data |
| V. Type-Safe Configuration | PASS | TypeScript types already defined in `api.ts` |
| VI. Performance & Scalability | PASS | No additional API calls; reuses existing data |

**Gate Result**: PASS - No constitutional violations.

## Project Structure

### Documentation (this feature)

```text
specs/033-compensation-matrix/
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal - no unknowns)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - no new API contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   └── ScenarioCostComparison.tsx  # MODIFY: Add compensation matrix table
├── services/
│   └── api.ts                       # NO CHANGE: total_compensation already in types
└── hooks/
    └── useCopyToClipboard.ts        # REUSE: Existing hook for copy functionality
```

**Structure Decision**: Frontend-only modification to existing component. No new files required.

## Complexity Tracking

> No constitutional violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |

## Implementation Approach

### Key Code Patterns to Replicate

The compensation matrix must exactly mirror the cost matrix implementation at lines 1039-1141 of `ScenarioCostComparison.tsx`:

1. **Table Structure**: Same header row with Scenario Name, Year columns, Total, Variance
2. **Data Access**: `analytics.contribution_by_year.find(y => y.year === year)?.total_compensation`
3. **Formatting**: Use existing `formatCurrency()` helper
4. **Styling**: Same Tailwind classes for anchor highlighting, variance badges
5. **Copy Function**: Create parallel `compensationTableToTSV()` function and `handleCompensationCopy()` handler

### Data Flow

```
comparisonData.analytics[] → ContributionYearSummary.total_compensation → formatCurrency() → Table Cell
```

### Required Changes

1. **Add State**: `const { copy: copyCompensation, copied: copiedCompensation } = useCopyToClipboard();`
2. **Add TSV Function**: `compensationTableToTSV()` callback (parallel to `tableToTSV()`)
3. **Add Copy Handler**: `handleCompensationCopy()` callback
4. **Add Table JSX**: Insert after line 1141 (after cost matrix closing `</div>`), before methodology footer (line 1143)

### Positioning in Component

```jsx
{/* Multi-Year Cost Matrix Table */}
<div className="bg-white rounded-xl ...">
  {/* Existing cost matrix - lines 1039-1141 */}
</div>

{/* Multi-Year Compensation Matrix Table - NEW */}
<div className="bg-white rounded-xl ...">
  {/* New compensation matrix - mirrors cost matrix structure */}
</div>

{/* Methodology Footer Section - line 1143+ */}
<div className="grid grid-cols-1 md:grid-cols-2 ...">
```

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | No backend changes; read-only data display |
| II. Modular Architecture | PASS | Single file modified; ~100-150 lines added to 1,191-line component (acceptable) |
| III. Test-First Development | DEFERRED | Manual testing documented in quickstart.md; no unit test infrastructure exists for React components |
| IV. Enterprise Transparency | PASS | Displays existing audited compensation data |
| V. Type-Safe Configuration | PASS | Uses existing TypeScript interfaces; no new types needed |
| VI. Performance & Scalability | PASS | Zero additional API calls; O(n) rendering where n = scenarios × years |

**Post-Design Gate Result**: PASS - Design maintains constitutional compliance.

## Artifacts Generated

| Artifact | Path | Status |
|----------|------|--------|
| Implementation Plan | `specs/033-compensation-matrix/plan.md` | Complete |
| Research | `specs/033-compensation-matrix/research.md` | Complete |
| Data Model | `specs/033-compensation-matrix/data-model.md` | Complete |
| Quickstart Guide | `specs/033-compensation-matrix/quickstart.md` | Complete |
| Contracts | `specs/033-compensation-matrix/contracts/README.md` | Complete (N/A - no new APIs) |

## Next Steps

Run `/speckit.tasks` to generate the implementation task list.
