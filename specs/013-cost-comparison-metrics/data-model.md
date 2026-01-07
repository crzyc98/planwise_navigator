# Data Model: Employer Cost Ratio Metrics

**Date**: 2026-01-07
**Feature**: 013-cost-comparison-metrics

## Entity Changes

This feature extends existing entities. No new entities are created.

### Extended Entity: ContributionYearSummary

**Location**: `planalign_api/models/analytics.py`

| Field | Type | Description | New/Existing |
|-------|------|-------------|--------------|
| year | int | Simulation year | Existing |
| total_employee_contributions | float | Employee deferral total | Existing |
| total_employer_match | float | Employer match total | Existing |
| total_employer_core | float | Employer core contribution total | Existing |
| total_all_contributions | float | Sum of all contributions | Existing |
| participant_count | int | Number of enrolled employees | Existing |
| average_deferral_rate | float | Avg deferral rate (decimal) | Existing |
| participation_rate | float | Participation % | Existing |
| total_employer_cost | float | Match + Core total | Existing |
| **total_compensation** | **float** | Sum of `prorated_annual_compensation` | **NEW** |
| **employer_cost_rate** | **float** | `total_employer_cost / total_compensation * 100` | **NEW** |

**Validation Rules**:
- `total_compensation >= 0` (non-negative)
- `employer_cost_rate >= 0` (non-negative percentage)
- If `total_compensation == 0`, then `employer_cost_rate = 0.0`

### Extended Entity: DCPlanAnalytics

**Location**: `planalign_api/models/analytics.py`

| Field | Type | Description | New/Existing |
|-------|------|-------------|--------------|
| scenario_id | str | Scenario UUID | Existing |
| scenario_name | str | Scenario display name | Existing |
| total_eligible | int | Eligible employee count | Existing |
| total_enrolled | int | Enrolled employee count | Existing |
| participation_rate | float | Participation % | Existing |
| participation_by_method | ParticipationByMethod | Enrollment breakdown | Existing |
| contribution_by_year | List[ContributionYearSummary] | Year-by-year data | Existing |
| total_employee_contributions | float | Grand total employee | Existing |
| total_employer_match | float | Grand total match | Existing |
| total_employer_core | float | Grand total core | Existing |
| total_all_contributions | float | Grand total all | Existing |
| deferral_rate_distribution | List[DeferralRateBucket] | Rate distribution | Existing |
| escalation_metrics | EscalationMetrics | Escalation data | Existing |
| irs_limit_metrics | IRSLimitMetrics | IRS limit data | Existing |
| average_deferral_rate | float | Weighted avg deferral | Existing |
| total_employer_cost | float | Grand total employer | Existing |
| **total_compensation** | **float** | Sum across all years | **NEW** |
| **employer_cost_rate** | **float** | Aggregate cost rate % | **NEW** |

**Validation Rules**:
- `total_compensation = sum(c.total_compensation for c in contribution_by_year)`
- `employer_cost_rate = total_employer_cost / total_compensation * 100` (if total_compensation > 0)
- If `total_compensation == 0`, then `employer_cost_rate = 0.0`

## Relationships

```
DCPlanAnalytics
    └── contribution_by_year: List[ContributionYearSummary]
            └── Each year includes total_compensation and employer_cost_rate
```

## Data Source

All data aggregated from existing `fct_workforce_snapshot` table:

```sql
SELECT
    simulation_year as year,
    SUM(prorated_annual_compensation) as total_compensation,
    SUM(employer_match_amount + employer_core_amount) as total_employer_cost,
    -- employer_cost_rate calculated in Python
FROM fct_workforce_snapshot
WHERE UPPER(employment_status) = 'ACTIVE'
GROUP BY simulation_year
```

## State Transitions

N/A - This is a read-only display feature. No state mutations.
