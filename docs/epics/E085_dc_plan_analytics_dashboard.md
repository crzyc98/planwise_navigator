# E085: DC Plan Contribution Analytics Dashboard

**Status**: PLANNED
**Priority**: Medium
**Approach**: Incremental - API first, then frontend
**Dependencies**: E084 (DC Plan Configuration), E039 (Employer Contributions)

---

## Executive Summary

Create a dedicated DC Plan Contribution Analytics Dashboard in PlanAlign Studio that surfaces the retirement plan contribution data already modeled in `fct_workforce_snapshot`. This enables retirement plan analysts to visualize contribution patterns, employer costs, and participation metrics without querying DuckDB directly.

**Problem**: The simulation engine models rich DC plan data (employee deferrals, employer match, employer core contributions, participation rates, escalation tracking), but this data is not exposed in the Studio analytics UI.

**Solution**: Add a new "DC Plan" tab to PlanAlign Studio analytics with KPI cards, contribution charts, deferral rate distribution, and scenario comparison.

---

## Part 1: Data Already Available

No new dbt models required. All data exists in `fct_workforce_snapshot`:

### Employee Contribution Fields
| Field | Description |
|-------|-------------|
| `prorated_annual_contributions` | Total employee deferrals |
| `current_deferral_rate` | Current deferral rate (%) |
| `original_deferral_rate` | Starting deferral rate before escalations |
| `effective_annual_deferral_rate` | Rate applied to contributions |
| `irs_limit_reached` | Boolean: hit IRS 402(g) limit |

### Employer Contribution Fields
| Field | Description |
|-------|-------------|
| `employer_match_amount` | Employer match contribution |
| `employer_core_amount` | Employer core (non-elective) contribution |
| `total_employer_contributions` | Match + Core combined |

### Participation Fields
| Field | Description |
|-------|-------------|
| `is_enrolled_flag` | Enrolled in plan |
| `participation_status` | participating / not_participating |
| `participation_status_detail` | auto enrollment, voluntary, opted out, etc. |

### Escalation Fields
| Field | Description |
|-------|-------------|
| `total_deferral_escalations` | Number of escalations received |
| `has_deferral_escalations` | Boolean: any escalations |
| `total_escalation_amount` | Total rate increase from escalations |

---

## Part 2: Implementation Plan

### Story S085-01: API Endpoint for DC Plan Analytics

**Files**:
- `planalign_api/routers/analytics.py` (new)
- `planalign_api/models/analytics.py` (new)
- `planalign_api/routers/__init__.py` (modify)

**Endpoints**:
```
GET /api/scenarios/{scenario_id}/analytics/dc-plan
GET /api/analytics/dc-plan/compare?scenarios=id1,id2,id3
```

**Response Model**:
```python
class ContributionYearSummary(BaseModel):
    year: int
    total_employee_contributions: float
    total_employer_match: float
    total_employer_core: float
    total_all_contributions: float
    participant_count: int

class DeferralRateBucket(BaseModel):
    bucket: str  # "0%", "1%", "2%", ..., "10%+"
    count: int
    percentage: float

class DCPlanAnalytics(BaseModel):
    scenario_id: str
    scenario_name: str

    # Participation
    total_eligible: int
    total_enrolled: int
    participation_rate: float
    participation_by_method: Dict[str, int]  # {auto: X, voluntary: Y, census: Z}

    # Contributions by year
    contribution_by_year: List[ContributionYearSummary]

    # Deferral rate distribution (11 buckets: 0%, 1%, 2%...9%, 10%+)
    deferral_rate_distribution: List[DeferralRateBucket]

    # Escalation metrics
    employees_with_escalations: int
    avg_escalation_count: float
    total_escalation_amount: float

    # IRS limit stats
    employees_at_irs_limit: int
    total_amount_capped: float
```

**Estimated Effort**: 1-2 days

---

### Story S085-02: Analytics Query Service

**File**: `planalign_api/services/analytics_service.py` (new)

**Methods**:
```python
class AnalyticsService:
    def get_dc_plan_analytics(self, workspace_id: str, scenario_id: str) -> DCPlanAnalytics:
        """Aggregate DC plan analytics for a single scenario."""

    def get_dc_plan_comparison(self, scenario_ids: List[str]) -> List[DCPlanAnalytics]:
        """Get DC plan analytics for multiple scenarios for comparison."""
```

**DuckDB Queries**:

