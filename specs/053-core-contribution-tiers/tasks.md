# Tasks: Core Contribution Tier Validation & Points-Based Mode

**Input**: Design documents from `/specs/053-core-contribution-tiers/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: No test tasks included (not requested in specification).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: User Story 1 - Tier Validation Warnings for Graded Core (Priority: P1) MVP

**Goal**: Add gap/overlap validation warnings to the graded-by-service core contribution tier editor, matching the existing validation UX on tenure-based and points-based match tiers.

**Independent Test**: Enable core contributions, select "Graded by Service", configure tiers with gaps/overlaps, and verify amber warning box appears with correct messages and [min, max) interval reminder.

### Implementation for User Story 1

- [x] T001 [US1] Add tier gap/overlap validation warnings to graded-by-service core schedule editor in `planalign_studio/components/config/DCPlanSection.tsx`. After the graded core schedule `</div>` closing tag (after line 597), add an IIFE block that calls `validateMatchTiers()` with `formData.dcCoreGradedSchedule.map(t => ({ min: t.serviceYearsMin, max: t.serviceYearsMax }))` and label `'service years'`. Render the amber warning box with the same markup as lines 201-212 (tenure match tier warnings), including the `[min, max) intervals` reminder text.

**Checkpoint**: Graded-by-service core tiers now show validation warnings. US1 is fully functional and independently testable.

---

## Phase 2: User Story 2 - Points-Based Core Contribution Mode (Priority: P2)

**Goal**: Add "Points-Based" as a third core contribution type in the UI with a tier editor for configuring point-range contribution rates.

**Independent Test**: Enable core contributions, select "Points-Based" from the dropdown, add/edit/delete point tiers, verify validation warnings appear for gaps/overlaps, and save the configuration.

### Implementation for User Story 2

- [x] T002 [P] [US2] Add `PointsCoreTier` interface and `dcCorePointsSchedule` field to `FormData` in `planalign_studio/components/config/types.ts`. Interface has three fields: `minPoints: number`, `maxPoints: number | null`, `rate: number`. Add `dcCorePointsSchedule: PointsCoreTier[]` to the `FormData` interface in the "DC Plan - Core Contribution" section.

- [x] T003 [P] [US2] Add default `dcCorePointsSchedule` to `DEFAULT_FORM_DATA` in `planalign_studio/components/config/constants.ts`. Add after the `dcCoreGradedSchedule` default (around line 152): `dcCorePointsSchedule: [{ minPoints: 0, maxPoints: 40, rate: 1.0 }, { minPoints: 40, maxPoints: 75, rate: 2.0 }, { minPoints: 75, maxPoints: null, rate: 3.0 }]`.

- [x] T004 [US2] Add "Points-Based" option and tier editor to `planalign_studio/components/config/DCPlanSection.tsx`. Three changes: (1) Add `<option value="points_based">Points-Based (varies by age + tenure points)</option>` to the core contribution type dropdown (after line 513). (2) Add a points-based core tier editor section rendered when `formData.dcCoreStatus === 'points_based'`, modeled on the points-based match tier editor (lines 217-309) but using `dcCorePointsSchedule` with fields `minPoints`, `maxPoints`, `rate` (no `maxDeferralPct`). Include formula description "Points = FLOOR(age) + FLOOR(years of service). Uses [min, max) intervals." and an empty-state message. (3) Add `validateMatchTiers()` warnings to the new points-based core editor, mapping `formData.dcCorePointsSchedule.map(t => ({ min: t.minPoints, max: t.maxPoints }))` with label `'points'`.

- [x] T005 [P] [US2] Add `core_points_schedule` mapping to API payload in `planalign_studio/components/config/buildConfigPayload.ts`. After the `core_graded_schedule` mapping (line 101), add: `core_points_schedule: formData.dcCorePointsSchedule.map((tier: any) => ({ min_points: tier.minPoints, max_points: tier.maxPoints, contribution_rate: tier.rate / 100 }))`.

- [x] T006 [P] [US2] Load `dcCorePointsSchedule` from saved config in `planalign_studio/components/config/ConfigContext.tsx`. In the section where core contribution config is loaded from overrides (near the `dcCoreGradedSchedule` loading logic), add loading for `dcCorePointsSchedule` from `dc_plan.core_points_schedule`, transforming API format `{min_points, max_points, contribution_rate}` back to UI format `{minPoints, maxPoints, rate}` where `rate = contribution_rate * 100`.

**Checkpoint**: Points-based core mode is available in the UI with tier editing, validation warnings, config persistence, and loading from saved state. US2 is fully functional and independently testable.

---

## Phase 3: User Story 3 - Points-Based Core in Simulation Engine (Priority: P3)

**Goal**: Make the simulation engine calculate core contributions using the points-based tier schedule when configured.

**Independent Test**: Configure points-based core tiers via the UI, run a simulation (`planalign simulate 2025`), and query `fct_yearly_events` to verify core contribution rates match the tier schedule based on employee age+service points.

**Dependencies**: US2 must be complete (config must be saveable from UI).

### Implementation for User Story 3

- [x] T007 [P] [US3] Export `employer_core_points_schedule` dbt variable in `planalign_orchestrator/config/export.py`. In the `_export_core_contribution_vars()` function, after the `core_graded_schedule` export block, add a block that reads `core_points_schedule` from `dc_plan_dict`, transforms each tier from API format `{min_points, max_points, contribution_rate (decimal)}` to dbt format `{min_points, max_points, rate (percentage = contribution_rate * 100)}`, and sets `dbt_vars["employer_core_points_schedule"]` with the transformed list.

- [x] T008 [P] [US3] Add `points_based` conditional branch to `dbt/models/intermediate/int_employer_core_contributions.sql`. (1) Add `{% set employer_core_points_schedule = var('employer_core_points_schedule', []) %}` at the top with other variable declarations. (2) In the core rate CASE expression (around line 283), add a new condition before the `graded_by_service` check: `{% if employer_core_status == 'points_based' and employer_core_points_schedule | length > 0 %}` that calls `{{ get_points_based_match_rate('(FLOOR(COALESCE(snap.age_as_of_december_31, 0))::INT + FLOOR(COALESCE(snap.current_tenure, 0))::INT)', employer_core_points_schedule, employer_core_contribution_rate) }}`. Use `{% elif ... %}` for the existing `graded_by_service` branch.

**Checkpoint**: Simulations with points-based core configuration produce correct contribution amounts. US3 is fully functional.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final verification across all user stories

- [x] T009 Verify all three core contribution modes work end-to-end: switch between Flat Rate, Graded by Service, and Points-Based in the UI, save each, and confirm tier data is preserved when switching modes
- [x] T010 Verify dbt model compiles with points-based core config by running `cd dbt && dbt compile --select int_employer_core_contributions --threads 1`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (US1)**: No dependencies — can start immediately
- **Phase 2 (US2)**: No dependency on US1 — can start in parallel
- **Phase 3 (US3)**: Depends on US2 completion (needs config shape to exist in API payload)
- **Phase 4 (Polish)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Independent — single file change to DCPlanSection.tsx
- **User Story 2 (P2)**: Independent — can run in parallel with US1
- **User Story 3 (P3)**: Depends on US2 — needs `core_points_schedule` in API payload and `dcCorePointsSchedule` in FormData

### Within Each User Story

- US1: Single task, no internal dependencies
- US2: T002 + T003 in parallel first, then T004 (needs types from T002), then T005 + T006 in parallel
- US3: T007 + T008 in parallel (different files, no dependencies between them)

### Parallel Opportunities

- T002 + T003 can run in parallel (different files: types.ts and constants.ts)
- T005 + T006 can run in parallel (different files: buildConfigPayload.ts and ConfigContext.tsx)
- T007 + T008 can run in parallel (different files: export.py and int_employer_core_contributions.sql)
- US1 and US2 can be worked on in parallel (no code dependencies between them)

---

## Parallel Example: User Story 2

```text
# Step 1: Launch type + constant tasks together:
T002: "Add PointsCoreTier interface in planalign_studio/components/config/types.ts"
T003: "Add default dcCorePointsSchedule in planalign_studio/components/config/constants.ts"

