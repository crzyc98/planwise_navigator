# Contracts: Fix 401(a)(17) Compensation Limit

**Feature**: 026-fix-401a17-comp-limit
**Date**: 2026-01-22

## API Contracts

**N/A** - This feature modifies dbt models and seeds only. No REST API, GraphQL, or external service contracts are affected.

## Data Contracts

### Seed Schema: config_irs_limits

The seed file gains a new column. Downstream models depend on this schema.

**Contract**:
```yaml
# Implicit contract via dbt seed
name: config_irs_limits
columns:
  - name: limit_year
    type: INTEGER
    constraints:
      - not_null
      - unique
  - name: base_limit
    type: INTEGER
    constraints:
      - not_null
      - positive
  - name: catch_up_limit
    type: INTEGER
    constraints:
      - not_null
      - positive
  - name: catch_up_age_threshold
    type: INTEGER
    constraints:
      - not_null
      - positive
  - name: compensation_limit  # NEW
    type: INTEGER
    constraints:
      - not_null
      - positive
```

### Model Output Schema: int_employee_match_calculations

New column added to output schema.

**New Column**:
```yaml
- name: irs_401a17_limit_applied
  type: BOOLEAN
  description: True if employee compensation exceeded 401(a)(17) limit and was capped
```

### Model Output Schema: int_employer_core_contributions

New column added to output schema.

**New Column**:
```yaml
- name: irs_401a17_limit_applied
  type: BOOLEAN
  description: True if employee compensation exceeded 401(a)(17) limit and was capped
```

## Integration Points

No external integrations are affected by this change.