1. **Participation Summary**:
```sql
SELECT
    COUNT(*) as total_eligible,
    SUM(CASE WHEN is_enrolled_flag THEN 1 ELSE 0 END) as total_enrolled,
    SUM(CASE WHEN participation_status_detail LIKE '%auto%' THEN 1 ELSE 0 END) as auto_enrolled,
    SUM(CASE WHEN participation_status_detail LIKE '%voluntary%' THEN 1 ELSE 0 END) as voluntary_enrolled,
    SUM(CASE WHEN participation_status_detail LIKE '%census%' THEN 1 ELSE 0 END) as census_enrolled
FROM fct_workforce_snapshot
WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
  AND employment_status = 'active'
```

2. **Contribution Totals by Year**:
```sql
SELECT
    simulation_year as year,
    SUM(prorated_annual_contributions) as total_employee,
    SUM(employer_match_amount) as total_match,
    SUM(employer_core_amount) as total_core,
    SUM(prorated_annual_contributions + employer_match_amount + employer_core_amount) as total_all,
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) as participant_count
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
GROUP BY simulation_year
ORDER BY simulation_year
```

3. **Deferral Rate Distribution** (11 buckets: 0%, 1%, 2%...9%, 10%+):
```sql
SELECT
    CASE
        WHEN current_deferral_rate = 0 THEN '0%'
        WHEN current_deferral_rate < 0.02 THEN '1%'
        WHEN current_deferral_rate < 0.03 THEN '2%'
        WHEN current_deferral_rate < 0.04 THEN '3%'
        WHEN current_deferral_rate < 0.05 THEN '4%'
        WHEN current_deferral_rate < 0.06 THEN '5%'
        WHEN current_deferral_rate < 0.07 THEN '6%'
        WHEN current_deferral_rate < 0.08 THEN '7%'
        WHEN current_deferral_rate < 0.09 THEN '8%'
        WHEN current_deferral_rate < 0.10 THEN '9%'
        ELSE '10%+'
    END as bucket,
    COUNT(*) as count
FROM fct_workforce_snapshot
WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
  AND employment_status = 'active'
  AND is_enrolled_flag = true
GROUP BY bucket
ORDER BY bucket
```

**Estimated Effort**: 1 day

---

### Story S085-03: DC Plan Analytics Page (Frontend)

**File**: `planalign_studio/components/DCPlanAnalytics.tsx` (new)

**Components**:

1. **Scenario Selector** (multi-select for comparison, max 3)
2. **KPI Cards Row**:
   - Total Employee Deferrals (formatted as currency)
   - Total Employer Match (formatted as currency)
   - Total Employer Core (formatted as currency)
   - Participation Rate (percentage)

3. **Contribution Stacked Bar Chart**:
   - X-axis: Simulation years
   - Stacks: Employee, Match, Core
   - In comparison mode: Grouped by scenario

4. **Deferral Rate Distribution Chart**:
   - Horizontal bar chart
   - 11 buckets (0%, 1%...9%, 10%+)
   - Show employee count per bucket

5. **Participation Breakdown Pie Chart**:
   - Auto-enrolled
   - Voluntary-enrolled
   - Census (baseline)

6. **Comparison Table** (when multiple scenarios selected):
   - Side-by-side metrics
   - Highlight differences

**Libraries**: Recharts (already used in AnalyticsDashboard)

**Estimated Effort**: 2-3 days

---

### Story S085-04: Navigation Integration

**Files**:
- `planalign_studio/App.tsx` (modify)
- `planalign_studio/components/Layout.tsx` (modify)
- `planalign_studio/services/api.ts` (modify)

**Changes**:
1. Add route: `/analytics/dc-plan`
2. Add nav item under Analytics dropdown: "DC Plan"
3. Add API client function: `getDCPlanAnalytics(scenarioId)`
4. Add comparison function: `compareDCPlanAnalytics(scenarioIds)`

**Estimated Effort**: 0.5 days

---

## Part 3: UI Wireframe

