# Implementation Plan: Expand Scenario Comparison Limit

**Branch**: `019-expand-scenario-comparison` | **Date**: 2026-01-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/019-expand-scenario-comparison/spec.md`

## Summary

Increase the scenario comparison limit from 5 to 6 on the Compare Costs page. This requires updating the selection limit constant, expanding the color palette to ensure 6 distinct colors, and adding UI feedback (disabled checkboxes with tooltip) when the limit is reached.

## Technical Context

**Language/Version**: TypeScript 5.8, React 19.2
**Primary Dependencies**: React, Recharts 3.5.0, Lucide-react 0.554.0
**Storage**: N/A (frontend-only change; backend API already supports variable scenario counts)
**Testing**: Manual testing (no existing test framework in frontend; Vitest available via Vite)
**Target Platform**: Web browser (React SPA via Vite)
**Project Type**: Web application (frontend component modification)
**Performance Goals**: Consistent with current 5-scenario rendering performance
**Constraints**: Must maintain visual clarity with 6 scenarios; colors must be distinguishable
**Scale/Scope**: Single component change (`ScenarioCostComparison.tsx`) + constants file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only change; no event store impact |
| II. Modular Architecture | PASS | Change is localized to one component + constants |
| III. Test-First Development | PASS | Will add acceptance tests for new limit |
| IV. Enterprise Transparency | N/A | No audit/logging changes required |
| V. Type-Safe Configuration | PASS | TypeScript ensures type safety |
| VI. Performance & Scalability | PASS | 6 scenarios within performance constraints |

**Gate Status**: PASS - No violations detected.

## Project Structure

### Documentation (this feature)

```text
specs/019-expand-scenario-comparison/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - no API changes)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   └── ScenarioCostComparison.tsx  # Primary change: selection limit + checkbox disable
├── constants.ts                     # COLORS.charts array expansion (5 → 6 colors)
└── types.ts                         # No changes expected
```

**Structure Decision**: Single component modification pattern. All changes are localized to the existing `planalign_studio/` frontend directory structure.

## Complexity Tracking

> No constitution violations to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | - | - |
