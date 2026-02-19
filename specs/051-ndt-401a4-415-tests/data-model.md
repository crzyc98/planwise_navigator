# Data Model: NDT 401(a)(4) & 415 Tests

**Branch**: `051-ndt-401a4-415-tests` | **Date**: 2026-02-19

## Entities

### Section401a4ScenarioResult

Represents the outcome of a 401(a)(4) general nondiscrimination test for a single scenario/year.

| Field | Type | Description |
|-------|------|-------------|
| scenario_id | string | Scenario identifier |
| scenario_name | string | Human-readable scenario name |
| simulation_year | int | Year tested |
| test_result | enum: pass/fail/error | Overall test outcome |
| test_message | string? | Error or informational message |
| applied_test | enum: ratio/general | Which test determined the result |
| hce_count | int | Number of HCE participants |
| nhce_count | int | Number of NHCE participants |
| excluded_count | int | Participants excluded (zero comp, etc.) |
| hce_average_rate | float | HCE group average employer contribution rate |
| nhce_average_rate | float | NHCE group average employer contribution rate |
| hce_median_rate | float | HCE group median (used in general test) |
| nhce_median_rate | float | NHCE group median (used in general test) |
| ratio | float | NHCE average / HCE average |
| ratio_test_threshold | float | 0.70 (fixed by IRS) |
| margin | float | Ratio minus threshold (positive = passing) |
| include_match | bool | Whether match was included in rates |
| service_risk_flag | bool | Elevated risk from service-based NEC + tenure skew |
| service_risk_detail | string? | Detail when flag is true (avg HCE/NHCE tenure) |
| hce_threshold_used | int | HCE compensation threshold applied |
| employees | list[Section401a4EmployeeDetail]? | Optional per-employee breakdown |

### Section401a4EmployeeDetail

Per-participant detail for 401(a)(4) test.

| Field | Type | Description |
|-------|------|-------------|
| employee_id | string | Employee identifier |
| is_hce | bool | HCE classification |
| employer_nec_amount | float | Employer core/NEC contribution |
| employer_match_amount | float | Employer match (0 if include_match=false) |
| total_employer_amount | float | NEC + match (or NEC only) |
| plan_compensation | float | 401(a)(17)-capped compensation |
| contribution_rate | float | total_employer_amount / plan_compensation |
| years_of_service | float | Current tenure |

### Section415ScenarioResult

Represents the outcome of a 415 annual additions limit test for a single scenario/year.

| Field | Type | Description |
|-------|------|-------------|
| scenario_id | string | Scenario identifier |
| scenario_name | string | Human-readable scenario name |
| simulation_year | int | Year tested |
| test_result | enum: pass/fail/error | Overall outcome (fail if any breach) |
| test_message | string? | Error or informational message |
| total_participants | int | Total participants tested |
| excluded_count | int | Participants excluded (zero comp, etc.) |
| breach_count | int | Participants exceeding 415 limit |
| at_risk_count | int | Participants at or above warning threshold |
| passing_count | int | Participants safely under limit |
| max_utilization_pct | float | Highest utilization % across all participants |
| warning_threshold_pct | float | Configurable threshold used (default 0.95) |
| annual_additions_limit | int | IRS dollar limit for the year |
| employees | list[Section415EmployeeDetail]? | Optional per-employee breakdown |

### Section415EmployeeDetail

Per-participant detail for 415 test.

| Field | Type | Description |
|-------|------|-------------|
| employee_id | string | Employee identifier |
| status | enum: pass/at_risk/breach | Individual participant status |
| employee_deferrals | float | Base deferrals (excluding catch-up) |
| employer_match | float | Employer match amount |
| employer_nec | float | Employer NEC/core amount |
| total_annual_additions | float | Sum of above three components |
| gross_compensation | float | Uncapped gross compensation (415 comp) |
| applicable_limit | float | Lesser of IRS dollar limit or 100% of gross comp |
| headroom | float | applicable_limit - total_annual_additions |
| utilization_pct | float | total_annual_additions / applicable_limit |

### Section401a4TestResponse (wrapper)

| Field | Type | Description |
|-------|------|-------------|
| test_type | string | Always "401a4" |
| year | int | Simulation year |
| results | list[Section401a4ScenarioResult] | One per scenario |

### Section415TestResponse (wrapper)

| Field | Type | Description |
|-------|------|-------------|
| test_type | string | Always "415" |
| year | int | Simulation year |
| results | list[Section415ScenarioResult] | One per scenario |

## Seed Schema Change

### config_irs_limits.csv — Add Column

| Column | Type | Description |
|--------|------|-------------|
| annual_additions_limit | int | IRS Section 415(c) annual additions dollar limit |

Added to existing rows. No schema migration needed — dbt seed reload handles it.

## Validation Rules

- `contribution_rate` must be >= 0.0 (no negative rates)
- `ratio` must be >= 0.0 (NHCE avg / HCE avg; undefined when HCE avg = 0)
- `utilization_pct` must be >= 0.0 (total additions / applicable limit)
- `headroom` can be negative (indicates breach)
- `applicable_limit` must be > 0 (validated by excluding zero-comp participants)
- `warning_threshold_pct` must be between 0.0 and 1.0 inclusive

## State Transitions

Not applicable — these are stateless analytical queries against completed simulation data. No state is persisted between test runs.
