# Tasks: Configurable Auto-Enrollment Opt-Out Rates

**Input**: Design documents from `/specs/068-optout-rate-config/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/config/`
- **API**: `planalign_api/routers/`
- **Orchestrator**: `planalign_orchestrator/config/`

---

## Phase 1: Setup

**Purpose**: No project initialization needed — all target files exist. This phase is a no-op.

**Checkpoint**: Ready to proceed to foundational work.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add opt-out rate fields to type definitions, defaults, and API — shared infrastructure that ALL user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 [P] Add 8 `dcOptOutRate*` fields to the `FormData` interface in `planalign_studio/components/config/types.ts`. Fields: `dcOptOutRateYoung` (number), `dcOptOutRateMid` (number), `dcOptOutRateMature` (number), `dcOptOutRateSenior` (number), `dcOptOutRateLowIncome` (number), `dcOptOutRateModerate` (number), `dcOptOutRateHigh` (number), `dcOptOutRateExecutive` (number). Add them after the existing `dcAutoEnrollHireDateCutoff` field in the DC Plan auto-enrollment section.

- [x] T002 [P] Add 8 default values to `DEFAULT_FORM_DATA` in `planalign_studio/components/config/constants.ts`. Defaults (as percentages): `dcOptOutRateYoung: 35`, `dcOptOutRateMid: 20`, `dcOptOutRateMature: 15`, `dcOptOutRateSenior: 10`, `dcOptOutRateLowIncome: 40`, `dcOptOutRateModerate: 25`, `dcOptOutRateHigh: 15`, `dcOptOutRateExecutive: 5`. Place after existing auto-enrollment defaults.

- [x] T003 [P] Add opt-out rate field mappings to `buildConfigPayload()` in `planalign_studio/components/config/buildConfigPayload.ts`. Map each `dcOptOutRate*` field to `dc_plan.opt_out_rate_*` key, converting percentage to decimal by dividing by 100 (e.g., `opt_out_rate_young: Number(formData.dcOptOutRateYoung) / 100`). Follow the existing pattern used for `default_deferral_percent`. Add all 8 mappings inside the existing `dc_plan` object.

- [x] T004 [P] Add opt-out rate defaults to the `/config/defaults` endpoint response in `planalign_api/routers/system.py`. Extend the `enrollment.auto_enrollment` dict with an `opt_out_rates` object containing `by_age` (young: 0.35, mid_career: 0.20, mature: 0.15, senior: 0.10) and `by_income` (low_income: 0.40, moderate: 0.25, high: 0.15, executive: 0.05). Follow the existing nested dict pattern at lines 157-162.

**Checkpoint**: Type definitions, defaults, payload mapping, and API defaults are ready. UI and orchestrator work can begin.

---

## Phase 3: User Story 1 & 2 - Configure Opt-Out Rates by Age Band and Income Band (Priority: P1) MVP

**Goal**: Analysts can view, edit, and save opt-out rates for both age bands and income bands in the DC Plan configuration panel.

**Note**: US1 and US2 are combined because they modify the same UI file (`DCPlanSection.tsx`) in the same collapsible section. Splitting them would create merge conflicts.

**Independent Test**: Open DC Plan config, verify "Opt-Out Assumptions" section appears with 8 pre-populated fields organized into "By Age" and "By Income" groups. Modify values, save, reload the scenario, and verify values persist.

### Implementation for User Story 1 & 2

- [x] T005 [US1] Add a collapsible "Opt-Out Assumptions" section to `planalign_studio/components/config/DCPlanSection.tsx`. Place it after the existing auto-enrollment fields. The section should only be visible when auto-enrollment is enabled (`dcAutoEnroll` is true). Use the same collapsible panel pattern used by other sections in this file.

