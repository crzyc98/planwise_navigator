# Data Model: IRS 402(g) Limits Hardening

**Feature**: 008-irs-402g-limits-hardening
**Date**: 2025-12-23

## Entity: IRS Limit Configuration

**Table Name**: `config_irs_limits` (dbt seed)
**Source File**: `dbt/seeds/config_irs_limits.csv`
**Primary Key**: `limit_year`

### Attributes

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `limit_year` | INTEGER | PK, NOT NULL | Plan year (e.g., 2025, 2026) |
| `base_limit` | INTEGER | NOT NULL, > 0 | IRS 402(g) base elective deferral limit in dollars |
| `catch_up_limit` | INTEGER | NOT NULL, >= base_limit | Total limit for catch-up eligible employees (base + catch-up amount) |
| `catch_up_age_threshold` | INTEGER | NOT NULL, > 0 | Minimum age for catch-up eligibility (typically 50) |

### Validation Rules

1. `base_limit` must be positive integer
2. `catch_up_limit` must be >= `base_limit`
3. `catch_up_age_threshold` must be positive integer (typically 50)
4. `limit_year` must be unique (one row per year)
5. Years should be contiguous or have fallback logic for gaps

### Sample Data

```csv
limit_year,base_limit,catch_up_limit,catch_up_age_threshold
2025,23500,31000,50
2026,24000,32000,50
2027,24500,32500,50
2028,25000,33000,50
2029,25500,33500,50
2030,26000,34000,50
```

### Relationships

```
config_irs_limits (1) ←──── (N) int_employee_contributions
                                 └─ via limit_year = simulation_year

config_irs_limits (1) ←──── (N) fct_workforce_snapshot
                                 └─ via limit_year = simulation_year
```

---

## Entity: Employee Contribution

**Table Name**: `int_employee_contributions` (dbt model)
**Materialization**: Incremental (delete+insert)
**Unique Key**: `[employee_id, simulation_year]`

### IRS Limit Enforcement Attributes

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `requested_contribution_amount` | DECIMAL(12,2) | Calculated | Pre-cap contribution (compensation × deferral_rate) |
| `annual_contribution_amount` | DECIMAL(12,2) | Calculated | Post-cap contribution (LEAST of requested and applicable_limit) |
| `applicable_irs_limit` | INTEGER | Derived | Age-appropriate limit from seed |
| `irs_limit_applied` | BOOLEAN | Calculated | TRUE if capping occurred |
| `amount_capped_by_irs_limit` | DECIMAL(12,2) | Calculated | requested - actual when capped |
| `limit_type` | VARCHAR | Derived | 'BASE' or 'CATCH_UP' |

### Limit Enforcement Logic

```sql
-- Determine applicable limit based on age and seed configuration
applicable_irs_limit = CASE
    WHEN current_age >= config_irs_limits.catch_up_age_threshold
    THEN config_irs_limits.catch_up_limit
    ELSE config_irs_limits.base_limit
END

-- Calculate IRS-compliant contribution
annual_contribution_amount = LEAST(
    requested_contribution_amount,
    applicable_irs_limit
)

-- Flag when limit applied
irs_limit_applied = (requested_contribution_amount > applicable_irs_limit)

-- Record amount capped
amount_capped_by_irs_limit = GREATEST(0,
    requested_contribution_amount - applicable_irs_limit
)
```

---

## Entity: Catch-Up Eligibility

**Derived Attribute** (not stored separately)

### Eligibility Determination

```sql
is_catch_up_eligible = (current_age >= config_irs_limits.catch_up_age_threshold)
```

### Age Calculation Rule

Per IRS regulations and spec assumptions:
- Age is determined as of **December 31 of the plan year**
- Uses `current_age` field from `int_employee_compensation_by_year`

---

## State Transitions

### Contribution Limit State Machine

```
                        ┌─────────────────────────────┐
                        │    Employee Input           │
                        │  (compensation, deferral)   │
                        └────────────┬────────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────────┐
                        │  Calculate Requested Amount │
                        │  compensation × deferral    │
                        └────────────┬────────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────────┐
                        │  Determine Applicable Limit │
                        │  age >= threshold? catch_up │
                        │                  : base     │
                        └────────────┬────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     │                               │
                     ▼                               ▼
        ┌────────────────────┐          ┌────────────────────┐
        │ requested <= limit │          │ requested > limit  │
        │ irs_limit_applied  │          │ irs_limit_applied  │
        │     = FALSE        │          │     = TRUE         │
        │ amount = requested │          │ amount = limit     │
        └────────────────────┘          └────────────────────┘
```

---

## Invariants

These invariants MUST hold for all data:

1. **IRS Compliance Invariant**
   ```
   ∀ employee: annual_contribution_amount <= applicable_irs_limit
   ```

2. **Flag Accuracy Invariant**
   ```
   ∀ employee: irs_limit_applied = (requested_contribution_amount > applicable_irs_limit)
   ```

3. **Capped Amount Consistency**
   ```
   ∀ employee: amount_capped_by_irs_limit = MAX(0, requested - annual_contribution_amount)
   ```

4. **Limit Type Consistency**
   ```
   ∀ employee: limit_type = 'CATCH_UP' ⟺ current_age >= catch_up_age_threshold
   ```

---

## Migration Notes

### Seed File Rename

**From**: `dbt/seeds/irs_contribution_limits.csv`
**To**: `dbt/seeds/config_irs_limits.csv`

**Column Mapping** (no changes):
| Old Column | New Column |
|------------|------------|
| `limit_year` | `limit_year` |
| `base_limit` | `base_limit` |
| `catch_up_limit` | `catch_up_limit` |
| `catch_up_age_threshold` | `catch_up_age_threshold` |

Note: Spec requested `catchup_limit` and `catchup_age` but existing seed uses underscores. Keeping existing convention for backward compatibility.
