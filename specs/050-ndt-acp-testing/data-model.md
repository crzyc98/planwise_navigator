# Data Model: NDT ACP Testing

**Branch**: `050-ndt-acp-testing` | **Date**: 2026-02-19

## Entities

### 1. IRS Limits Configuration (Seed Extension)

Extends existing `config_irs_limits.csv` with one new column.

| Field | Type | Description |
|-------|------|-------------|
| `limit_year` | INTEGER | Tax/plan year (PK) |
| `base_limit` | INTEGER | 402(g) elective deferral limit |
| `catch_up_limit` | INTEGER | 402(g) catch-up limit |
| `catch_up_age_threshold` | INTEGER | Age for catch-up eligibility |
| `compensation_limit` | INTEGER | 401(a)(17) compensation cap |
| **`hce_compensation_threshold`** | **INTEGER** | **HCE prior-year comp threshold (NEW)** |

**Validation rules**:
- `hce_compensation_threshold` > 0 for all years
- Values increase monotonically (threshold does not decrease year-over-year)

### 2. HCE Determination (Computed at Query Time)

Not persisted as a table. Computed in the analytics query by joining current-year snapshot with prior-year snapshot and IRS limits.

| Field | Type | Description |
|-------|------|-------------|
| `employee_id` | VARCHAR | Employee identifier |
| `simulation_year` | INTEGER | Current test year |
| `prior_year_compensation` | DOUBLE | Compensation from year - 1 |
| `hce_threshold` | INTEGER | IRS threshold for determination year |
| `is_hce` | BOOLEAN | TRUE if prior_year_comp > threshold |
| `determination_method` | VARCHAR | `prior_year` (only method for MVP) |

**Derivation rules**:
- `prior_year_compensation` = `current_compensation` from `fct_workforce_snapshot` where `simulation_year = test_year - 1`
- `hce_threshold` = `hce_compensation_threshold` from `config_irs_limits` where `limit_year = test_year - 1`
- First simulation year fallback: use current year compensation if no prior year exists
- Employee must appear in current year snapshot to be included

### 3. Per-Employee ACP (Computed at Query Time)

Not persisted. Computed in the analytics query.

| Field | Type | Description |
|-------|------|-------------|
| `employee_id` | VARCHAR | Employee identifier |
| `simulation_year` | INTEGER | Test year |
| `is_hce` | BOOLEAN | HCE classification |
| `is_plan_eligible` | BOOLEAN | Plan eligibility status |
| `is_enrolled` | BOOLEAN | Enrollment status |
| `employer_match_amount` | DOUBLE | Employer match $ |
| `eligible_compensation` | DOUBLE | Prorated annual compensation |
| `individual_acp` | DOUBLE | ACP = match / compensation |

**Derivation rules**:
- Population: all employees where `current_eligibility_status = 'eligible'` in current year snapshot
- `individual_acp` = `employer_match_amount / prorated_annual_compensation`
- Non-enrolled employees: `employer_match_amount = 0`, so `individual_acp = 0`
- Employees with `prorated_annual_compensation = 0` or NULL: excluded from test
- Terminated employees who were eligible during the year: included

### 4. ACP Test Result (API Response)

Computed and returned in the API response. Not persisted.

| Field | Type | Description |
|-------|------|-------------|
| `scenario_id` | VARCHAR | Scenario identifier |
| `scenario_name` | VARCHAR | Display name |
| `simulation_year` | INTEGER | Test year |
| `hce_count` | INTEGER | Number of HCE employees |
| `nhce_count` | INTEGER | Number of NHCE employees |
| `excluded_count` | INTEGER | Employees excluded (zero comp) |
| `eligible_not_enrolled_count` | INTEGER | Eligible but not enrolled |
| `hce_average_acp` | DOUBLE | HCE group average ACP (%) |
| `nhce_average_acp` | DOUBLE | NHCE group average ACP (%) |
| `basic_test_threshold` | DOUBLE | NHCE avg x 1.25 |
| `alternative_test_threshold` | DOUBLE | Lesser of (NHCE x 2, NHCE + 2%) |
| `applied_test` | VARCHAR | `basic` or `alternative` |
| `applied_threshold` | DOUBLE | The threshold used for determination |
| `test_result` | VARCHAR | `pass` or `fail` |
| `margin` | DOUBLE | Threshold - HCE avg (positive = passing) |
| `hce_threshold_used` | INTEGER | IRS $ threshold for HCE determination |

**Business rules**:
- `basic_test_threshold` = `nhce_average_acp * 1.25`
- `alternative_test_threshold` = `MIN(nhce_average_acp * 2.0, nhce_average_acp + 0.02)`
- `applied_test` = whichever yields a higher threshold (more favorable to plan)
- `test_result` = `pass` if `hce_average_acp <= applied_threshold`, else `fail`
- `margin` = `applied_threshold - hce_average_acp`

**Edge case results**:
- No NHCE employees: `test_result = 'error'`, message = "Insufficient NHCE population"
- No HCE employees: `test_result = 'pass'`, message = "No HCE employees in population"
- No eligible employees: `test_result = 'error'`, message = "No eligible employees found"

### 5. Per-Employee Detail (API Response, Optional)

Returned when client requests detail. Same computation as entity 3, formatted for display.

| Field | Type | Description |
|-------|------|-------------|
| `employee_id` | VARCHAR | Employee identifier |
| `is_hce` | BOOLEAN | HCE classification |
| `is_enrolled` | BOOLEAN | Enrollment status |
| `employer_match_amount` | DOUBLE | Match contribution $ |
| `eligible_compensation` | DOUBLE | Prorated annual compensation |
| `individual_acp` | DOUBLE | ACP percentage |
| `prior_year_compensation` | DOUBLE | Used for HCE determination |

## Relationships

```
config_irs_limits (seed, extended)
    |
    +--- hce_compensation_threshold ---> HCE Determination query
    |
fct_workforce_snapshot (existing, read-only)
    |
    +--- current year: eligibility, enrollment, match, compensation ---> Per-Employee ACP
    +--- prior year: current_compensation ---> HCE Determination
    |
Per-Employee ACP + HCE Determination
    |
    +--- GROUP BY is_hce ---> ACP Test Result (aggregated)
    +--- raw rows ---> Per-Employee Detail (drill-down)
```

## State Transitions

None. This feature is read-only analytics against completed simulation data. No state is created or modified.