- [x] T006 [US1] Add "By Age" input group inside the Opt-Out Assumptions section in `planalign_studio/components/config/DCPlanSection.tsx`. Include 4 numeric input fields: Young (18-25) bound to `dcOptOutRateYoung`, Mid-Career (26-35) bound to `dcOptOutRateMid`, Mature (36-50) bound to `dcOptOutRateMature`, Senior (51+) bound to `dcOptOutRateSenior`. Display as percentages (0-100). Add help text for each field describing the demographic segment.

- [x] T007 [US2] Add "By Income" input group inside the Opt-Out Assumptions section in `planalign_studio/components/config/DCPlanSection.tsx`. Include 4 numeric input fields: Low Income (<$30k) bound to `dcOptOutRateLowIncome`, Moderate ($30k-$50k) bound to `dcOptOutRateModerate`, High ($50k-$100k) bound to `dcOptOutRateHigh`, Executive (>$100k) bound to `dcOptOutRateExecutive`. Display as percentages (0-100). Add help text for each field.

- [x] T008 [US1] Add input validation for all 8 opt-out rate fields in `planalign_studio/components/config/DCPlanSection.tsx`. Validate that values are between 0 and 100 (percentage). Display a validation message if the user enters a value outside this range. Prevent saving invalid values. Follow existing validation patterns in the file.

- [x] T009 [US1] Wire up form state loading: when a scenario is loaded (existing `config_overrides.dc_plan` has opt-out rates), populate the 8 `dcOptOutRate*` fields from the saved values. Convert decimals (0.00-1.00) back to percentages (0-100) for display. If no opt-out rates are saved, use the defaults from `constants.ts`. This should be handled in the existing form initialization logic in `DCPlanSection.tsx` or its parent component.

**Checkpoint**: Age band and income band opt-out rate configuration is fully functional in the UI. Analysts can view, edit, save, and reload custom rates.

---

## Phase 4: User Story 3 - Simulation Uses Custom Opt-Out Rates (Priority: P1)

**Goal**: Custom opt-out rates configured in the UI flow through to the simulation engine and produce different enrollment outcomes.

**Independent Test**: Set all age-band opt-out rates to 99%, run a simulation, verify that nearly all auto-enrolled employees have opt-out events.

### Implementation for User Story 3

- [x] T010 [US3] Add opt-out rate mapping to the E095 dc_plan section of `_export_enrollment_vars()` in `planalign_orchestrator/config/export.py`. After the existing auto-enrollment field mappings (around line 166), add 8 mappings following the same `if dc_plan_dict.get("key") is not None` guard pattern. Map: `opt_out_rate_young` → `opt_out_rate_young`, `opt_out_rate_mid` → `opt_out_rate_mid`, `opt_out_rate_mature` → `opt_out_rate_mature`, `opt_out_rate_senior` → `opt_out_rate_senior`, `opt_out_rate_low_income` → `opt_out_rate_low_income`, `opt_out_rate_moderate` → `opt_out_rate_moderate`, `opt_out_rate_high` → `opt_out_rate_high`, `opt_out_rate_executive` → `opt_out_rate_executive`. Values are already decimals from buildConfigPayload, so cast with `float()` only.

- [x] T011 [US3] Verify backward compatibility: ensure that when `dc_plan` dict does NOT contain opt-out rate keys, the function does not set those dbt vars, allowing `dbt_project.yml` fallback defaults to take effect. This is inherent in the `if get() is not None` guard pattern but should be explicitly verified by reading the function end-to-end after changes.

**Checkpoint**: End-to-end data flow is complete. Custom opt-out rates from the UI reach the dbt SQL layer via orchestrator export.

---

## Phase 5: User Story 4 - Reset Opt-Out Rates to Defaults (Priority: P2)

**Goal**: Analysts can reset all opt-out rate fields to system defaults with a single action.

**Independent Test**: Modify several opt-out rates, click "Reset to Defaults", verify all 8 fields revert to default values.

### Implementation for User Story 4

