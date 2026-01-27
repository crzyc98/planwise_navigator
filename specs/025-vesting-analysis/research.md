# Research: Vesting Analysis

**Feature Branch**: `025-vesting-analysis`
**Date**: 2026-01-21

## Summary

This document captures technical research and decisions for implementing the Vesting Analysis feature. All NEEDS CLARIFICATION items have been resolved through codebase analysis.

---

## Decision 1: Data Source and Column Availability

**Question**: Does `fct_workforce_snapshot` contain all required columns for vesting analysis?

**Decision**: Yes - all required columns are available.

**Rationale**: Analysis of `dbt/models/marts/fct_workforce_snapshot.sql` confirms:
- `employee_hire_date` - Available (line 1052)
- `current_tenure` - Available (line 1055)
- `tenure_band` - Available (line 1057)
- `termination_date` - Available (line 1060)
- `termination_reason` - Available (line 1061)
- `employment_status` - Available (line 1059)
- `employer_match_amount` - Available (line 1087)
- `employer_core_amount` - Available (line 1088)
- `total_employer_contributions` - Available (line 1089)
- `annual_hours_worked` - Available (line 1090)

**Alternatives Considered**: N/A - data source was specified in requirements.

---

## Decision 2: Service Architecture Pattern

**Question**: Which existing service pattern should the VestingService follow?

**Decision**: Follow `AnalyticsService` pattern from `planalign_api/services/analytics_service.py`.

**Rationale**: The AnalyticsService pattern provides:
- `DatabasePathResolver` for workspace/scenario-aware database path resolution
- `WorkspaceStorage` for consistent storage access
- Read-only DuckDB connection pattern with explicit close
- Error handling with graceful fallbacks
- Logging via `logging.getLogger(__name__)`

**Key Code Pattern**:
```python
class VestingService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def analyze_vesting(self, workspace_id: str, scenario_id: str, ...) -> Optional[VestingAnalysisResponse]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            return None
        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            # Query and calculation logic
            pass
        finally:
            conn.close()
```

**Alternatives Considered**:
- `ComparisonService` pattern - Similar but more complex; not needed for single-scenario analysis
- Direct database access - Rejected for lack of workspace isolation

---

## Decision 3: API Endpoint Structure

**Question**: What URL pattern should vesting endpoints follow?

**Decision**: Use existing analytics endpoint pattern under workspaces.

**Rationale**: Consistent with existing analytics endpoints:
- `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan` (existing)
- `GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare` (existing)

**New Endpoints**:
- `GET /api/vesting/schedules` - List pre-defined schedules (global, no workspace)
- `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` - Run analysis

**Alternatives Considered**:
- `/api/workspaces/{workspace_id}/vesting/...` - Less consistent with analytics grouping
- `/api/analytics/vesting/...` - Loses workspace/scenario context from URL

---

## Decision 4: Vesting Calculation Logic

**Question**: How should vesting percentages be calculated for each schedule type?

**Decision**: Implement as a dictionary lookup with year-based progression.

**Rationale**: Follows common industry patterns for 401(k) vesting schedules:

```python
VESTING_SCHEDULES = {
    VestingScheduleType.IMMEDIATE: {0: 1.0},
    VestingScheduleType.CLIFF_2_YEAR: {0: 0.0, 1: 0.0, 2: 1.0},
    VestingScheduleType.CLIFF_3_YEAR: {0: 0.0, 1: 0.0, 2: 0.0, 3: 1.0},
    VestingScheduleType.CLIFF_4_YEAR: {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 1.0},
    VestingScheduleType.QACA_2_YEAR: {0: 0.0, 1: 0.0, 2: 1.0},
    VestingScheduleType.GRADED_3_YEAR: {0: 0.0, 1: 0.3333, 2: 0.6667, 3: 1.0},
    VestingScheduleType.GRADED_4_YEAR: {0: 0.0, 1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0},
    VestingScheduleType.GRADED_5_YEAR: {0: 0.0, 1: 0.20, 2: 0.40, 3: 0.60, 4: 0.80, 5: 1.0},
}

def get_vesting_percentage(schedule_type: VestingScheduleType, tenure_years: int) -> Decimal:
    schedule = VESTING_SCHEDULES[schedule_type]
    # Clamp tenure to max year in schedule
    max_year = max(schedule.keys())
    effective_tenure = min(int(tenure_years), max_year)
    return Decimal(str(schedule.get(effective_tenure, schedule[max_year])))
```

