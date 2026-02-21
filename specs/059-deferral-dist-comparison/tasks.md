# Tasks: Deferral Rate Distribution Comparison

**Input**: Design documents from `/specs/059-deferral-dist-comparison/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not requested in the feature specification. No test tasks included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: User Story 1 - Compare Deferral Distributions Across Scenarios (Priority: P1) MVP

**Goal**: Display a grouped bar chart comparing deferral rate distributions (0%-10%+) across scenarios in the DC Plan comparison section, using existing final-year distribution data already present in the API response.

**Independent Test**: Run two scenarios with different plan designs, navigate to scenario comparison page, expand DC Plan section, and verify grouped bar chart shows both distributions with correct bucket counts, percentages, and scenario colors.

**Note**: No setup or foundational phase needed — this feature extends existing files only. The `DCPlanComparisonResponse` already includes `deferral_rate_distribution: List[DeferralRateBucket]` per scenario in `analytics[]`. No backend changes required for US1.

### Implementation for User Story 1

- [x] T001 [US1] Add grouped bar chart for deferral distribution comparison in `planalign_studio/components/DCPlanComparisonSection.tsx`. Extract `deferral_rate_distribution` from each scenario in `comparisonData.analytics[]`. Transform to Recharts grouped bar format: each data point = one bucket (0%-10%+), with dynamic keys per scenario name. Render `<BarChart>` with: X-axis = bucket labels, Y-axis = percentage of enrolled (formatted with `%`), one `<Bar>` per scenario using `scenarioColors` prop, `<Tooltip>` showing bucket label, scenario name, employee count, and percentage. Place chart after existing "Average Deferral Rate Trends" chart. Use existing `tooltipStyle`, `ResponsiveContainer`, and `CartesianGrid` patterns from the same file. Include section heading "Deferral Rate Distribution" with descriptive subtitle.

**Checkpoint**: Grouped bar chart visible on comparison page with final-year distribution data. Functional MVP complete.

---

## Phase 2: User Story 2 - View Distribution for a Specific Simulation Year (Priority: P2)

**Goal**: Add per-year distribution data to the API response and a year selector dropdown so actuaries can view distributions for any simulation year, not just the final year.

**Independent Test**: Run a multi-year simulation (2025-2027), navigate to comparison page, verify year selector defaults to final year, select a different year and verify chart updates with that year's distribution.

### Implementation for User Story 2

- [x] T002 [P] [US2] Add `DeferralDistributionYear` Pydantic model in `planalign_api/models/analytics.py`. Fields: `year: int`, `distribution: List[DeferralRateBucket]`. Add `deferral_distribution_by_year: List[DeferralDistributionYear] = Field(default_factory=list, description="Per-year deferral rate distributions for all simulation years")` to `DCPlanAnalytics`. Follow the existing `ContributionYearSummary` / `contribution_by_year` pattern.

- [x] T003 [P] [US2] Add `DeferralDistributionYear` TypeScript interface in `planalign_studio/services/api.ts`. Fields: `year: number`, `distribution: DeferralRateBucket[]`. Add `deferral_distribution_by_year: DeferralDistributionYear[]` to the `DCPlanAnalytics` interface. Place near existing `DeferralRateBucket` interface.

- [x] T004 [US2] Add `_get_deferral_distribution_all_years()` method in `planalign_api/services/analytics_service.py`. Reuse the bucketing CASE expression from existing `_get_deferral_distribution()` but replace the `final_year` CTE with `GROUP BY simulation_year`. For each year: compute bucket counts and percentages (count/total_enrolled_in_year*100). Ensure all 11 buckets are present per year (fill missing buckets with count=0, percentage=0.0). Return `List[DeferralDistributionYear]` ordered by year. Call this new method from `get_dc_plan_analytics()` and assign result to `deferral_distribution_by_year` field. Keep existing `_get_deferral_distribution()` call unchanged for backward compatibility.

- [x] T005 [US2] Add year selector dropdown and wire to chart data in `planalign_studio/components/DCPlanComparisonSection.tsx`. Extract common years across all scenarios from `deferral_distribution_by_year` (intersection of year sets). Add `selectedYear` state defaulting to final (max) year. Render `<select>` dropdown above the chart with year options. On year change: look up distribution from `deferral_distribution_by_year` for the selected year per scenario, rebuild chart data. If `deferral_distribution_by_year` is empty or missing, fall back to existing `deferral_rate_distribution` (final year only, hide year selector).

**Checkpoint**: Year selector visible. Changing year updates chart with correct distribution. Backward compatible when per-year data is absent.

---

## Phase 3: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling that improves robustness across both user stories.

- [x] T006 Handle edge cases in `planalign_studio/components/DCPlanComparisonSection.tsx`. (1) Zero enrollment: if a scenario has all-zero distribution for selected year, show a subtle note below the chart. (2) Mismatched year ranges: year selector shows only years common to ALL scenarios (set intersection); if no common years, show informational message. (3) Single-year simulation: render year selector with single option (disabled or hidden). (4) Ensure bucket ordering is always 0%, 1%, 2%...9%, 10%+ regardless of API response order.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (US1)**: No dependencies — can start immediately. Uses existing API response data.
- **Phase 2 (US2)**: Depends on Phase 1 completion (T005 modifies chart built in T001). Backend tasks T002-T004 can start in parallel with Phase 1.
- **Phase 3 (Polish)**: Depends on Phase 2 completion (T006 handles edge cases for year selector from T005).

### User Story Dependencies

- **User Story 1 (P1)**: Independent — no backend changes, uses existing `deferral_rate_distribution` field.
- **User Story 2 (P2)**: Backend tasks (T002, T003, T004) are independent of US1. Frontend task (T005) depends on T001 (extends the chart built in US1) and T004 (backend must provide data).

### Within Each User Story

- US1: Single task (T001) — atomic frontend change
- US2: Models (T002, T003) in parallel → Service (T004) → Frontend (T005)

### Parallel Opportunities

- T002 and T003 can run in parallel (Python model vs TypeScript interface — different files)
- T002/T003 can also run in parallel with T001 (different files, no dependency)

---

## Parallel Example: User Story 2

```bash
# Launch backend model and frontend type in parallel:
Task: "Add DeferralDistributionYear Pydantic model in planalign_api/models/analytics.py"
Task: "Add DeferralDistributionYear TypeScript interface in planalign_studio/services/api.ts"

# Then sequentially:
Task: "Add _get_deferral_distribution_all_years() in planalign_api/services/analytics_service.py"
Task: "Add year selector dropdown in planalign_studio/components/DCPlanComparisonSection.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001: Grouped bar chart using existing final-year data
2. **STOP and VALIDATE**: Verify chart renders with correct colors, tooltips, and data
3. Deploy/demo if ready — actuaries get immediate value

### Incremental Delivery

1. T001 → MVP with final-year comparison chart
2. T002 + T003 (parallel) → T004 → T005 → Full year selection capability
3. T006 → Edge case robustness

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Total: 6 tasks (1 for US1, 4 for US2, 1 for polish)
- No new files created — all changes extend existing files
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
