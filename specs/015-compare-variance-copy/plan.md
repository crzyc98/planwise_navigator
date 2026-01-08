# Implementation Plan: Compare Variance Alignment & Copy Button

**Branch**: `015-compare-variance-copy` | **Date**: 2026-01-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-compare-variance-copy/spec.md`

## Summary

Fix the variance row alignment in the year-by-year breakdown tables on the Compare DC Plan Costs page and add copy-to-clipboard functionality for each metric table. The variance row currently uses an `inline-flex` container (`VarianceDisplay` component) which causes misalignment with the right-aligned values in other rows. The copy feature will export table data in TSV format suitable for Excel.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend)
**Primary Dependencies**: React 18, Vite, lucide-react (icons), Tailwind CSS
**Storage**: N/A (frontend-only feature, uses browser Clipboard API)
**Testing**: Manual visual testing, browser compatibility testing
**Target Platform**: Modern web browsers (Chrome, Firefox, Safari, Edge)
**Project Type**: Web application (frontend only for this feature)
**Performance Goals**: Copy feedback within 500ms of button click
**Constraints**: Must work with standard browser Clipboard API (`navigator.clipboard.writeText`)
**Scale/Scope**: 6 metric tables, each with 3 rows and up to 10 year columns

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only change, no event data modification |
| II. Modular Architecture | PASS | Changes confined to single component (~900 lines), may extract reusable hook |
| III. Test-First Development | PASS | Visual testing for alignment, manual testing for clipboard |
| IV. Enterprise Transparency | N/A | No logging changes required |
| V. Type-Safe Configuration | PASS | TypeScript with explicit props interfaces |
| VI. Performance & Scalability | PASS | Clipboard copy is O(rows × columns), negligible overhead |

**Gate Result**: PASS - No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/015-compare-variance-copy/
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
│   └── ScenarioCostComparison.tsx  # Main file to modify
├── hooks/
│   └── useCopyToClipboard.ts       # New reusable hook (optional)
└── services/
    └── api.ts                       # No changes needed
```

**Structure Decision**: Frontend-only changes in existing `planalign_studio/components/` directory. Optional extraction of clipboard logic to a reusable hook in `planalign_studio/hooks/`.

## Complexity Tracking

> No violations requiring justification.