- [x] T012 [US4] Add a "Reset to Defaults" button inside the Opt-Out Assumptions section in `planalign_studio/components/config/DCPlanSection.tsx`. When clicked, reset all 8 `dcOptOutRate*` fields to their `DEFAULT_FORM_DATA` values from `constants.ts`. Use the existing form state update pattern (e.g., `setFormData` or equivalent). Place the button at the top-right of the collapsible section header or at the bottom of the section.

**Checkpoint**: All user stories are complete. Full feature is functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling and final validation

- [x] T013 Handle legacy scenario loading: ensure that when a scenario saved before this feature (no opt-out rate keys in `config_overrides.dc_plan`) is loaded, the UI gracefully defaults to `DEFAULT_FORM_DATA` values. Verify in `planalign_studio/components/config/DCPlanSection.tsx` form initialization logic.

- [x] T014 Verify that the dbt layer correctly handles boundary values (0.00 and 1.00) by reviewing `dbt/models/intermediate/int_enrollment_events.sql` opt-out CTE logic (lines 379-460). No code changes expected — this is a verification task to confirm the SQL handles 0% and 100% opt-out rates without errors.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No-op for this feature
- **Foundational (Phase 2)**: No dependencies — can start immediately. T001-T004 are all [P] (parallel, different files)
- **US1+US2 (Phase 3)**: Depends on T001, T002, T003 (types, defaults, payload mapping)
- **US3 (Phase 4)**: Depends on T003 (payload mapping) — can run in parallel with Phase 3
- **US4 (Phase 5)**: Depends on T005 (collapsible section exists) from Phase 3
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **US1+US2 (P1)**: Depends on Phase 2 completion. No dependencies on US3 or US4.
- **US3 (P1)**: Depends on Phase 2 (T003 specifically). Can run in parallel with US1+US2 since it modifies a different file (`export.py`).
- **US4 (P2)**: Depends on US1+US2 (needs the UI section to exist).

### Within Each User Story

- T005 (collapsible section) before T006/T007 (field groups)
- T006/T007 can run in parallel (different field groups, but same file — execute sequentially to avoid conflicts)
- T008 (validation) after T006/T007
- T009 (state loading) after T008

### Parallel Opportunities

- **Phase 2**: All 4 tasks (T001-T004) can run in parallel — each modifies a different file
- **Phase 3 + Phase 4**: US1+US2 (frontend) and US3 (orchestrator) can run in parallel — different files entirely

---

## Parallel Example: Phase 2 (Foundational)

```
Task: T001 "Add dcOptOutRate* fields to FormData in types.ts"
Task: T002 "Add defaults to DEFAULT_FORM_DATA in constants.ts"
Task: T003 "Add opt-out rate mappings to buildConfigPayload.ts"
Task: T004 "Add opt_out_rates to /config/defaults in system.py"
```

All four tasks modify different files and can execute simultaneously.

## Parallel Example: Phase 3 + Phase 4

```
Stream A (Frontend): T005 → T006 → T007 → T008 → T009
Stream B (Backend):  T010 → T011
```

These two streams modify completely separate files and can run in parallel.

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

1. Complete Phase 2: Foundational (T001-T004, all parallel)
2. Complete Phase 3: US1+US2 — Age and income band UI
3. Complete Phase 4: US3 — Orchestrator passthrough
4. **STOP and VALIDATE**: Configure custom rates in UI, run simulation, verify enrollment results differ from defaults
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 2 → Foundation ready (types, defaults, payload, API)
2. Phase 3 → US1+US2 complete → Analysts can configure and save rates (MVP!)
3. Phase 4 → US3 complete → Rates flow through to simulation
4. Phase 5 → US4 complete → Reset button available
5. Phase 6 → Polish → Edge cases verified

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 and US2 are combined in Phase 3 because they modify the same file and section
- No dbt/SQL changes needed — the enrollment model already uses `{{ var() }}` templates
- Total: 14 tasks across 6 files modified, 0 files created
- Commit after each phase or logical group
