# Contract: Per-Design Contribution Family Configuration

The user-facing surface of this feature is YAML configuration. This is its contract.

## Shape

```yaml
plan_design_assignment:            # owned by #631, unchanged
  default_plan_design_id: legacy
  rules:
    - type: hire_date_cutoff
      cutoff: 2026-01-01
      plan_design_id: new_hires

plan_design_parameters:            # owned by #632; `match.family` and `employer_core.family` are new
  legacy:
    match:
      family: deferral_based       # NEW
      match_template: tiered       # NEW, audit label only
      cap_percent: 0.04
      tiers:
        - {employee_min: 0.00, employee_max: 0.03, match_rate: 1.00}
        - {employee_min: 0.03, employee_max: 0.05, match_rate: 0.50}
    employer_core:
      family: flat                 # NEW
      contribution_rate: 0.02
      integration_enabled: false   # NEW — per-design (D10)
    auto_enrollment: {default_deferral_rate: 0.06, window_days: 45, scope: new_hires_only}
    deferral_escalation: {increment: 0.01, cap: 0.10}
    eligibility: {waiting_period_days: 0}

  new_hires:
    match:
      family: tenure_graded        # a DIFFERENT family in the same run
      cap_percent: 0.04
      tenure_graded_bands:
        - min_years: 0
          max_years: 5
          tiers:
            - {employee_min: 0.00, employee_max: 0.02, match_rate: 1.00}
        - min_years: 5
          max_years: null
          tiers:
            - {employee_min: 0.00, employee_max: 0.02, match_rate: 1.00}
            - {employee_min: 0.02, employee_max: 0.06, match_rate: 0.50}
    employer_core:
      family: age_banded           # a DIFFERENT core family in the same run
      contribution_rate: 0.02      # fallback; unreachable once the guard is on
      age_schedule:                # NEWLY per-design (D9)
        - {min_age: 0,  max_age: 40,   rate: 1.5}
        - {min_age: 40, max_age: 55,   rate: 2.5}
        - {min_age: 55, max_age: null, rate: 4.0}
      integration_enabled: true    # NEW — per-design (D10)
      integration_level_mode: ss_wage_base
      integration_disparity_rate: 0.0054
    auto_enrollment: {default_deferral_rate: 0.06, window_days: 45, scope: new_hires_only}
    deferral_escalation: {increment: 0.01, cap: 0.10}
    eligibility: {waiting_period_days: 90}
```

## Guarantees

| # | Guarantee |
|---|---|
| C-01 | `match.family` accepts exactly `deferral_based`, `graded_by_service`, `tenure_graded`, `points_based`. The legacy `tenure_based` is accepted and normalized to `tenure_graded`. |
| C-02 | Omitting `match.family` inherits the run-global `employer_match.employer_match_status`, so every configuration written before this feature loads and runs unchanged. |
| C-03 | A design whose `family` names a schedule that is absent or empty is rejected at config load, with a message naming the design and the missing schedule field. The simulation does not start. |
| C-04 | Designs in `plan_design_parameters` must exactly match the design set implied by `plan_design_assignment` — unchanged from #632, and still enforced with `missing=`/`extra=` diagnostics. |
| C-05 | `match_template` is descriptive. Changing it changes `formula_id`, `formula_name`, and `formula_type` in the output; it never changes an amount. |
| C-06 | `cap_percent` is consulted only for `deferral_based` designs. The other three families cap through their own `max_deferral_pct` per band, as today. |
| C-07 | Two designs may share a family with different schedules; this is the #632 behavior and is unaffected. |
| C-08 | `employer_core.family` accepts exactly `flat`, `graded_by_service`, `points_based`, `age_banded`. |
| C-09 | Omitting `employer_core.family` inherits the run-global `employer_core_status`, so pre-existing configurations load unchanged. |
| C-10 | Match family and core family are independent. Any of the 16 combinations is valid, and a design may differ from another in core family alone. |
| C-11 | `age_schedule` and `points_schedule` are per-design. A configuration setting them per-design is honored, never silently flattened to a run-global value (FR-017). |
| C-12 | Core integration settings (`integration_enabled`, `integration_level_mode`, `integration_level_value`, `integration_disparity_rate`) are per-design. A grandfathered design keeps its own disparity treatment (FR-018). |
| C-13 | `integration_level_value` is required when `integration_level_mode` is `explicit`, and rejected at load otherwise. |
| C-14 | For a band-based core family, `contribution_rate` remains parseable but is unreachable at run time: a core-eligible employee falling outside every band aborts the run rather than silently taking it (D8). |

## Rejected configurations

These must fail at load, not at run time:

```yaml
# C-03: family without its schedule
new_hires:
  match: {family: points_based, cap_percent: 0.04, points_tiers: []}

# C-01: unknown family
new_hires:
  match: {family: age_weighted, cap_percent: 0.04}

# C-04: design in parameters that no assignment rule can produce
ghost_design:
  match: {family: deferral_based, cap_percent: 0.04, tiers: [...]}

# C-03/C-08: core family without its schedule
new_hires:
  employer_core: {family: age_banded, contribution_rate: 0.02}

# C-08: unknown core family
new_hires:
  employer_core: {family: integrated_flat, contribution_rate: 0.02}

# C-13: explicit integration level with no value
new_hires:
  employer_core:
    family: flat
    contribution_rate: 0.02
    integration_enabled: true
    integration_level_mode: explicit    # integration_level_value missing
```

## Migration of run-global core settings

`employer_core_status`, `employer_core_age_schedule`, `employer_core_points_schedule`, and the four
`employer_core_integration_*` vars remain accepted at the top level and act as the default for every
design that does not override them (C-09). This keeps every pre-existing configuration working
unchanged, which is what SC-001 measures. The per-design values win where both are present.
