# Tasks: Dark Mode Token Layer

**Input**: Design documents from `/specs/139-dark-mode-tokens/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Required by the specification's measurable outcomes and the project
constitution. Write each test task first and confirm it fails for the intended
reason before implementing the corresponding production task.

**Organization**: Tasks are grouped by user story. User Story 1 is the semantic-
token MVP; User Story 2 depends on those tokens for custom chart content; User
Story 3 ships only after both migration gates pass.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after its stated prerequisite because it touches
  different files and does not depend on another incomplete parallel task.
- **[Story]**: Maps the task to User Story 1, 2, or 3 from `spec.md`.
- Every task names the exact file or files it changes or validates.

---

## Phase 1: Setup (Shared Test and Frontend Infrastructure)

**Purpose**: Establish dependency-free fixtures and TypeScript support shared
by all three stories.

- [X] T001 [P] Create reusable repository paths and dynamic component/Recharts discovery helpers with asserted 54-component, 12-consumer, and 30-chart baselines, plus published retired/light palette fixtures and a palette JSON loader in `tests/fixtures/studio_theme.py`
- [X] T002 [P] Enable typed JSON module imports for the single shared palette source in `planalign_studio/tsconfig.json`

**Checkpoint**: Shared fixtures and frontend compiler support are ready; no
runtime behavior has changed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reconstruct the missing #497/#503 validation gate and establish
closed theme types/context before story work begins.

**⚠️ CRITICAL**: Complete this phase before implementing any user story.

- [X] T003 [P] Add failing tests that reproduce the retired-ramp lightness/normal-separation failures, accepted light-ramp hard passes and warnings, and accepted-light-on-dark-surface failure in `tests/unit/test_studio_palette.py`
- [X] T004 Implement the dependency-free hex/sRGB, OKLCH lightness/chroma, normal/CVD separation, surface-contrast, ordered reporting, and nonzero-on-hard-failure validator documented in research D5 in `scripts/validate_studio_palette.py` (depends on T003)
- [X] T005 Select six same-hue dark candidates in the light ramp's fixed slot order, iterate only through the reconstructed validator until hard failures are zero, and store validation surfaces, retired/light fixtures, light runtime slots, dark runtime slots, and warning mitigations in `planalign_studio/theme/chart-palettes.json` (depends on T004)
- [X] T006 [P] Add failing source-contract tests for closed `ThemePreference`/`ResolvedTheme` values, one storage key, guarded explicit-preference helpers, one theme context, and hook access in `tests/unit/test_studio_theme_contract.py`
- [X] T007 Implement the closed theme types, context, versioned storage key, guarded read/write/remove helpers, system media-query resolver, and context-only hook in `planalign_studio/theme/theme.ts` and `planalign_studio/hooks/useTheme.ts` (depends on T006)
- [X] T008 Run the foundational red/green gate and resolve only validator/type-contract defects in `tests/unit/test_studio_palette.py`, `tests/unit/test_studio_theme_contract.py`, `scripts/validate_studio_palette.py`, and `planalign_studio/theme/theme.ts`

**Checkpoint**: The published palette audit is executable and reproducible,
the dark ramp is accepted but not user-accessible, and one type-safe theme
authority is ready for consumers.

---

## Phase 3: User Story 1 - Semantic Surface Tokens Power Every Screen (Priority: P1) 🎯 MVP

**Goal**: Replace literal light-only layout/status colors with semantic roles so
one token change restyles every current Studio component.

**Independent Test**: Change one light semantic token in `index.css`, build
Studio, and confirm every migrated consumer changes through that token while
the dynamic scan reports zero `bg-white`, `text-gray-*`,
`border-gray/slate-*`, or inline neutral layout colors across all 54 component
TSX files and `App.tsx`.

### Tests for User Story 1

- [X] T009 [US1] Extend the failing source contract with required surface/text/border/input/disabled/overlay/status token families, `@theme inline` mappings, a dynamic component-tree scan, and narrow documented allowlist rules in `tests/unit/test_studio_theme_contract.py`

### Implementation for User Story 1

- [X] T010 [US1] Define light raw values—including the exact light raised/chart surface from the validated palette source—semantic Tailwind v4 `@theme inline` mappings, body defaults, focus/input/disabled/overlay roles, and paired success/warning/danger/info roles in `planalign_studio/index.css` (depends on T009)
- [X] T011 [P] [US1] Migrate error/placeholder states and all shell/loading/error/empty/modal/menu/header/sidebar surfaces by semantic role in `planalign_studio/App.tsx` and `planalign_studio/components/Layout.tsx` (depends on T010)
- [X] T012 [P] [US1] Migrate dashboard, workspace, scenario, and plan-design surfaces—including hover, selected, disabled, and status states—in `planalign_studio/components/Dashboard.tsx`, `planalign_studio/components/WorkspaceManager.tsx`, `planalign_studio/components/ScenariosPage.tsx`, and `planalign_studio/components/PlanDesignModal.tsx` (depends on T010)
- [X] T013 [P] [US1] Migrate the import flow's panels, inputs, mappings, previews, errors, and file states in `planalign_studio/components/DataImportWizard.tsx`, `planalign_studio/components/imports/FieldMappingStep.tsx`, `planalign_studio/components/imports/FileUploadStep.tsx`, `planalign_studio/components/imports/ImportedFilesList.tsx`, and `planalign_studio/components/imports/PreviewStep.tsx` (depends on T010)
- [X] T014 [P] [US1] Migrate the configuration shell/context controls and shared field primitives in `planalign_studio/components/ConfigStudio.tsx`, `planalign_studio/components/config/ConfigContext.tsx`, `planalign_studio/components/config/InputField.tsx`, and `planalign_studio/components/config/CompensationInput.tsx` (depends on T010)
- [X] T015 [P] [US1] Migrate configuration modal surfaces, form controls, overlays, and action states in `planalign_studio/components/config/ApplyWorkforceParamsModal.tsx`, `planalign_studio/components/config/CopyScenarioModal.tsx`, and `planalign_studio/components/config/TemplateModal.tsx` (depends on T010)
- [X] T016 [P] [US1] Migrate general configuration section surfaces and feedback roles in `planalign_studio/components/config/AdvancedSection.tsx`, `planalign_studio/components/config/CompensationSection.tsx`, `planalign_studio/components/config/DataSourcesSection.tsx`, `planalign_studio/components/config/SegmentationSection.tsx`, and `planalign_studio/components/config/SimulationSection.tsx` (depends on T010)
- [X] T017 [P] [US1] Migrate workforce-behavior editor surfaces, controls, tables, helper copy, and validation states in `planalign_studio/components/config/NewHireSection.tsx`, `planalign_studio/components/config/PromotionHazardEditor.tsx`, `planalign_studio/components/config/TenureGradedMatchEditor.tsx`, `planalign_studio/components/config/TurnoverSection.tsx`, and `planalign_studio/components/config/WorkforceParametersSection.tsx` (depends on T010)
- [X] T018 [P] [US1] Migrate the large DC-plan configuration surface by distinguishing panel/input/subtle/disabled/status roles rather than mechanically replacing gray steps in `planalign_studio/components/config/DCPlanSection.tsx` (depends on T010)
- [X] T019 [P] [US1] Migrate simulation control/detail/batch panels, tables, progress states, overlays, and errors in `planalign_studio/components/SimulationControl.tsx`, `planalign_studio/components/SimulationDetail.tsx`, and `planalign_studio/components/BatchProcessing.tsx` (depends on T010)
- [X] T020 [P] [US1] Migrate calibration and optimizer forms, candidate/result tables, status feedback, and non-chart surfaces in `planalign_studio/components/CalibrationPanel.tsx` and `planalign_studio/components/OptimizerPanel.tsx` (depends on T010)
- [X] T021 [P] [US1] Migrate analytics and DC-plan cards, filters, tables, custom tooltip markup, legends, labels, and status surfaces in `planalign_studio/components/AnalyticsDashboard.tsx`, `planalign_studio/components/DCPlanAnalytics.tsx`, and `planalign_studio/components/DCPlanComparisonSection.tsx` (depends on T010)
- [X] T022 [P] [US1] Migrate comparison/diff selectors, cards, tables, badges, legends, and anchor/summary surfaces in `planalign_studio/components/ScenarioComparison.tsx`, `planalign_studio/components/ScenarioCostComparison.tsx`, and `planalign_studio/components/ScenarioDiff.tsx` (depends on T010)
- [X] T023 [P] [US1] Migrate forfeiture, vesting, winners/losers, and NDT panels, tables, status badges, custom labels, and non-chart feedback in `planalign_studio/components/ForfeitureProjection.tsx`, `planalign_studio/components/VestingAnalysis.tsx`, `planalign_studio/components/WinnersLosersTab.tsx`, and `planalign_studio/components/NDTTesting.tsx` (depends on T010)
- [X] T024 [P] [US1] Migrate evidence and provenance headers, sections, code blocks, warnings, copy/download states, and errors in `planalign_studio/components/EvidencePackPanel.tsx` and `planalign_studio/components/RunProvenanceReport.tsx` (depends on T010)
- [X] T025 [P] [US1] Migrate live-simulation activity, connection, statistics, logs, and performance-card surfaces and statuses in `planalign_studio/components/simulation/ActivityFeed.tsx`, `planalign_studio/components/simulation/ConnectionStatusBadge.tsx`, `planalign_studio/components/simulation/LiveStatsPanel.tsx`, `planalign_studio/components/simulation/LogViewer.tsx`, and `planalign_studio/components/simulation/PerformanceTrendChart.tsx` (depends on T010)
- [X] T026 [P] [US1] Migrate employee search, timeline page, column, and year surfaces—including filters, event states, empty results, and borders—in `planalign_studio/components/timeline/EmployeeSearch.tsx`, `planalign_studio/components/timeline/EmployeeTimelinePage.tsx`, `planalign_studio/components/timeline/TimelineColumn.tsx`, and `planalign_studio/components/timeline/TimelineYear.tsx` (depends on T010)
- [X] T027 [US1] Make the full semantic-token scan pass with no broad allowlist, verify a temporary light-token edit propagates without component changes, then run TypeScript/Vite gates against `tests/unit/test_studio_theme_contract.py`, `planalign_studio/index.css`, and `specs/139-dark-mode-tokens/quickstart.md` (depends on T011-T026)

**Checkpoint**: User Story 1 is independently complete. Studio remains
light-presented but every current surface is controlled by semantic roles.

---

## Phase 4: User Story 2 - Charts Read Color from a Theme-Aware Source (Priority: P2)

**Goal**: Route every Recharts grid, axis, tooltip, cursor, legend/label, and
series role through one typed source with stable six-slot overflow behavior.

**Independent Test**: Run the dynamic Recharts contract over all 12 importers
and render each chart type; every chart explicitly consumes
`useChartTheme()`, no chart color literal/local palette/default remains, and
selecting the other resolved theme returns a different complete map without
consumer-specific theme logic.

### Tests for User Story 2

- [X] T028 [P] [US2] Add failing dynamic Recharts contract assertions requiring `useChartTheme()`, explicit grid/axis/tooltip/cursor/legend handling, themed series/reference roles, secondary identity cues, and no local palette or implicit light default in `tests/unit/test_studio_theme_contract.py`
- [X] T029 [P] [US2] Add failing tests for two complete immutable chart maps, exactly six unique slots, fixed light/dark hue order, all semantic roles, direct indices, normalized modulo overflow, and runtime palette-source parity in `tests/unit/test_studio_palette.py`

### Implementation for User Story 2

- [X] T030 [US2] Implement immutable light/dark `ChartTheme` maps, ready-to-spread tooltip/cursor styles, neutral legend text, semantic series roles, normalized modulo `colorAt`, and resolved-context selection in `planalign_studio/theme/chartTheme.ts` and `planalign_studio/hooks/useChartTheme.ts` (depends on T028-T029)
- [X] T031 [P] [US2] Remove superseded `COLORS.charts`, `CONTRIBUTION_COLORS`, and `COMPARISON_COLORS` chart authorities while preserving unrelated application constants in `planalign_studio/constants.ts` (depends on T030)
- [X] T032 [P] [US2] Migrate every grid, axis, tooltip, cursor, legend/label, categorical/fixed series, and custom tooltip in `planalign_studio/components/AnalyticsDashboard.tsx`, `planalign_studio/components/DCPlanAnalytics.tsx`, and `planalign_studio/components/DCPlanComparisonSection.tsx` to `useChartTheme()` (depends on T030)
- [X] T033 [P] [US2] Migrate default and explicit chart styling, frontier/reference roles, and performance series in `planalign_studio/components/CalibrationPanel.tsx`, `planalign_studio/components/OptimizerPanel.tsx`, and `planalign_studio/components/simulation/PerformanceTrendChart.tsx` to `useChartTheme()` (depends on T030)
- [X] T034 [P] [US2] Migrate comparison grids, axes, tooltips, neutral legends, anchor/baseline roles, and stable scenario slots in `planalign_studio/components/ScenarioComparison.tsx`, `planalign_studio/components/ScenarioCostComparison.tsx`, and `planalign_studio/components/ScenarioDiff.tsx` to `useChartTheme()` (depends on T030)
- [X] T035 [P] [US2] Migrate area/bar grids, axes, tooltip cursors, vesting pairs, and winner/loser/neutral roles in `planalign_studio/components/ForfeitureProjection.tsx`, `planalign_studio/components/VestingAnalysis.tsx`, and `planalign_studio/components/WinnersLosersTab.tsx` to `useChartTheme()` (depends on T030)
- [X] T036 [US2] Run the Recharts inventory/palette tests, direct chart-literal search, TypeScript check, and production build and resolve all failures in `tests/unit/test_studio_theme_contract.py`, `tests/unit/test_studio_palette.py`, and the 12 Recharts consumer files enumerated by `tests/fixtures/studio_theme.py` (depends on T031-T035)

**Checkpoint**: User Stories 1 and 2 are complete. All layout and chart colors
have shared authorities, while the user-facing dark control remains withheld.

---

## Phase 5: User Story 3 - Users Can Switch Between Light and Dark Themes (Priority: P3)

**Goal**: Ship a no-flash, system-aware, persistent, accessible theme control
that updates every surface/chart without reload or state loss.

**Independent Test**: With no stored value, first-paint and live-follow both OS
themes; choose Light or Dark and confirm persistence/OS precedence; return to
System; switch themes with an unsaved Configure value; then inspect every route
and chart in both modes with no light-only surface or palette failure.

### Tests for User Story 3

- [X] T037 [US3] Add failing source contracts for pre-mount bootstrap ordering, one shared storage key/value set, guarded storage behavior, provider-above-`App`, root `data-theme`/`color-scheme`, cleaned-up system media subscription, no reload/remount key, and accessible System/Light/Dark settings semantics in `tests/unit/test_studio_theme_contract.py`

### Implementation for User Story 3

- [X] T038 [US3] Implement `ThemeProvider` initialization, explicit persistence/removal, live system media updates, StrictMode-safe cleanup, document synchronization, toggle/reset actions, and storage-error fallback in `planalign_studio/theme/ThemeProvider.tsx` (depends on T037)
- [X] T039 [P] [US3] Add the local pre-paint stored/system resolver and `color-scheme` metadata before the app module in `planalign_studio/index.html`, then mount `ThemeProvider` above `App` without a theme-dependent key in `planalign_studio/index.tsx` (depends on T038)
- [X] T040 [P] [US3] Add independently chosen dark raw values for every semantic surface/text/border/input/disabled/overlay/status/chart token, bind the raised/chart surface to the exact validator surface, and add root `color-scheme` behavior and dark body defaults in `planalign_studio/index.css` (depends on T037)
- [X] T041 [P] [US3] Replace the dormant local `isDarkMode` boolean with an accessible Settings button label and System/Light/Dark radio group wired to `useTheme()` while preserving open menus and route state in `planalign_studio/components/Layout.tsx` (depends on T038)
- [X] T042 [US3] Run the preference/bootstrap source contract, palette validator, semantic/Recharts scans, TypeScript check, and production build and resolve all failures in `tests/unit/test_studio_theme_contract.py`, `tests/unit/test_studio_palette.py`, `planalign_studio/theme/ThemeProvider.tsx`, `planalign_studio/index.html`, `planalign_studio/index.tsx`, `planalign_studio/index.css`, and `planalign_studio/components/Layout.tsx` (depends on T039-T041)
- [ ] T043 [US3] Execute the System/Light/Dark, live OS change, explicit precedence, reload persistence, reset, invalid/unavailable storage, and unsaved Configure state-preservation scenarios and record results in `specs/139-dark-mode-tokens/quickstart.md` (depends on T042)
- [ ] T044 [US3] Execute the two-theme route/shell/modal/form/table/status and 30-chart browser matrix at desktop and approximately 900px, including six-slot and modulo-overflow cases, and record defects/results in `specs/139-dark-mode-tokens/quickstart.md` (depends on T043)

**Checkpoint**: All three stories are independently verifiable and the complete
dark-mode experience is ready for final cross-cutting review.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify warning mitigations, documentation, and repository-wide
quality gates after all desired stories are complete.

- [X] T045 Review every published palette warning against legend plus table/direct-label secondary encoding and correct any gap in `planalign_studio/components/AnalyticsDashboard.tsx`, `planalign_studio/components/DCPlanAnalytics.tsx`, `planalign_studio/components/DCPlanComparisonSection.tsx`, `planalign_studio/components/ForfeitureProjection.tsx`, `planalign_studio/components/OptimizerPanel.tsx`, `planalign_studio/components/ScenarioComparison.tsx`, `planalign_studio/components/ScenarioCostComparison.tsx`, `planalign_studio/components/VestingAnalysis.tsx`, and `planalign_studio/components/WinnersLosersTab.tsx`
- [X] T046 Run the complete fast theme/palette tests, direct validator, legacy-color searches, TypeScript check, and Vite build exactly as documented and append the final command outcomes to `specs/139-dark-mode-tokens/quickstart.md`
- [ ] T047 Review keyboard focus, accessible names/radio state, native control `color-scheme`, reduced viewport behavior, and console output in both themes and record final accessibility observations in `specs/139-dark-mode-tokens/quickstart.md`
- [X] T048 Remove obsolete theme/color code and unjustified allowlists, confirm no API/dbt/database/export change entered the diff, and run `git diff --check` against `planalign_studio/`, `scripts/validate_studio_palette.py`, `tests/fixtures/studio_theme.py`, `tests/unit/test_studio_palette.py`, and `tests/unit/test_studio_theme_contract.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: No dependencies; T001 and T002 can run in parallel.
- **Phase 2 — Foundational**: Depends on Phase 1 and blocks every story. T003
  and T006 can start in parallel; each implementation follows its failing test.
