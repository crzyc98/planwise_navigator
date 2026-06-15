# Research: DC Plan Analytics — 0% Deferral Fix and Year Filter

## Root Cause Analysis: Missing 0% Deferral Bucket

### Decision
Include non-enrolled eligible employees in the Deferral Rate Distribution query by removing the `is_enrolled_flag = true` filter from `_get_deferral_distribution` and `_get_deferral_distribution_all_years`.

### Rationale
The `_get_deferral_distribution` query currently filters `WHERE is_enrolled_flag = true AND UPPER(employment_status) = 'ACTIVE'`. This excludes non-enrolled employees entirely. Before feature 096, some enrolled new hires had `current_deferral_rate = NULL`, which the CASE statement classified as the 0% bucket — making the bucket appear populated. After 096, all voluntarily enrolled new hires receive a properly assigned deferral rate, so no enrolled employee has a NULL or zero deferral anymore. The 0% bucket disappeared.

The fix: remove `is_enrolled_flag = true`. All active employees (enrolled or not) are included. Non-enrolled employees have `current_deferral_rate = NULL` or `0`, which naturally lands in the 0% bucket. The chart now represents the full eligible active population, making it a complete deferral distribution (participation + non-participation combined).

The hard-coded `UPPER(employment_status) = 'ACTIVE'` filter stays. The deferral distribution is always an active-employee view; it does not need to respect the `active_only` toggle (which affects contribution totals and participation KPIs, not the distribution shape).

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Add a separate "non-enrolled" bar outside the existing buckets | Inconsistent with the current 11-bucket structure; more UI complexity for no additional insight |
| Keep `is_enrolled_flag = true` and add a separate KPI showing non-enrolled count | Doesn't fix the misleading impression that the distribution covers all employees |
| Change the chart title to "Enrolled Deferral Distribution" | Cosmetic only — doesn't restore the lost data signal |

---

## Year Picker: Data Strategy

### Decision
Implement the year picker **client-side**, deriving per-year data from existing API response fields (`contribution_by_year`, `deferral_distribution_by_year`). No new API endpoints or query parameters are needed.

### Rationale

The existing `DCPlanAnalytics` response already carries:
- `contribution_by_year: ContributionYearSummary[]` — per-year totals (employee contributions, match, core, participation rate, participant count)
- `deferral_distribution_by_year: DeferralDistributionYear[]` — per-year 11-bucket distribution

For a selected year, all KPI card values and the deferral distribution chart can be derived from these arrays. The comparison response (`DCPlanComparisonResponse`) also includes the full `DCPlanAnalytics` per scenario (including `contribution_by_year`), so year-filtered comparison is also fully client-side.

One field is missing: `total_eligible_count` per year (the denominator for "X of Y eligible" in the participation KPI subtext). A small backend change adds `COUNT(*) as total_eligible` to `_get_contribution_by_year`, populated into a new `total_eligible_count` field on `ContributionYearSummary`. This avoids the floating-point approximation `participant_count / (participation_rate / 100)`.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Add `year` query parameter to `/analytics/dc-plan` endpoint | Requires server-side filtering and an extra round-trip when switching years; client-side is instant |
| Add `year` query parameter to `/analytics/dc-plan/compare` | Same problem; the full comparison data is already in the response |
| Store per-year participation data in a separate API call | Over-engineering — the data is already available in `contribution_by_year` |

---

## Year Picker UX: Handling Comparison Mode Year Intersection

### Decision
In comparison mode, the year picker shows only years present in **all** selected scenarios (intersection). Years available in some but not all scenarios are omitted from the picker.

### Rationale
Comparing year N across scenarios only makes sense if all scenarios ran through year N. Including years where some scenarios have no data would show zeros for those scenarios, which is misleading (zero vs. "did not run that year" look identical).

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Show all years from any scenario, show "N/A" for missing | More complex UI; "N/A" is ambiguous (no data vs. simulation not run that year) |
| Show union of years, zero-fill missing | Actively misleading — zero contributions looks like a scenario ran and had no activity |

---

## Contribution by Year Chart: Year Highlight Approach

### Decision
When a year is selected, highlight the selected bar by giving it a distinct fill color (Fidelity green at full opacity) while rendering other year bars at reduced opacity (40%). No structural change to the chart is needed.

### Rationale
Recharts supports `Cell` components within `Bar` to set per-bar fill. This allows highlighting a single bar without changing the chart layout. Users retain full multi-year context while clearly seeing which year is selected.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Show only the selected year's bar (filter data array to one entry) | Loses year-over-year context, making trends invisible |
| Add a reference line or annotation | Harder to perceive than color change for stacked bars |

---

## Participation Summary in "All Years" Mode

### Decision
The aggregate participation KPI (shown when "All Years" is selected) continues to use the final-year snapshot from `_get_participation_summary` — unchanged from current behavior.

### Rationale
Participation rate is a point-in-time metric, not a cumulative one. "Overall participation" naturally means the most recent state of the workforce, not a sum or average across years.
