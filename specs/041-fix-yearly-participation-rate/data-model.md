# Data Model: Fix Yearly Participation Rate Consistency

**Feature**: 041-fix-yearly-participation-rate
**Date**: 2026-02-10

## Entities

### ContributionYearSummary (unchanged schema)

Per-year contribution and participation data returned in the analytics response.

| Field                      | Type    | Description                                         | Change |
| -------------------------- | ------- | --------------------------------------------------- | ------ |
| year                       | int     | Simulation year                                     | None   |
| total_employee_contributions | float | Total employee deferrals                            | None   |
| total_employer_match       | float   | Total employer match contributions                  | None   |
| total_employer_core        | float   | Total employer core contributions                   | None   |
| total_all_contributions    | float   | Total of all contributions                          | None   |
| participant_count          | int     | Number of enrolled participants                     | None   |
| average_deferral_rate      | float   | Average deferral rate for enrolled participants     | None   |
| **participation_rate**     | float   | **Participation rate for this year (0-100%)**       | **Calculation fix** |
| total_employer_cost        | float   | Sum of match and core contributions                 | None   |
| total_compensation         | float   | Sum of prorated_annual_compensation                 | None   |
| employer_cost_rate         | float   | Employer cost as % of total compensation            | None   |

**Calculation change for `participation_rate`**:
- **Before**: `enrolled_count / total_count * 100` (all employees in denominator)
- **After**: `active_enrolled_count / active_count * 100` (active employees only)

### DCPlanAnalytics (unchanged schema)

Top-level analytics response. No changes to field definitions or population logic.

### fct_workforce_snapshot (source table, unchanged)

| Column                    | Type    | Relevant to fix |
| ------------------------- | ------- | --------------- |
| simulation_year           | int     | GROUP BY key    |
| employment_status         | varchar | Filter for ACTIVE employees in participation rate |
| is_enrolled_flag          | boolean | Numerator condition for participation rate |
| prorated_annual_contributions | decimal | Contribution totals (all employees) |
| employer_match_amount     | decimal | Contribution totals (all employees) |
| employer_core_amount      | decimal | Contribution totals (all employees) |
| current_deferral_rate     | decimal | Average deferral rate (enrolled only) |
| prorated_annual_compensation | decimal | Compensation totals (all employees) |

## Relationships

No relationship changes. The fix modifies a single SQL aggregation expression within an existing query. All entity relationships remain unchanged.

## Validation Rules

- `participation_rate` MUST be in range [0.0, 100.0]
- `participation_rate` MUST be 0.0 when no active employees exist for a year
- Final-year `ContributionYearSummary.participation_rate` MUST match `DCPlanAnalytics.participation_rate` within 0.01 pp
