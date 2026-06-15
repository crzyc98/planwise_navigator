# Data Model: DC Plan Analytics — 0% Deferral Fix and Year Filter

## Changed Entities

### ContributionYearSummary (extended)

**File**: `planalign_api/models/analytics.py`

Adds one new field to supply the per-year eligible-employee count needed by the year-filtered participation KPI card.

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| year | int | existing | Simulation year |
| total_employee_contributions | float | existing | Total employee deferrals for the year |
| total_employer_match | float | existing | Total employer match for the year |
| total_employer_core | float | existing | Total employer core for the year |
| total_all_contributions | float | existing | Sum of all contributions for the year |
| participant_count | int | existing | Number of enrolled participants |
| **total_eligible_count** | **int** | **new** | **Total eligible employees (enrolled + non-enrolled) for the year** |
| participation_rate | float | existing | Enrolled / eligible × 100 |
| average_deferral_rate | float | existing | Mean deferral rate among enrolled |
| total_employer_cost | float | existing | Match + core |
| total_compensation | float | existing | Sum of prorated annual compensation |
| employer_cost_rate | float | existing | Employer cost / compensation × 100 |
| employee_contribution_rate | float | existing | Employee deferrals / compensation × 100 |
| match_contribution_rate | float | existing | Match / compensation × 100 |
| core_contribution_rate | float | existing | Core / compensation × 100 |
| total_contribution_rate | float | existing | All contributions / compensation × 100 |

### DeferralRateBucket (description change only)

**File**: `planalign_api/models/analytics.py`

| Field | Type | Status | Description |
|-------|------|--------|-------------|
| bucket | str | existing | Deferral rate bucket label |
| count | int | existing | Number of employees in this bucket |
| percentage | float | changed | ~~Percentage of enrolled employees~~ → **Percentage of eligible active employees** |

---

## Query Changes

### `_get_deferral_distribution` (analytics_service.py)

**Before** (filtering enrolled employees only):
```sql
WHERE simulation_year = final_year.max_year
  AND UPPER(employment_status) = 'ACTIVE'
  AND is_enrolled_flag = true
```

**After** (all active eligible employees):
```sql
WHERE simulation_year = final_year.max_year
  AND UPPER(employment_status) = 'ACTIVE'
```

The CASE expression already handles `current_deferral_rate IS NULL OR current_deferral_rate = 0` → `'0%'`, so non-enrolled employees (with NULL deferral rate) correctly land in the 0% bucket.

### `_get_deferral_distribution_all_years` (analytics_service.py)

Same change: remove `AND is_enrolled_flag = true` from the WHERE clause.

### `_get_contribution_by_year` (analytics_service.py)

Add `COUNT(*) as total_eligible` to the SELECT clause (alongside existing `COUNT(CASE WHEN is_enrolled_flag THEN 1 END) as participant_count`). The `status_filter` for `active_only` applies here so that `total_eligible_count` respects the same employment status filter as other metrics.

---

## TypeScript Interface Changes

### `ContributionYearSummary` (planalign_studio/services/api.ts)

Add:
```typescript
total_eligible_count: number;  // Total eligible employees for this year
```

---

## Frontend State Shape

The `DCPlanAnalytics.tsx` component adds:

```typescript
// Year selection state
const [selectedYear, setSelectedYear] = useState<number | null>(null); // null = All Years

// Derived: available years from loaded data
const availableYears: number[] = useMemo(() => {
  if (analytics) {
    return analytics.contribution_by_year.map(y => y.year);
  }
  if (comparisonData) {
    // Intersection of years across all selected scenarios
    const yearSets = comparisonData.analytics.map(
      a => new Set(a.contribution_by_year.map(y => y.year))
    );
    return [...yearSets[0]].filter(y => yearSets.every(s => s.has(y))).sort();
  }
  return [];
}, [analytics, comparisonData]);

// Derived: active year data (single scenario view)
const activeYearData: ContributionYearSummary | null = useMemo(() => {
  if (!analytics || selectedYear === null) return null;
  return analytics.contribution_by_year.find(y => y.year === selectedYear) ?? null;
}, [analytics, selectedYear]);

// Derived: active deferral distribution
const activeDeferralDistribution: DeferralRateBucket[] = useMemo(() => {
  if (!analytics) return [];
  if (selectedYear !== null) {
    const yearDist = analytics.deferral_distribution_by_year.find(
      y => y.year === selectedYear
    );
    return yearDist?.distribution ?? [];
  }
  return analytics.deferral_rate_distribution; // final-year aggregate (default)
}, [analytics, selectedYear]);
```

No persistence needed — year selection is transient UI state that resets with scenario changes.
