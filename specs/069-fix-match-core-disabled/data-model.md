# Data Model: Fix DC Plan Match/Core Contributions When Disabled

**Date**: 2026-03-13
**Feature**: 069-fix-match-core-disabled

## Entities

### Config Export Variables (Modified)

New variable added to the dbt variable export:

| Variable | Type | Default | Source |
|----------|------|---------|--------|
| `employer_match_enabled` | boolean | `true` | `dc_plan.match_enabled` from scenario config_overrides |

Existing variable (no changes needed):

| Variable | Type | Default | Source |
|----------|------|---------|--------|
| `employer_core_enabled` | boolean | `true` | `dc_plan.core_enabled` or `employer_core_contribution.enabled` |

### Match Calculation Model Output (Modified)

Affected columns in `int_employee_match_calculations`:

| Column | Change | When `employer_match_enabled = false` |
|--------|--------|---------------------------------------|
| `employer_match_amount` | Gated | Always `0.00` |
| `capped_match_amount` | Gated | Always `0.00` |
| `match_status` | New value | `'disabled'` |
| `uncapped_match_amount` | Gated | Always `0.00` |
| `match_cap_applied` | Gated | Always `FALSE` |

### DC Plan Config Override (No Schema Change)

The `dc_plan` object in `config_overrides` already contains:

```
dc_plan:
  match_enabled: boolean     # Already sent by UI, now read by export
  core_enabled: boolean      # Already fully wired
  match_template: string
  match_tiers: array
  match_cap_percent: float
  ...
```

## State Transitions

```
match_enabled toggle:
  true → false:  All match amounts become $0, match_status = 'disabled'
  false → true:  Match calculations resume using preserved formula/tiers

  Note: Formula/tier configuration is preserved regardless of enabled state.
        Only the calculation output changes.
```

## Validation Rules

- `employer_match_enabled` must be a boolean (true/false)
- When not explicitly set, defaults to `true` for backward compatibility
- The enabled flag applies uniformly to all employees in the scenario (no per-employee override)
- The enabled flag applies to all simulation years in a multi-year run
