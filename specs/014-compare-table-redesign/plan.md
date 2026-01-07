# Implementation Plan: Compare Page Table Redesign

**Branch**: `014-compare-table-redesign` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-compare-table-redesign/spec.md`

## Summary

Redesign the year-by-year breakdown section of the Scenario Cost Comparison page. Replace the current single dense table (years as rows, metrics as columns) with 6 separate metric-specific tables where rows are Baseline/Comparison/Variance and columns are simulation years (2025, 2026, 2027, etc.).

## Technical Context

**Language/Version**: TypeScript 5.x (frontend only)
**Primary Dependencies**: React 18, Vite, Tailwind CSS, Lucide React icons
**Storage**: N/A (frontend-only change, no backend modifications)
**Testing**: Manual visual testing (no existing test suite for React components)
**Target Platform**: Desktop browsers (1280px+ viewport)
**Project Type**: Web application (frontend only)
**Performance Goals**: Render within 2 seconds, no horizontal scrolling within tables
**Constraints**: Must work with existing data structures, no API changes required
**Scale/Scope**: Single component refactor (~200 lines of JSX changes)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only change, no data modifications |
| II. Modular Architecture | PASS | Refactoring existing component, may extract MetricTable subcomponent |
| III. Test-First Development | PASS | No unit tests for React components currently; visual testing acceptable |
| IV. Enterprise Transparency | N/A | UI change only |
| V. Type-Safe Configuration | PASS | Will use existing TypeScript types |
| VI. Performance & Scalability | PASS | Simplifies rendering, reduces table complexity |

**Gate Status**: PASS - No violations, proceed with implementation.

## Project Structure

### Documentation (this feature)

```text
specs/014-compare-table-redesign/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # N/A (no API changes)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   └── ScenarioCostComparison.tsx  # Main component to modify
└── services/
    └── api.ts                       # Existing types (no changes needed)
```

**Structure Decision**: This is a frontend-only refactor within the existing `planalign_studio/` directory. The ScenarioCostComparison component will be modified in-place. A new MetricTable subcomponent may be extracted for reusability.

## Complexity Tracking

> No violations to track. This is a straightforward UI refactor.

## Implementation Approach

### Current Structure (to be replaced)
```
+------+-------------------+----------+-----------+---------+
| Year | Metric            | Baseline | Comparison| Variance|
+------+-------------------+----------+-----------+---------+
| 2025 | Participation Rate| 75.5%    | 80.2%     | +4.7%   |
| 2025 | Avg Deferral Rate | 5.5%     | 6.0%      | +0.5%   |
| 2025 | Employer Match    | $500K    | $550K     | +$50K   |
| ... (6 metrics per year, all years stacked)              |
+------+-------------------+----------+-----------+---------+
```

### New Structure (target)
```
Participation Rate
+------------+--------+--------+--------+
|            | 2025   | 2026   | 2027   |
+------------+--------+--------+--------+
| Baseline   | 75.5%  | 78.0%  | 80.5%  |
| Comparison | 80.2%  | 82.5%  | 85.0%  |
| Variance   | +4.7%  | +4.5%  | +4.5%  |
+------------+--------+--------+--------+

Avg Deferral Rate
+------------+--------+--------+--------+
|            | 2025   | 2026   | 2027   |
+------------+--------+--------+--------+
| Baseline   | 5.50%  | 5.75%  | 6.00%  |
| Comparison | 6.00%  | 6.25%  | 6.50%  |
| Variance   | +0.50% | +0.50% | +0.50% |
+------------+--------+--------+--------+

... (4 more tables: Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate)
```

### Key Design Decisions

1. **MetricTable Component**: Extract a reusable `MetricTable` component that takes:
   - `title`: string (metric name)
   - `years`: number[] (sorted year list)
   - `baselineValues`: Map<number, number> (year -> value)
   - `comparisonValues`: Map<number, number> (year -> value)
   - `formatValue`: (val: number) => string
   - `isCost`: boolean (for variance color logic)
   - `baselineLabel`: string (e.g., "Baseline")
   - `comparisonLabel`: string (e.g., scenario name)

2. **Data Transformation**: Transform `yearByYearData` from year-first to metric-first structure.

3. **Styling**: Maintain existing Tailwind classes, consistent with MetricCard styling.

4. **Variance Display**: Reuse existing `VarianceDisplay` component.
