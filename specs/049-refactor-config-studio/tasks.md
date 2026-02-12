# Tasks: Refactor ConfigStudio into Modular Section Components

**Input**: Design documents from `/specs/049-refactor-config-studio/`
**Prerequisites**: plan.md (required), spec.md (required), data-model.md, contracts/ConfigContext.ts, research.md, quickstart.md

**Tests**: Not included — no frontend test framework exists in this project. Verification is via TypeScript compilation and manual visual testing.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/` (existing)
- **New directory**: `planalign_studio/components/config/` (created in setup)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new directory and shared type/constant files that all subsequent tasks depend on

- [X] T001 Create `planalign_studio/components/config/` directory structure
- [X] T002 [P] Create shared TypeScript types in `planalign_studio/components/config/types.ts` — extract `MatchTier`, `MatchTemplate`, `FormData`, `AgeDistributionRow`, `LevelDistributionRow`, `JobLevelCompRow`, `LevelMarketAdjustmentRow`, `TenureMatchTier`, `PointsMatchTier`, `CoreGradedTier` interfaces from ConfigStudio.tsx lines 8-18 and the formData object shape (lines 205-337). Reference `specs/049-refactor-config-studio/contracts/ConfigContext.ts` for the complete type definitions
- [X] T003 [P] Create shared constants in `planalign_studio/components/config/constants.ts` — extract `MATCH_TEMPLATES` object (lines 29-64), `calculateMatchCap` function (lines 21-27), and default `formData` initial values (lines 205-337) from ConfigStudio.tsx

**Checkpoint**: Types and constants are standalone files with no imports from ConfigStudio.tsx

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create reusable UI components, the payload builder, and the ConfigContext provider that ALL section components depend on

**CRITICAL**: No section component can be created until ConfigContext.tsx (T007) is complete

- [X] T004 [P] Extract `InputField` component to `planalign_studio/components/config/InputField.tsx` — move the `InputFieldProps` interface (lines 67-78) and `InputField` component (lines 80-112) from ConfigStudio.tsx. Import types from `./types`. Export as named export
- [X] T005 [P] Extract `CompensationInput` component to `planalign_studio/components/config/CompensationInput.tsx` — move the `CompensationInput` function (lines 114-149) from ConfigStudio.tsx. Export as named export
- [X] T006 [P] Create `buildConfigPayload` utility in `planalign_studio/components/config/buildConfigPayload.ts` — extract the payload construction logic from `handleSaveConfig` (lines 1340-1466 of ConfigStudio.tsx). Pure function signature: `(formData: FormData, promotionHazardConfig, bandConfig) => configPayload`. Include all percentage-to-decimal conversions and field name mappings. Import `FormData`, `calculateMatchCap` from local modules
- [X] T007 Create `ConfigContext` provider in `planalign_studio/components/config/ConfigContext.tsx` — implement the `ConfigContextType` interface from `specs/049-refactor-config-studio/contracts/ConfigContext.ts`. Extract from ConfigStudio.tsx: all shared useState hooks (lines 155-560, including `savedPromotionHazardConfig` at line 559 and `savedBandConfig` at line 560), the 5 useEffect hooks enumerated below, `dirtySections` useMemo (lines 910-991), `isDirty` useMemo (lines 901-907), `handleChange` (line 339), `inputProps` helper (line 1565), `handleSaveConfig` (lines 1327-1562 — use imported `buildConfigPayload`), `beforeunload` effect (lines 994-1005). Export `ConfigProvider` component and `useConfigContext` hook. Receive `activeWorkspace` and `scenarioId` as props from the shell. Create `currentScenario` state internally (useState at line 158 of original) — load it from the scenarios list using `scenarioId` within a useEffect.
  **5 useEffect hooks to extract** (critical — missing any one silently breaks a feature):
  1. **Config load from workspace** (~lines 564-680): loads `base_config` from `activeWorkspace` → populates `formData` defaults
  2. **Scenario config overlay** (~lines 682-780): if `scenarioId` present, loads `config_overrides` → overwrites `formData` fields
  3. **Seed config load** (~lines 782-900): loads band config + promotion hazard config from API → populates `bandConfig`, `promotionHazardConfig`, `savedBandConfig`, `savedPromotionHazardConfig`
  4. **savedFormData snapshot** (~lines 893-900): after initial load completes, sets `savedFormData` to a deep copy of `formData` for dirty comparison
  5. **beforeunload warning** (lines 994-1005): warns user on browser close/navigate if `isDirty`

**Checkpoint**: Foundation ready — `useConfigContext()` hook is available for all section components. Section extraction can begin.

---

## Phase 3: User Story 1 — Extract Section Components (Priority: P1)

**Goal**: Each of the 8 configuration sections becomes a standalone component file. ConfigStudio.tsx becomes a thin shell under 300 lines.

**Independent Test**: Verify each section file exists, contains only its relevant UI, and `ConfigStudio.tsx` is under 300 lines.

### Simple Sections (can all be extracted in parallel)

- [X] T008 [P] [US1] Extract `TurnoverSection` to `planalign_studio/components/config/TurnoverSection.tsx` — move lines 3156-3209 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `handleChange`, `inputProps`. No local state. Imports `InputField` from `./InputField`. ~70 lines
- [X] T009 [P] [US1] Extract `SimulationSection` to `planalign_studio/components/config/SimulationSection.tsx` — move lines 1965-2009 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `handleChange`, `inputProps`. No local state. Imports `InputField` from `./InputField`. ~60 lines

### Medium Sections (can all be extracted in parallel)

- [X] T010 [P] [US1] Extract `AdvancedSection` to `planalign_studio/components/config/AdvancedSection.tsx` — move lines 3854-4002 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `setFormData`, `handleChange`, `activeWorkspace`, `scenarioId`. Local state: `dbDeleteStatus`, `dbDeleteMessage`. Inline handler for `deleteScenarioDatabase` API call. ~170 lines
- [X] T011 [P] [US1] Extract `CompensationSection` to `planalign_studio/components/config/CompensationSection.tsx` — move lines 2012-2208 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `setFormData`, `handleChange`, `inputProps`, `activeWorkspace`. Local state: `targetCompGrowth`, `solverStatus`, `solverResult`, `solverError`. Local handler: `handleSolveCompensation` (calls `solveCompensationGrowth` API). Imports `InputField`. ~230 lines
- [X] T012 [P] [US1] Extract `DataSourcesSection` to `planalign_studio/components/config/DataSourcesSection.tsx` — move lines 1749-1962 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `setFormData`, `handleChange`, `activeWorkspace`, `currentScenario`, `scenarioId`. Local state: `uploadStatus`, `uploadMessage`, `fileInputRef`. Inline handlers for census file upload (`uploadCensusFile` API) and path validation (`validateFilePath` API). Also handles E089 auto-save via `updateScenario`. ~230 lines

### Complex Sections

- [X] T013 [P] [US1] Extract `SegmentationSection` to `planalign_studio/components/config/SegmentationSection.tsx` — move lines 2856-3153 from ConfigStudio.tsx. Uses `useConfigContext()` for `bandConfig`, `setBandConfig`, `saveStatus`, `activeWorkspace`. Local state: `bandConfigLoading`, `bandConfigError`, `bandValidationErrors`, `ageBandAnalysis`, `ageBandAnalyzing`, `tenureBandAnalysis`, `tenureBandAnalyzing`. Local handlers: `handleBandChange`, `validateBandsClient`, `handleMatchCensusAgeBands`, `handleApplyAgeBandSuggestions`, `handleMatchCensusTenureBands`, `handleApplyTenureBandSuggestions` (calls `analyzeAgeBands`/`analyzeTenureBands` APIs). ~330 lines
- [X] T014 [P] [US1] Extract `PromotionHazardEditor` to `planalign_studio/components/config/PromotionHazardEditor.tsx` — move lines 2697-2850 from ConfigStudio.tsx (currently embedded in the newhire section). Uses `useConfigContext()` for `promotionHazardConfig`, `setPromotionHazardConfig`. Local state: `promotionHazardLoading`, `promotionHazardError`, `promotionHazardValidationErrors`. Local handlers: `handlePromotionHazardBaseChange`, `handlePromotionHazardAgeMultiplierChange`, `handlePromotionHazardTenureMultiplierChange`, `validatePromotionHazardConfig`. ~170 lines
- [X] T015 [US1] Extract `NewHireSection` to `planalign_studio/components/config/NewHireSection.tsx` — move lines 2211-2853 from ConfigStudio.tsx (excluding the ~153-line promotion hazard block extracted in T014, so ~550 lines after extraction + import overhead). Uses `useConfigContext()` for `formData`, `setFormData`, `handleChange`, `activeWorkspace`. Local state: `matchCensusLoading/Error/Success`, `matchCompLoading/Error/Success`, `compensationAnalysis`, `compLookbackYears`, `compScaleFactor`, `compScaleLocal`. Local handlers: `handleAgeWeightChange`, `handleLevelPercentageChange`, `handleJobLevelCompChange`, `handleLevelAdjustmentChange`, `handleMatchCensus` (calls `analyzeAgeDistribution`), `handleMatchCompensation` (calls `analyzeCompensation`). Imports `PromotionHazardEditor` from `./PromotionHazardEditor` and `CompensationInput` from `./CompensationInput`. Depends on T014. ~550 lines
- [X] T016 [P] [US1] Extract `DCPlanSection` to `planalign_studio/components/config/DCPlanSection.tsx` — move lines 3212-3851 from ConfigStudio.tsx. Uses `useConfigContext()` for `formData`, `setFormData`, `handleChange`. Local handlers: `validateMatchTiers` for tenure/points gap/overlap validation, inline tier add/remove/edit handlers. Import `calculateMatchCap` and `MATCH_TEMPLATES` from `./constants`, `MatchTier` from `./types`. ~650 lines

### Modals

- [X] T017 [P] [US1] Extract `TemplateModal` to `planalign_studio/components/config/TemplateModal.tsx` — move lines 4008-4095 from ConfigStudio.tsx. Receives props: `show`, `onClose`, `templates`, `templatesLoading`. Uses `useConfigContext()` for `setFormData`. ~100 lines
- [X] T018 [P] [US1] Extract `CopyScenarioModal` to `planalign_studio/components/config/CopyScenarioModal.tsx` — move lines 4097-4339 from ConfigStudio.tsx. Receives props: `show`, `onClose`, `scenarios`, `scenariosLoading`. Uses `useConfigContext()` for `setFormData`, `setPromotionHazardConfig`, `setBandConfig`, `activeWorkspace`. Includes E100 census file validation and seed config copying logic. ~250 lines

### Shell Rewrite

- [X] T019 [US1] Rewrite `planalign_studio/components/ConfigStudio.tsx` as thin shell — replace entire file content. Import all section components from `./config/`, `ConfigProvider` from `./config/ConfigContext`, modal components from `./config/`. Render: `ConfigProvider` wrapper, header bar with back/save/run buttons (lines 1600-1708), sidebar navigation (lines 1710-1743), conditional section rendering (`activeSection === 'xxx'` for each section), template and copy-from-scenario modals. Local state: `activeSection`, `showTemplateModal`, `templates`, `templatesLoading`, `showCopyScenarioModal`, `availableScenarios`, `copyingScenariosLoading`. Target: under 300 lines. Depends on T007-T018

**Checkpoint**: All section files exist. ConfigStudio.tsx is under 300 lines. Each section file is self-contained.

---

## Phase 4: User Story 2 — Verify Behavioral Preservation (Priority: P1)

**Goal**: Confirm zero functional regression — dirty-tracking, save/load, all section interactions work identically.

**Independent Test**: Launch PlanAlign Studio, navigate to every section, edit fields, verify dirty indicators, save, reload, and confirm all values persist.

- [X] T020 [US2] Verify TypeScript compilation — run `cd planalign_studio && npx tsc --noEmit` (or equivalent Vite type-check). Fix any type errors across all 15+ new files. Ensure zero new compilation errors (SC-006)
- [X] T021 [US2] Verify dirty-tracking across all 8 sections — for each section, confirm the amber dot appears in the sidebar when a field is modified, and clears after save. Specifically verify: (1) simulation fields, (2) datasources census path, (3) compensation fields, (4) newhire fields including array modifications, (5) segmentation band config changes, (6) turnover rates, (7) DC plan tier edits, (8) advanced settings. Verify the `dirtySections` useMemo in ConfigContext.tsx covers all field comparisons from the original (lines 910-991)
- [X] T022 [US2] Verify save/load round-trip — confirm `handleSaveConfig` in ConfigContext.tsx correctly serializes all formData fields via `buildConfigPayload`, including: percentage-to-decimal conversions, array field mappings (age_distribution, level_distribution, match_tiers, tenure_match_tiers, points_match_tiers, core_graded_schedule), and promotion_hazard + band configs. Verify save to both workspace base_config and scenario config_overrides paths. Also verify save failure behavior: when the API returns an error, the error message MUST display in the shell header bar (saveStatus/saveMessage from context), not within any section component
- [X] T023 [US2] Verify modal functionality — confirm TemplateModal correctly applies template values to formData across all sections, and CopyScenarioModal correctly copies config including promotion hazard and band configs with E100 census validation
- [X] T024 [US2] Verify section-specific features — confirm: (1) DataSources census upload + path validation, (2) Compensation solver "magic button", (3) NewHire "Match Census" for age and compensation, (4) Segmentation "Match Census" for age/tenure bands, (5) DCPlan match tier add/remove/validate and auto-calculated match cap, (6) Advanced danger zone database delete, (7) Rapid section navigation: switch between sections while an async operation is in-flight (e.g., census upload, band analysis, compensation solver) and confirm loading states remain stable and don't leak across sections

**Checkpoint**: All behavioral acceptance scenarios from US2 pass. No user-visible changes from the original.

---

## Phase 5: User Story 3 — Verify Extensibility (Priority: P2)

**Goal**: Confirm the refactored architecture supports adding new sections without modifying existing section files.

**Independent Test**: Verify that adding a new section requires only: (1) new section file, (2) section registry entry in ConfigStudio, (3) dirty-tracking fields in ConfigContext.

- [X] T025 [US3] Verify extensibility pattern — review the final architecture and confirm: (1) `useConfigContext()` provides all needed state without prop drilling, (2) the section registry in ConfigStudio.tsx is a simple array that new sections are appended to, (3) dirty-tracking in ConfigContext.tsx has a clear per-section pattern that can be extended by adding a new block, (4) no section component imports or depends on another section component (except NewHireSection → PromotionHazardEditor which is a parent-child relationship, not a sibling dependency)

**Checkpoint**: Architecture supports extensibility as described in US3 acceptance scenarios.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup and verification of success criteria

- [X] T026 Verify ConfigStudio.tsx line count is under 300 lines (SC-001) — run `wc -l planalign_studio/components/ConfigStudio.tsx` and confirm < 300
- [X] T027 Verify all 8 section files exist and are self-contained (SC-002) — list all files in `planalign_studio/components/config/` and confirm each section file contains only its own UI logic
- [X] T028 Remove any dead code from the extraction — check for unused imports, commented-out code, or leftover fragments in ConfigStudio.tsx or section files
- [X] T029 Verify no section component exceeds 700 lines — run line counts on all files in `planalign_studio/components/config/` to ensure modular architecture is maintained

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: T004-T006 can start after Phase 1. T007 depends on T002, T003, T006
- **US1 (Phase 3)**: All section tasks depend on T007 (ConfigContext). Section tasks marked [P] can run in parallel. T015 (NewHireSection) depends on T014 (PromotionHazardEditor). T019 (shell rewrite) depends on all T008-T018
- **US2 (Phase 4)**: All tasks depend on T019 (complete shell rewrite)
- **US3 (Phase 5)**: Depends on Phase 4 completion
- **Polish (Phase 6)**: Depends on Phase 4 completion

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — structural extraction
- **US2 (P1)**: Depends on US1 completion — behavioral verification
- **US3 (P2)**: Depends on US2 completion — extensibility verification

### Within Phase 3 (US1): Task Dependency Graph

```text
T007 (ConfigContext) ──┬──→ T008 (Turnover)      ─┐
                       ├──→ T009 (Simulation)     ─┤
                       ├──→ T010 (Advanced)       ─┤
                       ├──→ T011 (Compensation)   ─┤
                       ├──→ T012 (DataSources)    ─┤
                       ├──→ T013 (Segmentation)   ─┤
                       ├──→ T014 (PromoHazard) ──→ T015 (NewHire) ─┤
                       ├──→ T016 (DCPlan)         ─┤
                       ├──→ T017 (TemplateModal)  ─┤
                       └──→ T018 (CopyScnModal)   ─┤
                                                   └──→ T019 (Shell Rewrite)
