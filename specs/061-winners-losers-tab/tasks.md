# Tasks: Winners & Losers Comparison Tab

**Input**: Design documents from `/specs/061-winners-losers-tab/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md

**Tests**: Included for backend service (constitution requires test-first for core modules).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new files and shared Pydantic models needed by all user stories

- [x] T001 [P] Create Pydantic response models (BandGroupResult, HeatmapCell, WinnersLosersResponse) in planalign_api/models/winners_losers.py per data-model.md
- [x] T002 [P] Create WinnersLosersService skeleton with constructor accepting WorkspaceStorage and DatabasePathResolver in planalign_api/services/winners_losers_service.py
- [x] T003 [P] Add `getWinnersLosersComparison(workspaceId, planA, planB)` function to planalign_studio/services/api.ts returning the WinnersLosersResponse type
- [x] T004 [P] Create WinnersLosersTab.tsx component skeleton in planalign_studio/components/WinnersLosersTab.tsx with workspace/scenario loading (copy pattern from DCPlanAnalytics.tsx)

**Checkpoint**: All new files exist. Models compile. Component renders empty shell.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend comparison engine — the core logic that all frontend stories depend on

**⚠️ CRITICAL**: No user story visualization work can begin until comparison endpoint returns data

- [x] T005 Write unit test for classify logic (winner/loser/neutral) and band aggregation in tests/test_winners_losers.py using in-memory DuckDB with sample fct_workforce_snapshot data
- [x] T006 Implement `_query_scenario_contributions(conn, final_year)` private method in planalign_api/services/winners_losers_service.py — queries fct_workforce_snapshot for active employees at final simulation year, returns DataFrame with employee_id, age_band, tenure_band, employer_match_amount + employer_core_amount as employer_total
- [x] T007 Implement `_classify_employees(df_a, df_b)` private method in planalign_api/services/winners_losers_service.py — INNER JOIN on employee_id, compute delta, assign winner/loser/neutral status, return merged DataFrame
- [x] T008 Implement `_aggregate_results(merged_df)` private method in planalign_api/services/winners_losers_service.py — group by age_band, tenure_band, and (age_band, tenure_band) to produce age_band_results, tenure_band_results, and heatmap lists
- [x] T009 Implement public `analyze(workspace_id, plan_a, plan_b)` method in planalign_api/services/winners_losers_service.py — orchestrates resolve DB paths → query both scenarios → classify → aggregate → return WinnersLosersResponse. Include total_excluded count for employees in only one scenario.
- [x] T010 Add GET endpoint at /api/workspaces/{workspace_id}/analytics/winners-losers in planalign_api/routers/analytics.py with Query params plan_a and plan_b, validation (both scenarios exist and completed), dependency injection for WinnersLosersService
- [x] T011 Run tests/test_winners_losers.py and verify classification + aggregation tests pass

**Checkpoint**: `curl /api/workspaces/{wid}/analytics/winners-losers?plan_a=X&plan_b=Y` returns JSON with age_band_results, tenure_band_results, heatmap.

---

## Phase 3: User Story 1 — Compare Two Plans by Age Band (Priority: P1) 🎯 MVP

**Goal**: Display bar chart of winner/loser counts by age band when two scenarios are selected

**Independent Test**: Select two completed scenarios → age band bar chart shows winner/loser bars for each band with tooltips

### Implementation for User Story 1

- [x] T012 [US1] Add route for WinnersLosersTab in planalign_studio/App.tsx at path "analytics/winners-losers"
- [x] T013 [US1] Add "Winners & Losers" NavItem in planalign_studio/components/Layout.tsx sidebar (use Scale or GitCompare icon from lucide-react, place after existing analytics nav items)
- [x] T014 [US1] Implement Plan A and Plan B scenario selectors in WinnersLosersTab.tsx header — two dropdowns showing only completed scenarios, Plan A defaults to baseline (FR-003), Plan B defaults to first non-Plan-A scenario (FR-004)
- [x] T015 [US1] Implement summary banner in WinnersLosersTab.tsx showing total winners, losers, neutral, and excluded count (FR-011) using KPI-card style from AnalyticsDashboard
- [x] T016 [US1] Implement age band bar chart in WinnersLosersTab.tsx using Recharts BarChart with grouped bars for winners (green) and losers (red) per age band (FR-006), with tooltips showing count and percentage (FR-009)

**Checkpoint**: Navigate to Winners & Losers tab, select two scenarios, see age band bar chart with summary banner.

---

## Phase 4: User Story 2 — Compare Two Plans by Tenure Band (Priority: P1)

**Goal**: Display tenure band bar chart below the age band chart

**Independent Test**: With two scenarios selected, tenure band bar chart renders below age band chart with correct band labels

### Implementation for User Story 2

- [x] T017 [US2] Add tenure band bar chart in WinnersLosersTab.tsx below the age band chart, same Recharts BarChart pattern as T016 but using tenure_band_results data (FR-007), with tooltips (FR-009)

**Checkpoint**: Both age band and tenure band charts visible, counts sum to same total.

---

## Phase 5: User Story 3 — View Age × Tenure Heatmap (Priority: P2)

**Goal**: Display heatmap grid of age bands vs tenure bands with diverging color scale

**Independent Test**: With two scenarios selected, a color-coded grid appears below the bar charts. Green cells = net winners, red cells = net losers, gray = empty.

### Implementation for User Story 3

- [x] T018 [US3] Implement CSS Grid heatmap component section in WinnersLosersTab.tsx with age bands as rows and tenure bands as columns (FR-008). Use Tailwind classes for diverging color scale: green shades for net winners, red shades for net losers, gray for empty/zero cells. Color intensity proportional to net_pct.
- [x] T019 [US3] Add interactive tooltips to heatmap cells showing "X Winners / Y Losers (Z total)" on hover, and "No employees in this group" for empty cells (FR-009)

**Checkpoint**: Heatmap grid renders below bar charts. Cells are correctly colored. Tooltips work.

---

## Phase 6: User Story 4 — Change Plan Selections (Priority: P2)

**Goal**: Changing Plan A or Plan B dropdowns re-fetches data and updates all visualizations

**Independent Test**: Change Plan B dropdown → all charts and heatmap update. Set Plan A = Plan B → all employees show neutral.

### Implementation for User Story 4

- [x] T020 [US4] Wire useEffect in WinnersLosersTab.tsx to re-fetch comparison data whenever planA or planB state changes, with loading spinner during fetch
- [x] T021 [US4] Persist plan selections via URL search params (?plan_a=...&plan_b=...) in WinnersLosersTab.tsx using useSearchParams, and restore on mount (FR-012)

**Checkpoint**: Switching scenarios updates all visualizations. URL reflects current selections.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error states, and robustness

- [x] T022 Handle edge case: fewer than 2 completed scenarios — show message "At least two completed scenarios are required to compare winners and losers." in WinnersLosersTab.tsx
- [x] T023 Handle edge case: empty bands (zero employees) — show band in chart with zero-height bar; show gray cell in heatmap
- [x] T024 Handle error states in WinnersLosersTab.tsx — show ErrorState component on API failure, EmptyState when no data
- [x] T025 Verify SC-003: add a visual consistency check that age band totals = tenure band totals = summary banner total (display warning if mismatch)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — all T001-T004 can run in parallel
- **Phase 2 (Foundational)**: Depends on T001 (models) and T002 (service skeleton). BLOCKS all frontend visualization work.
- **Phase 3 (US1)**: Depends on Phase 2 completion (need working API endpoint)
- **Phase 4 (US2)**: Depends on Phase 3 (same component, adds below age chart)
- **Phase 5 (US3)**: Depends on Phase 3 (adds heatmap section to same component)
- **Phase 6 (US4)**: Depends on Phase 3 (needs working component with data flow)
- **Phase 7 (Polish)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (Age Band Chart)**: Requires foundational API — gateway story, must complete first
- **US2 (Tenure Band Chart)**: Requires US1 component structure — adds a section below age chart
- **US3 (Heatmap)**: Requires US1 component structure — adds a section below charts
- **US4 (Plan Switching)**: Requires US1 data flow — wires re-fetch on selection change

### Within Each Phase

- Models (T001) before service (T006-T009)
- Service methods sequentially: query → classify → aggregate → orchestrate
- API endpoint (T010) after service is complete
- Frontend: route + nav (T012-T013) before component features (T014-T016)

### Parallel Opportunities

```
Phase 1 (all parallel):
  T001 (models) || T002 (service skeleton) || T003 (api.ts) || T004 (component skeleton)

Phase 2 (sequential within, parallel tests):
  T005 (tests) → T006 → T007 → T008 → T009 → T010 → T011

Phase 3 + 4 (sequential):
  T012 || T013 → T014 → T015 → T016 → T017

Phase 5 + 6 (can parallel after US1):
  T018 → T019  ||  T020 → T021
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (all 4 tasks in parallel)
2. Complete Phase 2: Foundational backend (test → service → endpoint)
3. Complete Phase 3: US1 — Age band chart with summary banner
4. Complete Phase 4: US2 — Tenure band chart
5. **STOP and VALIDATE**: Both bar charts render, counts consistent, tooltips work
6. Deploy/demo — this is the P1 MVP

### Incremental Delivery

1. **MVP**: Setup + Foundation + US1 + US2 → Two bar charts with summary
2. **Enhancement**: US3 → Heatmap grid adds intersection analysis
3. **Polish**: US4 + Phase 7 → Re-selection, URL persistence, edge cases

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 and US2 are both P1 priority and share the same component, so US2 is a quick addition after US1
- US3 (heatmap) and US4 (re-selection) can be developed in parallel after US1 is complete
- Backend service should stay under 300 lines per constitution (Principle II)
- All DuckDB connections must be read_only=True per plan architecture
