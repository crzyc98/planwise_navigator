# Tasks: Trended Contribution Percentage Rates

**Input**: Design documents from `/specs/066-dc-contribution-rates/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new project structure needed. This feature extends existing files only.

- [x] T001 Verify development environment: run `planalign studio --verbose` and confirm API starts on port 8000 and frontend on port 5173

**Checkpoint**: Dev environment ready

---

## Phase 2: Foundational (Backend Model Extension)

**Purpose**: Extend the Pydantic model with new fields — required before any service or frontend work

- [x] T002 Add four new float fields to `ContributionYearSummary` in `planalign_api/models/analytics.py`: `employee_contribution_rate: float = 0.0`, `match_contribution_rate: float = 0.0`, `core_contribution_rate: float = 0.0`, `total_contribution_rate: float = 0.0`
- [x] T003 Add same four float fields to `DCPlanAnalytics` model in `planalign_api/models/analytics.py` for aggregate-level rates (after existing `employer_cost_rate` field)

**Checkpoint**: Pydantic models extended. API will return 0.0 defaults for new fields until service logic is added.

---

## Phase 3: User Story 1 & 2 - Backend Rate Computation + Trend Chart (Priority: P1) MVP

**Goal**: Compute contribution rates in the analytics service and display them as a trended line chart on the DC Plan comparison page.

**Independent Test**: Run a multi-year simulation, call the analytics API, verify 4 new rate fields are populated. Open DC Plan comparison page and verify the "Contribution Rate Trends" chart renders with 4 series.

### Implementation

- [x] T004 [US1] Compute per-year contribution rates in `_get_contribution_by_year()` in `planalign_api/services/analytics_service.py`: after the existing `employer_cost_rate` calculation, add `employee_contribution_rate = round(total_employee / total_compensation * 100, 2) if total_compensation > 0 else 0.0`, and similarly for `match_contribution_rate` (using `total_match`), `core_contribution_rate` (using `total_core`), and `total_contribution_rate` (sum of the three). Pass all four to `ContributionYearSummary` constructor.
- [x] T005 [US1] Compute aggregate contribution rates in `_compute_grand_totals()` in `planalign_api/services/analytics_service.py`: sum `total_employee_contributions`, `total_employer_match`, `total_employer_core` across all years, divide each by summed `total_compensation`, multiply by 100. Add all four rate keys to the returned dict.
- [x] T006 [US1] Wire aggregate rates into `DCPlanAnalytics` construction in `planalign_api/services/analytics_service.py`: pass the four new grand total rate values when constructing the `DCPlanAnalytics` response object.
- [x] T007 [P] [US1] Add four new fields to `ContributionYearSummary` TypeScript interface in `planalign_studio/services/api.ts`: `employee_contribution_rate: number`, `match_contribution_rate: number`, `core_contribution_rate: number`, `total_contribution_rate: number`
- [x] T008 [US1] Add "Contribution Rate Trends" line chart to `planalign_studio/components/DCPlanComparisonSection.tsx`: create a new chart section (after Employer Cost Rate Trends) with a Recharts `LineChart` rendering 4 series — Employee (%), Match (%), Core (%), Total (%). Build chart data by iterating `contribution_by_year` for each scenario. Use colors: Employee `#0088FE`, Match `#00C49F`, Core `#FFBB28`, Total `#FF8042`. Include tooltips with `tooltipStyle`, percentage formatting, and legend. Follow the existing `ResponsiveContainer` + `LineChart` pattern.

**Checkpoint**: API returns populated rate fields. DC Plan page shows the new Contribution Rate Trends chart with 4 series across all simulation years.

---

## Phase 4: User Story 3 - Summary Table Integration (Priority: P2)

**Goal**: Add contribution rate percentages to the summary comparison table for at-a-glance comparison.

**Independent Test**: Open DC Plan comparison page and verify the summary table includes rows for Employee Contribution Rate, Match Contribution Rate, Core Contribution Rate, and Total Contribution Rate with correct values and delta formatting.

### Implementation

- [x] T009 [US3] Add four new `SummaryMetricRow` entries to the summary comparison table in `planalign_studio/components/DCPlanComparisonSection.tsx`: add rows for "Employee Contribution Rate", "Employer Match Rate", "Employer Core Rate", and "Total Contribution Rate" with `unit: 'percent'` and `favorableDirection: 'higher'` (or as appropriate). Source values from the last year's `contribution_by_year` entry for each scenario.

**Checkpoint**: Summary table shows all four contribution rate metrics with baseline values and scenario deltas.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling and verification

- [x] T010 Verify zero-compensation edge case: run a simulation scenario where all employees terminate in a year, confirm API returns 0.0% for all rates and the chart renders without errors
- [ ] T011 Verify single-year simulation: run a 1-year simulation and confirm the chart renders with one data point per series
- [ ] T012 Run quickstart.md validation: follow the verification steps in `specs/066-dc-contribution-rates/quickstart.md` end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — verify environment
- **Foundational (Phase 2)**: Depends on Phase 1 — adds Pydantic model fields
- **User Story 1 & 2 (Phase 3)**: Depends on Phase 2 — backend computation + frontend chart
- **User Story 3 (Phase 4)**: Depends on Phase 3 (needs rate data in API response) — summary table
- **Polish (Phase 5)**: Depends on Phase 3 minimum, Phase 4 preferred

### Within Phase 3

- T004 → T005 → T006 (sequential: per-year rates → grand totals → wiring)
- T007 can run in parallel with T004-T006 (different file: TypeScript vs Python)
- T008 depends on T004-T007 (needs both API data and TypeScript types)

### Parallel Opportunities

- T007 (TypeScript interface) can run in parallel with T004-T006 (Python service)
- T002 and T003 can be done together (same file, adjacent code)

---

## Parallel Example: Phase 3

```bash
# These can run in parallel (different files):
Task T004-T006: "Backend rate computation in planalign_api/services/analytics_service.py"
Task T007: "TypeScript interface update in planalign_studio/services/api.ts"

# Then sequentially:
Task T008: "Frontend chart in planalign_studio/components/DCPlanComparisonSection.tsx"
```

---

## Implementation Strategy

### MVP First (Phase 3 Only)

1. Complete Phase 1: Verify environment
2. Complete Phase 2: Extend Pydantic models (T002-T003)
3. Complete Phase 3: Backend rates + frontend chart (T004-T008)
4. **STOP and VALIDATE**: Verify chart renders with correct rates
5. Deploy/demo — users can see contribution rate trends

### Incremental Delivery

1. Phase 1-2 → Models ready (API returns 0.0 defaults)
2. Phase 3 → Trend chart live (MVP!)
3. Phase 4 → Summary table enhanced
4. Phase 5 → Edge cases verified, quickstart validated

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 and US2 are merged into Phase 3 because US2 (backend API) is a prerequisite for US1 (frontend chart) — they form one deliverable unit
- Total task count: 12
- Estimated scope: Small (~80 lines across 3 files)
