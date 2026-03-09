# Tasks: Fix Target Compensation Growth Persistence

**Input**: Design documents from `/specs/064-fix-comp-growth-persist/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested in spec — test tasks omitted.

**Organization**: Tasks grouped by user story. US1 (frontend form model + component) and US2 (API round-trip) are both P1 but US2 depends on US1's type definitions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No setup needed — all changes modify existing files in an existing project.

*No tasks in this phase.*

---

## Phase 2: Foundational (Type & Default Definitions)

**Purpose**: Extend the shared FormData type and defaults that both user stories depend on.

**CRITICAL**: US1 and US2 both need these type/default changes before implementation can begin.

- [x] T001 Add `targetCompensationGrowth: number` field to `FormData` interface in `planalign_studio/components/config/types.ts` (in the compensation fields section, after `promoRateMultiplier`)
- [x] T002 Add `targetCompensationGrowth: 5.0` to `DEFAULT_FORM_DATA` in `planalign_studio/components/config/constants.ts` (in the compensation section, after `promoRateMultiplier`)

**Checkpoint**: FormData type and defaults updated — user story implementation can begin.

---

## Phase 3: User Story 1 — Persist Target Compensation Growth Value (Priority: P1) MVP

**Goal**: The slider reads from and writes to `formData.targetCompensationGrowth` instead of local `useState`, so the value survives component unmount/remount within a session.

**Independent Test**: Set slider to 7.5%, navigate to another config section, return to Compensation — slider should show 7.5%.

### Implementation for User Story 1

- [x] T003 [US1] Replace local `useState<number>(5.0)` with `formData.targetCompensationGrowth` in `planalign_studio/components/config/CompensationSection.tsx` — remove the `targetCompGrowth` state variable, read slider value from `formData.targetCompensationGrowth`, update via `setFormData` spread pattern
- [x] T004 [US1] Update the slider's `onChange` handler in `planalign_studio/components/config/CompensationSection.tsx` to call `setFormData(prev => ({ ...prev, targetCompensationGrowth: newValue }))` instead of `setTargetCompGrowth`
- [x] T005 [US1] Update the `solveCompensationGrowth` call in `planalign_studio/components/config/CompensationSection.tsx` to use `formData.targetCompensationGrowth` instead of `targetCompGrowth`

**Checkpoint**: Slider value persists across in-session navigation (component mount/unmount cycle). "Calculate Settings" still works correctly.

---

## Phase 4: User Story 2 — Round-Trip Through API (Priority: P1)

**Goal**: The target compensation growth value is included in the save payload, stored by the backend, and hydrated on load — surviving full page reloads and cross-session access.

**Independent Test**: Set slider to 8.0%, save scenario, refresh browser, reopen scenario — slider shows 8.0%. Load a pre-fix scenario — slider shows 5.0% default.

### Implementation for User Story 2

- [x] T006 [P] [US2] Add `target_compensation_growth_percent: Number(formData.targetCompensationGrowth)` to the compensation object in `planalign_studio/components/config/buildConfigPayload.ts` (after `promotion_rate_multiplier`)
- [x] T007 [P] [US2] Hydrate `targetCompensationGrowth` from scenario overrides in `planalign_studio/components/config/ConfigContext.tsx` — in the useEffect that loads scenario-specific overrides, add `targetCompensationGrowth: cfg.compensation?.target_compensation_growth_percent ?? prev.targetCompensationGrowth` alongside existing compensation field hydrations
- [x] T008 [P] [US2] Hydrate `targetCompensationGrowth` from workspace base config in `planalign_studio/components/config/ConfigContext.tsx` — in the useEffect that loads workspace base config, add the same null-coalescing pattern
- [x] T009 [US2] Add `targetCompensationGrowth` to dirty tracking in `planalign_studio/components/config/ConfigContext.tsx` — in the useEffect that checks for compensation changes, add comparison `formData.targetCompensationGrowth !== savedFormData.targetCompensationGrowth`

**Checkpoint**: Full round-trip works — value persists across browser refresh, cross-session, and backward-compatible with pre-fix scenarios.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation and edge case handling.

- [ ] T010 Run quickstart.md manual validation (set slider → save → navigate away → return → verify value)
- [ ] T011 Test backward compatibility — load a scenario saved before this fix and verify slider defaults to 5.0% without errors
  *(T010 and T011 require manual testing with a running PlanAlign Studio instance)*

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — start immediately
- **US1 (Phase 3)**: Depends on Phase 2 (T001, T002) for type definitions
- **US2 (Phase 4)**: Depends on Phase 2 (T001, T002) for type definitions; independent of US1
- **Polish (Phase 5)**: Depends on US1 + US2 completion

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational only — no dependency on US2
- **User Story 2 (P1)**: Depends on Foundational only — no dependency on US1
- US1 and US2 can run in parallel after Phase 2

### Within Each User Story

- US1: T003 → T004 → T005 (sequential — same file, each builds on previous)
- US2: T006, T007, T008 can run in parallel [P] (different files); T009 depends on T007/T008 (same file)

### Parallel Opportunities

- T001 and T002 are in different files but T002 depends on T001's type — run sequentially
- After Phase 2: US1 and US2 can proceed in parallel
- Within US2: T006, T007, T008 touch different files — can run in parallel

---

## Parallel Example: User Story 2

```bash
# After Phase 2 completes, launch these US2 tasks in parallel:
Task: "Add target_compensation_growth_percent to buildConfigPayload.ts"
Task: "Hydrate targetCompensationGrowth from scenario overrides in ConfigContext.tsx"
# Note: T007 and T008 are in the same file, so run T008 after T007
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001, T002)
2. Complete Phase 3: User Story 1 (T003-T005)
3. **STOP and VALIDATE**: Slider persists across in-session navigation
4. This alone fixes the most visible symptom (slider resetting on tab switch)

### Full Fix (Both Stories)

1. Complete Phase 2: Foundational (T001, T002)
2. Complete Phase 3: User Story 1 (T003-T005) — in-session persistence
3. Complete Phase 4: User Story 2 (T006-T009) — cross-session persistence
4. Complete Phase 5: Polish (T010-T011) — validation
5. Full round-trip persistence achieved

---

## Notes

- All tasks modify existing files — no new files created
- T003-T005 are in the same file (CompensationSection.tsx) — could be done as a single edit
- T007-T009 are in the same file (ConfigContext.tsx) — could be done as a single edit
- Backward compatibility is handled by `??` null-coalescing — no migration needed
- Total: 11 tasks across 5 files
