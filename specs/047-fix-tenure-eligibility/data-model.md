# Data Model: Fix Tenure Eligibility Enforcement

**Feature Branch**: `047-fix-tenure-eligibility`
**Date**: 2026-02-11

## Modified Entities

### 1. Employer Eligibility Record (`int_employer_eligibility` table)

**Schema changes**: None. Behavioral change only.

**Affected columns** (output changes):

| Column | Before Fix | After Fix |
|--------|-----------|-----------|
| `eligible_for_match` | `TRUE` for new hires regardless of tenure config | `FALSE` when `tenure < minimum_tenure_years` and `allow_new_hires` resolves to `false` |
| `eligible_for_core` | Same issue | Same fix |
| `match_eligibility_reason` | `'eligible'` for ineligible new hires | `'insufficient_tenure'` |
| `match_allow_new_hires` (metadata) | Always `true` when not explicitly set | Reflects resolved value (may now be `false`) |
| `core_allow_new_hires` (metadata) | Always `true` when not explicitly set | Reflects resolved value (may now be `false`) |

### 2. Eligibility Configuration (`EmployerMatchEligibilitySettings` Pydantic model)

**No field additions**. Default resolution change:

| Field | Current Default | New Default |
|-------|----------------|-------------|
| `allow_new_hires` | `True` (unconditional) | `True` if `minimum_tenure_years == 0`, else `False` |

New `@model_validator(mode='before')` resolves the conditional default before Pydantic applies field defaults.

### 3. Workforce Snapshot (`fct_workforce_snapshot` table)

**Schema changes**: None. Downstream effect only.

| Column | Impact |
|--------|--------|
| `employer_match_amount` | Will be `0.0` for newly-ineligible employees |
| `employer_core_amount` | Will be `0.0` for newly-ineligible employees |
| `total_employer_contributions` | Reduced by excluded employees' amounts |

## State Transitions

No new state transitions. Existing eligibility determination flow is unchanged — only the input defaults are corrected.

## Data Flow

```
simulation_config.yaml / Studio UI (dc_plan)
  → SimulationConfig (Pydantic, with new model_validator warning)
    → _export_employer_match_vars() / _export_core_contribution_vars()
      → dbt --vars { employer_match: { eligibility: { allow_new_hires: <resolved> } } }
        → int_employer_eligibility.sql (conditional Jinja default as final fallback)
          → eligible_for_match / eligible_for_core (correct output)
            → int_employee_match_calculations / int_employer_core_contributions
              → fct_workforce_snapshot (correct contribution amounts)
```

## Validation Rules

- `eligible_for_match = FALSE` when `current_tenure < minimum_tenure_years` AND `allow_new_hires = FALSE`
- `eligible_for_core = FALSE` when `current_tenure < core_minimum_tenure_years` AND `core_allow_new_hires = FALSE`
- Boundary: `current_tenure >= minimum_tenure_years` → eligible (`>=` check, not `>`)
- `apply_eligibility = FALSE` → no tenure check (backward compat, unchanged)