- **Phase 3 — User Story 1**: Depends on Phase 2. T011–T026 can run in parallel
  after the semantic CSS contract and T010 exist; T027 joins them.
- **Phase 4 — User Story 2**: Depends on User Story 1 because custom tooltips,
  legends, and chart containers use its semantic tokens. T028 and T029 can run
  in parallel; T031–T035 can run in parallel after T030; T036 joins them.
- **Phase 5 — User Story 3**: Depends on User Stories 1 and 2 so no partially
  themed UI can be exposed. T039–T041 can run in parallel after T038 and the
  failing contract exists; T042 joins them before manual validation.
- **Phase 6 — Polish**: Depends on all desired user stories.

### User Story Dependency Graph

```text
Setup → Foundational → US1 (semantic surfaces) → US2 (themed charts) → US3 (theme control) → Polish
```

- **US1 (P1)**: First independently deliverable increment and suggested MVP.
- **US2 (P2)**: Requires US1 token roles for chart HTML/custom content but can
  be tested independently once US1 is present.
- **US3 (P3)**: Requires both migrations and the validated dark ramp; it is the
  only phase that exposes theme selection to users.

### Within Each User Story

- Write each story's test tasks and confirm the expected failure first.
- Add the shared model/source before migrating consumers.
- Parallel component migrations must touch disjoint files.
- Join all parallel work at the story validation task.
- Do not move to the next story until the current checkpoint passes.

