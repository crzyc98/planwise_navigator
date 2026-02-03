# Implementation Plan: Vesting Hours Requirement Toggle

**Branch**: `030-vesting-hours-toggle` | **Date**: 2026-01-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/030-vesting-hours-toggle/spec.md`

## Summary

Add UI controls to the VestingAnalysis component for configuring the 1000-hour vesting requirement (ERISA provision). The feature exposes existing backend API fields (`require_hours_credit`, `hours_threshold`) through toggle controls and threshold inputs for both current and proposed schedule configurations. Results display will show which hours settings were applied.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend only)
**Primary Dependencies**: React 18, Lucide-react (icons), existing Tailwind CSS
**Storage**: N/A (frontend state only; backend unchanged)
**Testing**: Manual testing via browser; component structure follows existing patterns
**Target Platform**: Web browser (React/Vite frontend)
**Project Type**: Web application (frontend modification only)
**Performance Goals**: No degradation from current performance; UI updates <16ms
**Constraints**: Must maintain existing UI layout consistency; no new dependencies
**Scale/Scope**: Single component modification (~100 lines added)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only change; no event store modifications |
| II. Modular Architecture | PASS | Single component modification; no new modules needed |
| III. Test-First Development | PASS | Manual testing adequate for UI toggle; no complex logic |
| IV. Enterprise Transparency | PASS | Hours settings displayed in results for audit visibility |
| V. Type-Safe Configuration | PASS | Uses existing TypeScript types (VestingScheduleConfig) |
| VI. Performance & Scalability | PASS | No performance impact; simple state updates |

**Gate Status**: PASS - No violations. Proceeding to design.

## Project Structure

### Documentation (this feature)

```text
specs/030-vesting-hours-toggle/
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal - no unknowns)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - no new API)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   └── VestingAnalysis.tsx    # MODIFY: Add hours toggle controls
└── services/
    └── api.ts                 # NO CHANGES (types already exist)
```

**Structure Decision**: Frontend-only modification to existing component. No new files required.

## Complexity Tracking

> No violations to justify - feature is straightforward UI enhancement.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
