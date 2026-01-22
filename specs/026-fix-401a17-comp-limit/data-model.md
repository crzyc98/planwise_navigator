# Data Model: Fix 401(a)(17) Compensation Limit

**Feature**: 026-fix-401a17-comp-limit
**Date**: 2026-01-22

## Entity Changes

### Modified: config_irs_limits (seed)

**Location**: `dbt/seeds/config_irs_limits.csv`

| Column | Type | Description | Change |
|--------|------|-------------|--------|
| limit_year | INTEGER | Tax year | Existing |
| base_limit | INTEGER | 402(g) base deferral limit | Existing |
| catch_up_limit | INTEGER | 402(g) catch-up limit | Existing |
| catch_up_age_threshold | INTEGER | Age for catch-up eligibility | Existing |
| **compensation_limit** | **INTEGER** | **401(a)(17) compensation cap** | **NEW** |

**Sample Data**:
```csv
limit_year,base_limit,catch_up_limit,catch_up_age_threshold,compensation_limit
2025,23500,31000,50,350000
2026,24000,32000,50,360000
2027,24500,32500,50,370000
```

**Validation Rules**:
- `compensation_limit` MUST be > 0
- `compensation_limit` MUST be >= `base_limit` (logically required)
- One row per `limit_year` (existing uniqueness constraint)

---

### Modified: int_employee_match_calculations (model output)

**Location**: `dbt/models/intermediate/events/int_employee_match_calculations.sql`

| Column | Type | Description | Change |
|--------|------|-------------|--------|
| employee_id | VARCHAR | Employee identifier | Existing |
| simulation_year | INTEGER | Simulation year | Existing |
| eligible_compensation | DECIMAL | Full compensation (uncapped) | Existing |
| employer_match_amount | DECIMAL | Capped match amount | Existing (behavior change) |
| **irs_401a17_limit_applied** | **BOOLEAN** | **True if comp was capped** | **NEW** |
| ... | ... | Other existing fields | Existing |

**Behavior Change**:
- `employer_match_amount`: Now capped at `match_cap_percent × MIN(eligible_compensation, irs_401a17_limit)`
- Previously: `match_cap_percent × eligible_compensation`

**New Calculation Logic**:
```sql
-- Capped match (deferral-based mode)
LEAST(
    am.match_amount,
    LEAST(am.eligible_compensation, lim.irs_401a17_limit) * {{ match_cap_percent }}
) AS capped_match_amount

-- Audit field
am.eligible_compensation > lim.irs_401a17_limit AS irs_401a17_limit_applied
```

---

### Modified: int_employer_core_contributions (model output)

**Location**: `dbt/models/intermediate/int_employer_core_contributions.sql`

| Column | Type | Description | Change |
|--------|------|-------------|--------|
| employee_id | VARCHAR | Employee identifier | Existing |
| simulation_year | INTEGER | Simulation year | Existing |
| eligible_compensation | DECIMAL | Full compensation (uncapped) | Existing |
| employer_core_amount | DECIMAL | Capped core contribution | Existing (behavior change) |
| **irs_401a17_limit_applied** | **BOOLEAN** | **True if comp was capped** | **NEW** |
| ... | ... | Other existing fields | Existing |

**Behavior Change**:
- `employer_core_amount`: Now capped at `core_rate × MIN(eligible_compensation, irs_401a17_limit)`
- Previously: `core_rate × eligible_compensation`

**New Calculation Logic**:
```sql
-- Capped compensation for core calculation
LEAST(
    COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation),
    lim.irs_401a17_limit
) * {{ core_rate }}

-- Audit field
COALESCE(wf.prorated_annual_compensation, pop.prorated_annual_compensation, pop.employee_compensation) > lim.irs_401a17_limit AS irs_401a17_limit_applied
```

---

## Relationships

```
config_irs_limits (1) ──── (N) int_employee_match_calculations
                  │              (joined on simulation_year = limit_year)
                  │
                  └──── (N) int_employer_core_contributions
                              (joined on simulation_year = limit_year)
```

**Join Pattern**: Single-row CTE cross-joined into calculation, then filtered by year equality.

---

## State Transitions

N/A - This feature does not introduce new states or state transitions. It modifies calculation behavior for existing contribution calculations.

---

## Impact Analysis

### Downstream Models

Models that reference the modified outputs:

| Model | Impact | Action Required |
|-------|--------|-----------------|
| `fct_yearly_events` | None | No DC contribution events use these amounts directly |
| `fct_workforce_snapshot` | None | Does not reference match/core calculation models |
| `int_employer_eligibility` | None | Input to match/core, not output |
| Downstream dashboards | Informational | Will show lower employer costs for high earners |

### Backward Compatibility

- **New field**: `irs_401a17_limit_applied` - additive, no breaking change
- **Calculation change**: `employer_match_amount` and `employer_core_amount` will be lower for high earners
- **Data migration**: None required (recalculation on next simulation run)

---

## Validation Constraints

### Seed Validation (config_irs_limits)

```yaml
# dbt/seeds/schema.yml (add to existing)
seeds:
  - name: config_irs_limits
    columns:
      - name: compensation_limit
        tests:
          - not_null
          - positive_values
```

### Output Validation (test_401a17_compliance.sql)

```sql
-- Singular test: Returns violations (passes if 0 rows)
-- Located: dbt/tests/data_quality/test_401a17_compliance.sql
-- Validates:
--   1. No match amount exceeds match_cap × 401(a)(17) limit
--   2. No core amount exceeds core_rate × 401(a)(17) limit
```