### Parallel Opportunities

- **Setup**: T001 and T002.
- **Foundational**: T003 and T006; validator and theme-type work then proceed on
  separate files.
- **US1**: T011–T026 after T010, split across disjoint component groups.
- **US2**: T028 and T029; then T031–T035 after T030.
- **US3**: T039–T041 after T038.
- Tests/build/manual joins are intentionally sequential to validate the merged
  story state.

---

## Parallel Example: User Story 1

After T010, launch disjoint migration groups together:

```text
Task T011: Migrate App.tsx and Layout.tsx shell surfaces.
Task T013: Migrate DataImportWizard.tsx and components/imports/*.tsx.
Task T018: Migrate components/config/DCPlanSection.tsx.
Task T025: Migrate components/simulation/*.tsx.
Task T026: Migrate components/timeline/*.tsx.
```

Join all groups at T027 and run the dynamic scan before starting US2.

## Parallel Example: User Story 2

After T030 creates the shared hook/maps:

```text
Task T032: Migrate AnalyticsDashboard/DCPlan chart consumers.
Task T033: Migrate Calibration/Optimizer/Performance chart consumers.
Task T034: Migrate Scenario comparison/diff chart consumers.
Task T035: Migrate Forfeiture/Vesting/Winners-Losers chart consumers.
```