```
┌─────────────────────────────────────────────────────────────────────┐
│  DC Plan Analytics                           [Scenario Selector ▼]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Employee    │ │ Employer    │ │ Employer    │ │ Participation│   │
│  │ Deferrals   │ │ Match       │ │ Core        │ │ Rate         │   │
│  │ $4.2M      │ │ $1.8M       │ │ $890K       │ │ 78.5%        │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│                                                                     │
│  ┌────────────────────────────────┐ ┌────────────────────────────┐ │
│  │   Contributions by Year        │ │  Deferral Rate Distribution │ │
│  │   [Stacked Bar Chart]          │ │  [Horizontal Bar Chart]     │ │
│  │                                │ │                              │ │
│  │   █ Employee  █ Match  █ Core  │ │  0%  ████░░░░░░  12%        │ │
│  │                                │ │  1%  █░░░░░░░░░   3%        │ │
│  │   2025   2026   2027           │ │  2%  ██░░░░░░░░   5%        │ │
│  │   ▓▓▓▓   ▓▓▓▓   ▓▓▓▓          │ │  3%  ████████░░  18%        │ │
│  │   ▓▓▓▓   ▓▓▓▓   ▓▓▓▓          │ │  ...                        │ │
│  │   ████   ████   ████          │ │  10%+ ███████░░░  15%        │ │
│  └────────────────────────────────┘ └────────────────────────────┘ │
│                                                                     │
│  ┌────────────────────────────────┐ ┌────────────────────────────┐ │
│  │   Participation Breakdown      │ │  Escalation Summary        │ │
│  │   [Pie Chart]                  │ │                            │ │
│  │                                │ │  Employees w/ Escalations  │ │
│  │      Auto (45%)                │ │  3,240 (42%)               │ │
│  │      Voluntary (33%)           │ │                            │ │
│  │      Census (22%)              │ │  Avg Escalations: 2.3      │ │
│  │                                │ │  Total Rate Increase: 2.8% │ │
│  └────────────────────────────────┘ └────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 4: Acceptance Criteria

1. New "DC Plan" tab visible in Studio analytics navigation
2. KPI cards show: Total Employee Deferrals, Total Employer Match, Total Employer Core, Participation Rate
3. Contribution stacked bar chart shows Employee vs Match vs Core by year
4. Deferral rate distribution shows 11 buckets (0%, 1%, 2%...9%, 10%+)
5. Participation pie chart shows breakdown by enrollment method (auto, voluntary, census)
6. **Scenario comparison**: Can select 2-3 scenarios for side-by-side metrics comparison
7. Comparison view shows grouped bar charts and comparison table
8. Export to Excel includes DC plan analytics data

---

## Part 5: What This Epic Does NOT Include

- Vesting schedules (not modeled - see E084 deferred items)
- Forfeitures (not modeled - see E084 deferred items)
- Account balances (not modeled)
- Investment elections beyond target date fund allocation
- Distribution modeling
- What-if sensitivity analysis (separate future epic)
- Monte Carlo simulation / confidence intervals (separate future epic)

---

## Part 6: Files to Modify/Create

| File | Action | Purpose |
|------|--------|---------|
| `planalign_api/routers/__init__.py` | Modify | Register analytics router |
| `planalign_api/routers/analytics.py` | Create | DC plan analytics endpoints |
| `planalign_api/models/analytics.py` | Create | Pydantic response models |
| `planalign_api/services/analytics_service.py` | Create | DuckDB query logic |
| `planalign_studio/components/DCPlanAnalytics.tsx` | Create | React analytics page |
| `planalign_studio/services/api.ts` | Modify | Add API client functions |
| `planalign_studio/App.tsx` | Modify | Add route |
| `planalign_studio/components/Layout.tsx` | Modify | Add nav item |

---

## Part 7: Estimated Scope

| Component | Lines | Effort |
|-----------|-------|--------|
| Backend (API + Service + Models) | ~300 | 2-3 days |
| Frontend (Page + Components) | ~600 | 2-3 days |
| **Total** | ~900 | **4-6 days** |

**Complexity**: Medium (follows existing patterns from AnalyticsDashboard and ScenarioComparison)

---

## Part 8: Implementation Order

```
S085-01: API Endpoint (Day 1-2)
├── Create analytics.py router
├── Create analytics.py models
└── Register router in __init__.py

S085-02: Query Service (Day 2)
├── Create analytics_service.py
└── Implement DuckDB queries

S085-03: Frontend Page (Day 3-4)
├── Create DCPlanAnalytics.tsx
├── Implement KPI cards
├── Implement contribution charts
├── Implement deferral distribution
└── Implement comparison mode

S085-04: Navigation Integration (Day 5)
├── Add route to App.tsx
├── Add nav item to Layout.tsx
└── Add API client to api.ts
```

---

## Part 9: Testing Strategy

### API Tests
- Test single scenario endpoint returns valid data
- Test comparison endpoint with 2-3 scenarios
- Test error handling for non-existent scenarios
- Test empty database handling

### Frontend Tests
- Component renders without errors
- KPI cards display formatted values
- Charts render with sample data
- Scenario selector works correctly
- Comparison mode toggles views

### Integration Tests
- End-to-end test: run simulation → view analytics
- Verify data consistency between workforce snapshot and analytics

---

## Part 10: Future Enhancements (Out of Scope)

1. **Sensitivity Analysis**: What-if sliders for match rate changes
2. **Cost Projections**: Multi-year employer cost forecasting
3. **Cohort Analysis**: Breakdown by age band, tenure band, job level
4. **Benchmark Comparison**: Compare against industry benchmarks
5. **Export Enhancements**: PDF report generation