# Step 2: After T002 completes, build the UI:
T004: "Add points-based core tier editor in planalign_studio/components/config/DCPlanSection.tsx"

# Step 3: Launch persistence tasks together:
T005: "Add core_points_schedule to payload in planalign_studio/components/config/buildConfigPayload.ts"
T006: "Load dcCorePointsSchedule from config in planalign_studio/components/config/ConfigContext.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001 (add validation warnings to graded core tiers)
2. **STOP and VALIDATE**: Test validation with gap/overlap/non-zero-start configurations
3. This delivers immediate value — parity fix for existing UI gap

### Incremental Delivery

1. Complete US1 (T001) → Validate → Deploy (validation parity fix)
2. Complete US2 (T002-T006) → Validate → Deploy (new UI mode)
3. Complete US3 (T007-T008) → Validate → Deploy (backend simulation support)
4. Complete Polish (T009-T010) → Final verification

### Sequential Strategy (Single Developer)

1. T001 → validate US1
2. T002, T003 → T004 → T005, T006 → validate US2
3. T007, T008 → validate US3
4. T009, T010 → final verification

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No new files are created — all tasks modify existing files
- US1 is a single-task MVP that can be deployed independently
- US2 and US3 together form the complete points-based core feature
- The `validateMatchTiers()` function and `get_points_based_match_rate` macro are reused — no new shared utilities needed
