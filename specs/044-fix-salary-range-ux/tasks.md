# Tasks: Salary Range Configuration UX Improvements

**Input**: Design documents from `/specs/044-fix-salary-range-ux/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Not requested — manual browser verification per quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/ConfigStudio.tsx` (single file for all changes)

---

## Phase 1: Setup

**Purpose**: No setup needed — all changes are to an existing file with no new dependencies.

*Phase skipped — no setup tasks required.*

---

## Phase 2: Foundational (CompensationInput Helper)

**Purpose**: Create the shared helper component that both user stories' input improvements depend on.

**CRITICAL**: The CompensationInput helper is used by US1 tasks and must be created first.

- [x] T001 Create `CompensationInput` helper component above the `ConfigStudio` function in `planalign_studio/components/ConfigStudio.tsx`. The component accepts props `{ value: number, onCommit: (v: number) => void, hasError?: boolean, step?: number, min?: number }`. It manages local `localValue: string` state via `useState(String(value))`, syncs from parent via `useEffect` on `value` prop changes, updates `localValue` on `onChange` (no parsing), and calls `onCommit(parseFloat(localValue) || 0)` on `onBlur` and Enter keypress. Uses Tailwind classes `w-36 shadow-sm sm:text-sm rounded-md p-1 border text-right focus:ring-fidelity-green focus:border-fidelity-green` with conditional `border-red-500` (when `hasError`) or `border-gray-300`. Default `step=500`, `min=0`. See `quickstart.md` Step 2 and `data-model.md` CompensationInput section for full specification.

**Checkpoint**: CompensationInput helper exists and compiles — user story implementation can now begin.

---

## Phase 3: User Story 1 - Comfortable Salary Range Editing (Priority: P1) MVP

**Goal**: Salary range input fields allow natural editing without snapping, clipping, or lag, with inline min > max validation.

**Independent Test**: Open Job Level Compensation table, edit min/max values across all levels. Verify: (1) clearing and retyping works without snap-to-0, (2) large values ($500K+) fully visible, (3) arrow keys step by $500, (4) setting min > max shows red borders + warning text, (5) saving still persists correct values.

### Implementation for User Story 1

- [x] T002 [US1] Replace the min compensation `<input>` element (currently at ~line 2447-2454) in the `jobLevelCompensation` table in `planalign_studio/components/ConfigStudio.tsx` with a `<CompensationInput>` component. Pass `value={row.minComp}`, `onCommit={(v) => handleJobLevelCompChange(idx, 'minComp', String(v))}`, and `hasError={hasRangeError}` where `hasRangeError` is computed as `row.minComp > row.maxComp && row.minComp > 0 && row.maxComp > 0`.

- [x] T003 [US1] Replace the max compensation `<input>` element (currently at ~line 2457-2464) in the same table in `planalign_studio/components/ConfigStudio.tsx` with a `<CompensationInput>` component. Pass `value={row.maxComp}`, `onCommit={(v) => handleJobLevelCompChange(idx, 'maxComp', String(v))}`, and `hasError={hasRangeError}` using the same condition as T002.

- [x] T004 [US1] Add inline min > max validation warning in the `jobLevelCompensation` table rows in `planalign_studio/components/ConfigStudio.tsx`. When `hasRangeError` is true for a row, render a `<span className="text-xs text-red-600">Min exceeds max</span>` element visible in or below the row. Ensure the warning does not shift the table layout (use a colspan cell, an extra column, or position it below the row).

**Checkpoint**: User Story 1 complete — salary inputs are comfortable to edit with validation feedback. Verify all 5 acceptance scenarios from spec.md.

---

## Phase 4: User Story 2 - Practical Default Scale Factor (Priority: P2)

**Goal**: Match Census scale factor defaults to 1.5x instead of 1.0x on page load.

**Independent Test**: Navigate to compensation configuration section, observe scale factor input shows 1.5 before any interaction. Click Match Census (with census loaded) and verify ranges are scaled by 1.5x.

### Implementation for User Story 2

- [x] T005 [US2] Change the `compScaleFactor` default from `1.0` to `1.5` at line 347 in `planalign_studio/components/ConfigStudio.tsx`. Change `useState<number>(1.0)` to `useState<number>(1.5)`.

**Checkpoint**: User Story 2 complete — scale factor defaults to 1.5. Verify all 3 acceptance scenarios from spec.md.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final verification that both stories work together without regressions.

- [ ] T006 *(manual)* Verify Match Census end-to-end: launch PlanAlign Studio (`planalign studio`), load a workspace with census data, click "Match Census" with default 1.5x scale factor, confirm ranges populate correctly, then manually edit a range value to confirm onBlur commit works on Match Census-populated values.

- [ ] T007 *(manual)* Verify save flow: after editing salary ranges with the new inputs and triggering min > max validation, click Save and confirm the API payload contains correct `min_compensation` / `max_compensation` values (check browser DevTools network tab or server logs).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — can start immediately
- **US1 (Phase 3)**: Depends on T001 (CompensationInput helper)
- **US2 (Phase 4)**: No dependencies — can start immediately (independent of T001)
- **Polish (Phase 5)**: Depends on Phase 3 and Phase 4 completion

### User Story Dependencies

- **User Story 1 (P1)**: Depends on T001 (foundational helper). No dependency on US2.
- **User Story 2 (P2)**: Fully independent — single line change with no dependencies on any other task.

### Within Each User Story

- **US1**: T002 and T003 can run in parallel (different `<td>` elements in same table). T004 depends on T002/T003 (needs `hasRangeError` variable in scope).
- **US2**: Single task (T005), no internal dependencies.

### Parallel Opportunities

- T001 (foundational) and T005 (US2) can run in parallel — different code locations, no overlap
- T002 and T003 (US1 min/max inputs) can run in parallel — different `<td>` cells
- US1 and US2 are independent stories that can be implemented in parallel

---

## Parallel Example: Full Implementation

```text
# Parallel batch 1 (no dependencies):
T001: Create CompensationInput helper component
T005: Change scale factor default to 1.5

# Parallel batch 2 (after T001):
T002: Replace min compensation input with CompensationInput
T003: Replace max compensation input with CompensationInput

# Sequential (after T002 + T003):
T004: Add min > max validation warning

# Sequential (after all):
T006: Verify Match Census end-to-end
T007: Verify save flow
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001: CompensationInput helper
2. Complete T002, T003, T004: Input replacement + validation
3. **STOP and VALIDATE**: Test all 5 US1 acceptance scenarios
4. Deploy if ready — salary editing is immediately improved

### Incremental Delivery

1. T001 → CompensationInput helper ready
2. T002 + T003 + T004 → US1 complete (comfortable editing + validation)
3. T005 → US2 complete (1.5x default)
4. T006 + T007 → Cross-story verification
5. Each story adds value without breaking the other

---

## Notes

- All changes are in a single file: `planalign_studio/components/ConfigStudio.tsx`
- No new dependencies, no backend changes, no API changes
- The `handleJobLevelCompChange` handler signature is preserved — CompensationInput passes `String(v)` to maintain backward compatibility
- The min > max validation is visual-only and does not block save (per spec assumptions)
- Total: 7 tasks (1 foundational + 3 US1 + 1 US2 + 2 polish)
