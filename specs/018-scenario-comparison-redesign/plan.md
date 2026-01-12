# Implementation Plan: Scenario Cost Comparison Redesign

**Branch**: `018-scenario-comparison-redesign` | **Date**: 2026-01-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/018-scenario-comparison-redesign/spec.md`

## Summary

Redesign the `ScenarioCostComparison.tsx` component to adopt design patterns from `CostComparison.tsx`, including:
- Sidebar-based multi-scenario selection with search
- Anchor/baseline scenario designation with visual indicators
- Annual/Cumulative view toggle with appropriate chart types
- Incremental costs variance chart
- Multi-Year Cost Matrix table
- Methodology/assumptions footer panels

This is a **replacement** of the existing component - the new implementation will serve the same `/compare` route.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend React component)
**Primary Dependencies**: React 18, react-router-dom, recharts, lucide-react, Tailwind CSS
**Storage**: N/A (API-driven, no local persistence)
**Testing**: Manual UI testing, existing Vite build validation
**Target Platform**: Modern browsers (Chrome, Firefox, Safari, Edge)
**Project Type**: Web application (frontend component in planalign_studio/)
**Performance Goals**: View toggle <1s, anchor change <2s (per SC-002, SC-003)
**Constraints**: Must integrate with existing API endpoints; preserve copy-to-clipboard functionality
**Scale/Scope**: Single React component replacement (~1100 lines current → ~500-600 lines redesigned)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicable? | Status | Notes |
|-----------|-------------|--------|-------|
| I. Event Sourcing & Immutability | No | N/A | Frontend component, no event creation |
| II. Modular Architecture | Yes | ✅ PASS | Single component with clear responsibility |
| III. Test-First Development | Partial | ⚠️ WAIVED | Frontend UI component; manual testing acceptable |
| IV. Enterprise Transparency | No | N/A | Read-only visualization component |
| V. Type-Safe Configuration | Yes | ✅ PASS | TypeScript types for all state/props |
| VI. Performance & Scalability | Yes | ✅ PASS | Client-side rendering, <2s response targets |

**Gate Status**: ✅ PASS - No constitution violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/018-scenario-comparison-redesign/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - using existing API)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   ├── ScenarioCostComparison.tsx  # TARGET: Replace entirely
│   ├── CostComparison.tsx          # REFERENCE: Design pattern source
│   └── Layout.tsx                  # Provides workspace context
├── hooks/
│   └── useCopyToClipboard.ts       # REUSE: Existing clipboard hook
├── services/
│   └── api.ts                      # REUSE: Existing API client
├── constants.ts                    # REUSE: COLORS.charts for chart palette
└── App.tsx                         # Routes: /compare → ScenarioCostComparison
```

**Structure Decision**: Single component replacement within existing frontend structure. No new directories needed.

## Complexity Tracking

> No violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