Join the four groups at T036.

## Parallel Example: User Story 3

After T038 creates the provider:

```text
Task T039: Wire pre-paint bootstrap and root provider mount.
Task T040: Define the complete dark semantic token values.
Task T041: Wire the accessible Settings preference control.
```

Join at T042 before any manual preference or visual acceptance work.

---

## Implementation Strategy

### MVP First — User Story 1

1. Complete Setup and Foundational phases.
2. Complete the semantic-token test and CSS source.
3. Run the disjoint component migrations.
4. Stop at T027 and validate the light-presented semantic-token layer.
5. Demo that one token change restyles all migrated screens without shipping a
   dark control.

### Incremental Delivery

1. **Foundation**: Executable palette audit plus closed theme types.
2. **US1 / MVP**: All layout and status surfaces use semantic tokens.
3. **US2**: All chart primitives and series use one typed theme source.
4. **US3**: Dark values and accessible persistent/system control become visible.
5. **Polish**: Complete warning, accessibility, build, and visual gates.

Each checkpoint produces a testable repository state and does not require a
simulation/database mutation.

### Parallel Team Strategy

1. Complete shared Setup/Foundational test-first work together.
2. For US1, split T011–T026 by disjoint component group and join at T027.
3. For US2, split the four chart-consumer groups and join at T036.
4. Keep provider/bootstrap/control integration coordinated in US3, with CSS and
   Settings work parallel only after the provider contract is stable.

---

## Notes

- `[P]` tasks still respect the prerequisite named in their description or
  phase dependency; the marker only means their file edits do not conflict.
- The dark palette is selected by executable validation, never inversion or
  per-view judgment.
- Keep broad mechanical replacements out of the migration; map each element to
  its semantic role.
- Existing modulo overflow behavior is preserved; do not extend the validated
  six-slot ramp silently.
- Browser validation is required because the repository has no frontend test
  runner; source contracts and builds do not prove first-paint or visual state.
- Do not run dbt or write `dbt/simulation.duckdb` for this frontend-only feature.
- Do not commit or create a branch unless explicitly requested.