```

### Parallel Opportunities

**Maximum parallelism in Phase 3**: After T007, up to 10 tasks can run in parallel:
- T008, T009, T010, T011, T012, T013, T014, T016, T017, T018

**Sequential constraints**:
- T014 → T015 (PromotionHazardEditor before NewHireSection)
- All T008-T018 → T019 (all sections before shell rewrite)

---

## Parallel Example: Phase 3 Section Extraction

```text
# After T007 (ConfigContext) is complete, launch all independent sections:
Parallel batch 1 (10 tasks):
  T008: TurnoverSection.tsx
  T009: SimulationSection.tsx
  T010: AdvancedSection.tsx
  T011: CompensationSection.tsx
  T012: DataSourcesSection.tsx
  T013: SegmentationSection.tsx
  T014: PromotionHazardEditor.tsx
  T016: DCPlanSection.tsx
  T017: TemplateModal.tsx
  T018: CopyScenarioModal.tsx

# After T014 completes:
Sequential:
  T015: NewHireSection.tsx (imports PromotionHazardEditor)

# After ALL T008-T018 complete:
Sequential:
  T019: Rewrite ConfigStudio.tsx shell
```

---

## Implementation Strategy

### MVP First (US1 Complete)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T007)
3. Complete Phase 3: US1 — Extract all sections (T008-T019)
4. **STOP and VALIDATE**: TypeScript compiles, ConfigStudio < 300 lines
5. Proceed to Phase 4: US2 verification

### Incremental Delivery

1. Setup + Foundational → Types, constants, context, and UI components ready
2. Extract simple sections first (T008-T009) → Quick wins, validate pattern works
3. Extract medium sections (T010-T012) → Build confidence with more complex state
4. Extract complex sections (T013-T016) → Largest files, most state migration
5. Extract modals + rewrite shell (T017-T019) → Final assembly
6. Verify everything (T020-T029) → Full validation sweep

### Risk Mitigation

- **Highest risk task**: T007 (ConfigContext) — contains all shared state, effects, and save handler. If this is wrong, everything downstream breaks. Allocate extra attention here.
- **Second highest risk**: T019 (Shell Rewrite) — must correctly wire all imports and conditional rendering. This is the integration point.
- **Mitigation**: After T007, extract a simple section (T008 or T009) first and verify the `useConfigContext()` pattern works before extracting all remaining sections.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- No test tasks included — no frontend test framework exists in this project
- Verification in Phase 4 is manual + TypeScript compilation
- Commit after each task or logical group (e.g., after all simple sections)
- The formData shape must be preserved EXACTLY — no field renames, type changes, or default value modifications