**Alternatives Considered**:
- Formula-based calculation - More flexible but harder to validate
- Database-stored schedules - Over-engineering for fixed set of schedules

---

## Decision 5: Hours-Based Vesting Credit

**Question**: How should hours-based vesting credit reduce tenure?

**Decision**: Reduce tenure by 1 year if hours threshold not met.

**Rationale**: Per IRS regulations, an employee who works fewer than 1,000 hours in a year may not receive vesting credit for that year. Implementation:

```python
def apply_hours_credit(
    tenure_years: float,
    annual_hours: float,
    require_hours: bool,
    hours_threshold: int = 1000
) -> int:
    """Return effective tenure years after hours credit adjustment."""
    if not require_hours:
        return int(tenure_years)
    if annual_hours < hours_threshold:
        return max(0, int(tenure_years) - 1)
    return int(tenure_years)
```

**Alternatives Considered**:
- Proportional hours credit - More complex; not standard for vesting
- Per-year hours tracking - Would require historical data not available

---

## Decision 6: Frontend Component Pattern

**Question**: Which existing component should VestingAnalysis.tsx follow?

**Decision**: Follow `DCPlanAnalytics.tsx` pattern.

**Rationale**: DCPlanAnalytics provides:
- Workspace/scenario selector at top
- Analysis action button
- Summary KPI cards
- Recharts visualizations (bar charts)
- Data table with sorting

**Key UI Structure**:
1. Header with navigation context
2. Configuration section (schedule selectors, hours toggle)
3. "Analyze" button
4. Results section:
   - Summary cards (total forfeitures, variance, employee count)
   - Bar chart (forfeitures by tenure band)
   - Sortable data table (employee details)

**Alternatives Considered**:
- ScenarioComparison pattern - Too focused on multi-scenario; we're comparing schedules
- Custom layout - Unnecessary; existing pattern fits well

---

## Decision 7: SQL Query for Terminated Employees

**Question**: What query retrieves terminated employees with employer contributions?

**Decision**: Use single query with simulation year filter.

**Rationale**: Query structure based on existing patterns in analytics_service.py:

```sql
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure,
    tenure_band,
    employer_match_amount,
    employer_core_amount,
    total_employer_contributions,
    annual_hours_worked
FROM fct_workforce_snapshot
WHERE simulation_year = ?
  AND UPPER(employment_status) = 'TERMINATED'
  AND total_employer_contributions > 0
ORDER BY total_employer_contributions DESC
```

**Performance Note**: With 10,000 terminated employees, this query should complete in <1 second on DuckDB due to columnar storage.

**Alternatives Considered**:
- Multiple queries by tenure band - Less efficient; can aggregate in Python
- Include active employees - Out of scope; vesting analysis is for terminated only

---

## Decision 8: Forfeiture Calculation

**Question**: How is forfeiture amount calculated?

**Decision**: Forfeiture = Total Employer Contributions × (1 - Vesting Percentage)

**Rationale**: Standard forfeiture calculation:

```python
def calculate_forfeiture(
    total_employer_contributions: Decimal,
    vesting_percentage: Decimal
) -> Decimal:
    unvested_percentage = Decimal("1.0") - vesting_percentage
    return (total_employer_contributions * unvested_percentage).quantize(Decimal("0.01"))
```

**Example**:
- Employee with $10,000 employer contributions
- 3 years tenure, 5-year graded schedule → 60% vested
- Forfeiture = $10,000 × (1 - 0.60) = $4,000

**Alternatives Considered**: N/A - this is the standard calculation method.

---

## Summary of Technical Decisions

| Area | Decision |
|------|----------|
| Data Source | `fct_workforce_snapshot` with all required columns |
| Service Pattern | Follow `AnalyticsService` with `DatabasePathResolver` |
| API Structure | `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` |
| Vesting Logic | Dictionary lookup by schedule type and tenure years |
| Hours Credit | Reduce tenure by 1 year if below threshold |
| Frontend | Follow `DCPlanAnalytics.tsx` component pattern |
| Query | Single filtered query on terminated employees |
| Forfeiture | Total × (1 - Vesting%) with $0.01 precision |
