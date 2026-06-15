# Quickstart: DC Plan Analytics — 0% Deferral Fix and Year Filter

## What This Feature Does

1. **Bug fix**: Non-enrolled employees now appear in the 0% bucket of the Deferral Rate Distribution chart, making participation gaps visible.
2. **Year picker**: A new dropdown in the DC Plan analytics controls lets users filter all charts and KPI cards to a specific simulation year.

## Files to Change

### Backend (Python)

| File | Change |
|------|--------|
| `planalign_api/models/analytics.py` | Add `total_eligible_count: int` to `ContributionYearSummary`; update `DeferralRateBucket.percentage` description |
| `planalign_api/services/analytics_service.py` | Remove `is_enrolled_flag = true` from both distribution queries; add `total_eligible` to `_get_contribution_by_year` |

### Frontend (TypeScript/React)

| File | Change |
|------|--------|
| `planalign_studio/services/api.ts` | Add `total_eligible_count: number` to `ContributionYearSummary` interface |
| `planalign_studio/components/DCPlanAnalytics.tsx` | Add year picker state, controls UI, and year-filtered derived data |

### Tests

| File | Change |
|------|--------|
| `tests/test_dc_plan_analytics.py` | Add/update tests for 0% bucket fix and per-year eligible count |

---

## Implementation Order

```
1. Backend models (analytics.py)           — type-safe foundation
2. Backend service (analytics_service.py)  — query fixes
3. Backend tests (test_dc_plan_analytics.py) — verify fix
4. TypeScript types (api.ts)               — match updated response
5. Frontend component (DCPlanAnalytics.tsx) — year picker + derived data
```

---

## Step-by-Step: Backend Bug Fix

### 1. `planalign_api/models/analytics.py`

In `ContributionYearSummary`, add after `participant_count`:
```python
total_eligible_count: int = Field(
    default=0, description="Total eligible employees (enrolled + non-enrolled) for this year"
)
```

Update `DeferralRateBucket.percentage` description:
```python
percentage: float = Field(description="Percentage of eligible active employees")
```

### 2. `planalign_api/services/analytics_service.py`

**Fix `_get_deferral_distribution`** — in the `bucketed` CTE, change WHERE:
```sql
-- REMOVE:
AND is_enrolled_flag = true

-- Keep:
WHERE simulation_year = final_year.max_year
  AND UPPER(employment_status) = 'ACTIVE'
```

**Fix `_get_deferral_distribution_all_years`** — same removal in the `bucketed` CTE:
```sql
-- REMOVE:
AND is_enrolled_flag = true

-- Keep:
WHERE UPPER(employment_status) = 'ACTIVE'
```

**Fix `_get_contribution_by_year`** — add to SELECT:
```sql
COUNT(*) as total_eligible,
```

And in the Python result construction:
```python
total_eligible_count=int(row["total_eligible"]),
```

---

## Step-by-Step: Frontend Year Picker

### 3. `planalign_studio/services/api.ts`

In `ContributionYearSummary` interface, add:
```typescript
total_eligible_count: number;
```

### 4. `planalign_studio/components/DCPlanAnalytics.tsx`

**Add state**:
```typescript
const [selectedYear, setSelectedYear] = useState<number | null>(null);
```

**Reset on scenario change** (add to the existing workspace effect):
```typescript
setSelectedYear(null);
```

**Derive available years** (useMemo):
```typescript
const availableYears = useMemo(() => {
  if (analytics) return analytics.contribution_by_year.map(y => y.year);
  if (comparisonData) {
    const sets = comparisonData.analytics.map(
      a => new Set(a.contribution_by_year.map(y => y.year))
    );
    return [...sets[0]].filter(y => sets.every(s => s.has(y))).sort((a, b) => a - b);
  }
  return [];
}, [analytics, comparisonData]);
```

**Derive active year data** (useMemo):
```typescript
const activeYearData = useMemo(() => {
  if (!analytics || selectedYear === null) return null;
  return analytics.contribution_by_year.find(y => y.year === selectedYear) ?? null;
}, [analytics, selectedYear]);

const activeDeferralDistribution = useMemo(() => {
  if (!analytics) return [];
  if (selectedYear !== null) {
    return analytics.deferral_distribution_by_year.find(
      y => y.year === selectedYear
    )?.distribution ?? [];
  }
  return analytics.deferral_rate_distribution;
}, [analytics, selectedYear]);
```

**Add year picker to controls** (after the scenario selector):
```tsx
{(analytics || comparisonData) && availableYears.length > 1 && (
  <select
    value={selectedYear ?? ''}
    onChange={(e) => setSelectedYear(e.target.value ? Number(e.target.value) : null)}
    className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
  >
    <option value="">All Years</option>
    {availableYears.map(year => (
      <option key={year} value={year}>{year}</option>
    ))}
  </select>
)}
```

**Update KPI cards** to use `activeYearData` when available:
- `total_employee_contributions` → `activeYearData?.total_employee_contributions ?? analytics.total_employee_contributions`
- `total_employer_match` → `activeYearData?.total_employer_match ?? analytics.total_employer_match`
- `total_employer_core` → `activeYearData?.total_employer_core ?? analytics.total_employer_core`
- `participation_rate` → `activeYearData?.participation_rate ?? analytics.participation_rate`
- `total_enrolled` subtext → `activeYearData ? activeYearData.participant_count : analytics.total_enrolled`
- `total_eligible` subtext → `activeYearData ? activeYearData.total_eligible_count : analytics.total_eligible`

**Update Deferral Distribution chart** data source:
```typescript
// Replace deferralDistributionData computation:
const deferralDistributionData = activeDeferralDistribution.map(bucket => ({
  bucket: bucket.bucket,
  count: bucket.count,
  percentage: bucket.percentage,
}));
```

**Update Contributions by Year chart** to highlight selected year:
```tsx
<Bar
  dataKey="Employee"
  stackId="a"
  name="Employee"
  radius={[0, 0, 4, 4]}
>
  {contributionChartData.map((entry) => (
    <Cell
      key={entry.year}
      fill={CONTRIBUTION_COLORS.employee}
      opacity={selectedYear === null || entry.year === selectedYear ? 1 : 0.3}
    />
  ))}
</Bar>
// Repeat for Match and Core bars
```

**Update comparison table** to use year-filtered data:
```typescript
// Comparison table rows compute from contribution_by_year when year is selected:
const getComparisonMetric = (a: DCPlanAnalytics, key: keyof ContributionYearSummary) => {
  if (selectedYear !== null) {
    const yearData = a.contribution_by_year.find(y => y.year === selectedYear);
    return yearData?.[key] ?? 0;
  }
  return a[key as keyof DCPlanAnalytics] as number;
};
```

---

## Verifying the Bug Fix

After implementation, run a simulation and verify:

```
Total active employees in final year: N
Enrolled employees: M (participation rate ~65%)
Non-enrolled: N - M

Expected 0% bucket count = N - M
Sum of all buckets = N (= total active eligible)
```

The KPI participation card "M of N eligible" should match the deferral distribution total.
