# Implementation Plan: Salary Range Configuration UX Improvements

**Branch**: `044-fix-salary-range-ux` | **Date**: 2026-02-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/044-fix-salary-range-ux/spec.md`

## Summary

Two targeted UX improvements to the ConfigStudio salary range configuration: (1) change the Match Census scale factor default from 1.0 to 1.5, and (2) fix finicky salary range input fields by switching from controlled `onChange` to `onBlur` commit pattern, widening inputs, reducing step size, and adding inline min > max validation. All changes are frontend-only, isolated to `ConfigStudio.tsx`.

## Technical Context

**Language/Version**: TypeScript 5.x (React 18 frontend)
**Primary Dependencies**: React 18, Vite, Tailwind CSS
**Storage**: N/A (frontend state only; no backend/database changes)
**Testing**: Manual browser testing (no existing frontend test suite for ConfigStudio)
**Target Platform**: Web browser (PlanAlign Studio at localhost:5173)
**Project Type**: Web application (frontend-only change)
**Performance Goals**: Input response feels instantaneous; no perceptible lag during editing
**Constraints**: Must not break existing Match Census flow or save behavior
**Scale/Scope**: Single file change (~50 lines modified in ConfigStudio.tsx)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | N/A | Frontend-only; no events created or modified |
| II. Modular Architecture | PASS | Changes isolated to single component; no new modules needed |
| III. Test-First Development | PASS | Manual browser testing appropriate for UI input behavior; no existing component test suite to extend |
| IV. Enterprise Transparency | N/A | No audit/logging impact |
| V. Type-Safe Configuration | PASS | TypeScript types preserved; no Pydantic changes |
| VI. Performance & Scalability | PASS | Reduces re-renders by switching onChange to onBlur |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/044-fix-salary-range-ux/
├── plan.md              # This file
├── research.md          # Phase 0: research findings
├── data-model.md        # Phase 1: component state model
├── quickstart.md        # Phase 1: implementation quickstart
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_studio/
└── components/
    └── ConfigStudio.tsx    # Single file modified (3 change areas)
```

**Structure Decision**: Frontend-only change to a single existing component. No new files, no new modules, no contracts directory needed (no API changes).

## Change Areas

### Area 1: Scale Factor Default (Line 347)

**Current**:
```typescript
const [compScaleFactor, setCompScaleFactor] = useState<number>(1.0);
```

**Proposed**:
```typescript
const [compScaleFactor, setCompScaleFactor] = useState<number>(1.5);
```

### Area 2: Input Handler — Switch to onBlur Pattern (Lines 350-357)

**Current**: `handleJobLevelCompChange` is called on every keystroke via `onChange`, immediately parsing the string to a number with `parseFloat(value) || 0`. This causes:
- Value snaps to 0 when field is cleared (empty string → `parseFloat("") || 0` → `0`)
- Every keystroke triggers a full state update and re-render
- Partial edits (e.g., deleting digits to retype) produce unintended intermediate values

**Proposed approach**:
1. Track local string state per input using `onBlur` commit pattern
2. On focus: store current numeric value as editable string
3. During editing: update local string only (no formData state change)
4. On blur/Enter: parse the final value and commit to formData via `handleJobLevelCompChange`
5. If empty on blur, commit 0

**Implementation**: Create a small inline wrapper component or use local state refs within the table row to manage the intermediate string state. The simplest approach is a `CompensationInput` helper component that:
- Accepts `value: number` and `onCommit: (value: number) => void`
- Manages its own `localValue: string` state
- Renders a text input that commits on blur/Enter

### Area 3: Input Styling & Validation (Lines 2446-2466)

**Current issues**:
- `w-28` (112px) clips values above ~$99,999 visually
- `step="1000"` makes arrow keys jump aggressively
- No min > max validation feedback

**Proposed changes**:
- Widen input: `w-28` → `w-36` (144px) to comfortably display values up to $999,999
- Reduce step: `step="1000"` → `step="500"` for finer arrow key control
- Add conditional red border + warning text when `row.minComp > row.maxComp`
- Use `type="text"` with `inputMode="numeric"` instead of `type="number"` to avoid browser spin buttons and gain full control over input parsing (alternative: keep `type="number"` with onBlur — simpler, keeps native behavior)

**Decision**: Keep `type="number"` to retain native numeric input behavior (spin buttons, mobile numeric keyboard). The onBlur pattern resolves the parsing issues regardless of input type.

## Complexity Tracking

> No constitution violations — table not needed.
