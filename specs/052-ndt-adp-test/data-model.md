# Data Model: NDT ADP Test

**Branch**: `052-ndt-adp-test` | **Date**: 2026-02-19

## Entities

### ADPEmployeeDetail

Individual participant's ADP test data for audit detail.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| employee_id | string | yes | Unique employee identifier |
| is_hce | boolean | yes | HCE classification based on prior-year compensation |
| employee_deferrals | float | yes | Total elective deferrals (pre-tax + Roth) for the plan year |
| plan_compensation | float | yes | Plan-year eligible compensation (prorated for mid-year entrants) |
| individual_adp | float | yes | Employee's ADP: deferrals / compensation |
| prior_year_compensation | float | no | Prior-year compensation used for HCE determination (null if prior year unavailable) |

**Validation Rules**:
- `individual_adp` = `employee_deferrals` / `plan_compensation`
- `plan_compensation` > 0 (zero compensation employees are excluded)
- `individual_adp` >= 0.0 (cannot be negative)
- `employee_deferrals` >= 0.0 (zero deferrals are valid, not excluded)

### ADPScenarioResult

Outcome of an ADP test for a single scenario and year.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| scenario_id | string | yes | — | Scenario identifier |
| scenario_name | string | yes | — | Human-readable scenario name |
| simulation_year | int | yes | — | Year tested |
| test_result | string | yes | — | "pass", "fail", "exempt", or "error" |
| test_message | string | no | null | Informational/error message |
| hce_count | int | yes | 0 | Number of HCE participants |
| nhce_count | int | yes | 0 | Number of NHCE participants |
| excluded_count | int | yes | 0 | Participants excluded (zero comp, ineligible) |
| hce_average_adp | float | yes | 0.0 | Arithmetic mean of HCE individual ADPs |
| nhce_average_adp | float | yes | 0.0 | Arithmetic mean of NHCE individual ADPs |
| basic_test_threshold | float | yes | 0.0 | Prong 1: NHCE avg × 1.25 |
| alternative_test_threshold | float | yes | 0.0 | Prong 2: min(NHCE avg × 2, NHCE avg + 0.02) |
| applied_test | string | yes | "basic" | "basic" or "alternative" (whichever is more favorable) |
| applied_threshold | float | yes | 0.0 | The threshold from the applied test |
| margin | float | yes | 0.0 | applied_threshold - hce_average_adp (positive = passing) |
| excess_hce_amount | float | no | null | Total excess HCE deferral amount (only when failing) |
| testing_method | string | yes | "current" | "current" or "prior" year testing method |
| safe_harbor | boolean | yes | false | Whether safe harbor exemption was applied |
| hce_threshold_used | int | yes | 0 | HCE compensation threshold for audit trail |
| employees | list | no | null | List of ADPEmployeeDetail (when requested) |

**Validation Rules**:
- `test_result` in ("pass", "fail", "exempt", "error")
- `applied_test` in ("basic", "alternative")
- `testing_method` in ("current", "prior")
- When `test_result` = "exempt", `safe_harbor` must be true
- When `test_result` = "fail", `excess_hce_amount` must be populated and > 0
- When `test_result` = "pass" or "exempt", `excess_hce_amount` is null
- `margin` = `applied_threshold` - `hce_average_adp`
- `hce_count` + `nhce_count` + `excluded_count` = total eligible population queried

**State Transitions**: None — this is a point-in-time calculation result, not a stateful entity.

### ADPTestResponse

Wrapper for multi-scenario ADP test results.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| test_type | string | yes | "adp" | Always "adp" |
| year | int | yes | — | Simulation year tested |
| results | list | yes | — | List of ADPScenarioResult |

## Relationships

```
ADPTestResponse
  └── 1:N ADPScenarioResult (one per scenario)
        └── 1:N ADPEmployeeDetail (optional, one per eligible participant)
```

## Data Sources

All data is read-only from `fct_workforce_snapshot` table in per-scenario DuckDB databases:

| Entity Field | Source Column | Source Table |
|-------------|--------------|-------------|
| employee_deferrals | `prorated_annual_contributions` | fct_workforce_snapshot |
| plan_compensation | `prorated_annual_compensation` | fct_workforce_snapshot |
| prior_year_compensation | `current_compensation` (year - 1) | fct_workforce_snapshot |
| HCE threshold | `hce_compensation_threshold` | config_irs_limits |

## Excess HCE Amount Calculation

When test fails: `excess_hce_amount = (hce_average_adp - applied_threshold) × sum(hce_plan_compensations)`

This represents the aggregate dollar reduction in HCE deferrals needed for the HCE average ADP to meet the applied threshold.
