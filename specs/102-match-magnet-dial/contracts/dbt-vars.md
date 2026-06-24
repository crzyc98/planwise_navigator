# Contract: dbt Variables (config ↔ SQL seam)

The dbt-var layer is the integration contract between the Python/UI config layer and the SQL models. All vars are emitted by `planalign_orchestrator/config/export.py` and read by the voluntary-enrollment models.

## Variables

| dbt var | Type | Default (`dbt_project.yml`) | Producer | Consumers |
|---------|------|------------------------------|----------|-----------|
| `enrollment_match_magnet_enabled` | bool | `true` | `_export_enrollment_vars` (config + dc_plan) | `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment` |
| `enrollment_match_magnet_probability` | float [0,1] | `0.45` | `_export_enrollment_vars` | same two models |
| `voluntary_max_deferral_rate` | float [0.01,1] | `0.10` (**NEW**) | `_export_enrollment_vars` | same two models (final bounds clamp) |
| `employer_match_max_deferral_rate` | float | computed from active formula (**NEW / always-on**) | `_export_employer_match_vars` | both voluntary models (deferral_based ceiling) |
| `employer_match_status` | str | `deferral_based` | `_export_employer_match_vars` | ceiling dispatch macro |
| `employer_match_graded_schedule` | list | `[]` | existing | graded/tenure ceiling macro |
| `points_match_tiers` | list | `[]` | existing | points ceiling macro |
| `deferral_match_response_match_max_rate` | float | (existing) | `_export_deferral_match_response_vars` | kept as backward-compatible alias; only when DMR enabled |

## Contract rules

1. **Always-on ceiling (FR-003)**: `employer_match_max_deferral_rate` MUST be exported whenever a match is configured, regardless of `deferral_match_response` enablement. SQL precedence for `deferral_based`: `employer_match_max_deferral_rate` → (legacy) `deferral_match_response_match_max_rate` → `max(employee_max over match_tiers)` → hard default.
2. **Backward compatibility**: When none of the new config/dc_plan keys are supplied, exported values equal the `dbt_project.yml` defaults above, reproducing current results (SC-004).
3. **Percent convention**: UI sends whole-number percents; export divides by 100 before emitting decimals (matches `voluntary_enrollment_rate`).
4. **Determinism**: vars are pure functions of scenario config; no runtime/random inputs (SC-005).

## Macro contract (SQL)

```text
resolve_match_magnet_ceiling(status, years_of_service_col, points_col, deferral_scalar) -> SQL expr (decimal)
  deferral_based      -> deferral_scalar
  graded_by_service   -> get_tiered_match_max_deferral(years_of_service_col, employer_match_graded_schedule, default)
  tenure_graded       -> get_tiered_match_max_deferral(years_of_service_col, employer_match_graded_schedule, default)
  points_based        -> <points max-deferral macro>(points_col, points_match_tiers, default)
  else / disabled     -> 0

apply_match_magnet(selected_rate, ceiling, snap_random, enabled, snap_prob, floor, cap) -> SQL expr (decimal)
  snapped = CASE WHEN enabled AND ceiling > 0 AND selected_rate < ceiling AND snap_random < snap_prob
                 THEN ceiling ELSE selected_rate END
  return GREATEST(floor, LEAST(cap, snapped))    -- cap = voluntary_max_deferral_rate, floor = 0.01
```

Both voluntary-enrollment models MUST call these macros (no inline duplicate logic).
