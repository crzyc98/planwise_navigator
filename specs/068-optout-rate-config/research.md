# Research: Configurable Auto-Enrollment Opt-Out Rates

**Branch**: `068-optout-rate-config` | **Date**: 2026-03-10

## Research Tasks

### R1: Current Opt-Out Rate Data Flow

**Decision**: The data flow has two independent paths that must be unified.

**Findings**:
1. **Legacy path** (`_export_enrollment_vars`, lines 74-110 of `export.py`): Reads opt-out rates from `SimulationConfig.enrollment.auto_enrollment.opt_out_rates` Pydantic model. Age rates are absolute (0.10, 0.07, 0.05, 0.03). Income rates are **multipliers** (1.20, 1.00, 0.70, 0.50) applied as `base_rate * multiplier`.

2. **E095 UI path** (`_export_enrollment_vars`, lines 131-199 of `export.py`): Reads from `dc_plan` dict sent by PlanAlign Studio. Currently handles auto_enroll, deferral, scope, window, grace period, escalation — but **does NOT handle opt-out rates**.

3. **dbt layer** (`int_enrollment_events.sql`, lines 379-460): Consumes absolute opt-out rates via `{{ var('opt_out_rate_*') }}`. Income rates in SQL are used as ratios (`income_rate / moderate_rate`), meaning the dbt layer effectively treats them as multipliers too.

**Rationale**: The E095 dc_plan path is the correct integration point. Adding opt-out rate fields to `dc_plan` dict follows the established pattern exactly.

### R2: Income Rate Representation (Multipliers vs Absolute)

**Decision**: The UI will display **absolute percentage rates** (e.g., 40% for low income), not multipliers. The orchestrator will convert.

**Rationale**:
- The GitHub issue (#201) describes absolute rates: "opt_out_rate_low_income: 0.40 (< $30k)"
- Analysts think in terms of "40% of low-income workers opt out", not "1.2x multiplier"
- The `dbt_project.yml` defaults use absolute rates (0.40, 0.25, 0.15, 0.05)
- The orchestrator already does `base_rate * multiplier` conversion; we just need the reverse

**Alternatives considered**:
- Multiplier UI: Rejected because it's confusing for analysts
- Separate multiplier + base rate UI: Rejected as unnecessarily complex

### R3: Default Value Discrepancy

**Decision**: Use the `dbt_project.yml` defaults (higher rates) as the UI defaults, since they match the issue description and represent the "hardcoded" values analysts see today.

**Findings**:
- `dbt_project.yml` defaults: young=0.35, mid=0.20, mature=0.15, senior=0.10
- `simulation_config.yaml` defaults: young=0.10, mid=0.07, mature=0.05, senior=0.03
- `workforce.py` Pydantic defaults: young=0.10, mid=0.07, mature=0.05, senior=0.03

**Rationale**: The `dbt_project.yml` values are what actually get used when no config override is provided. The `simulation_config.yaml` values are lower but get overridden by dbt_project.yml fallbacks if not passed through. The issue explicitly lists the dbt_project.yml values as "current hardcoded defaults."

**Resolution**: UI defaults should match `dbt_project.yml` values. The orchestrator export must always pass these values to dbt to ensure UI values take precedence over dbt_project.yml fallbacks.

### R4: Frontend Pattern for New Config Fields

**Decision**: Follow the exact pattern used by existing auto-enrollment fields (window, grace period, scope, cutoff).

**Findings** (from `DCPlanSection.tsx`, `types.ts`, `constants.ts`, `buildConfigPayload.ts`):
1. **types.ts**: Add `dcOptOutRate*` fields to `FormData` interface (camelCase)
2. **constants.ts**: Add defaults to `DEFAULT_FORM_DATA`
3. **DCPlanSection.tsx**: Add collapsible section with input fields grouped by "By Age" and "By Income"
4. **buildConfigPayload.ts**: Map to `dc_plan.opt_out_rate_*` keys, converting percentage to decimal (divide by 100)

**Pattern**: UI sends percentages (e.g., 35.0 for 35%), `buildConfigPayload` converts to decimals (0.35).

### R5: Orchestrator Export Pattern

**Decision**: Add opt-out rate handling to the E095 dc_plan section of `_export_enrollment_vars()`, following the same `if dc_plan_dict.get("key") is not None` guard pattern.

**Findings**: The function at lines 131-199 of `export.py` already processes 10+ dc_plan fields with a consistent pattern:
```python
if dc_plan_dict.get("field_name") is not None:
    dbt_vars["dbt_var_name"] = type_cast(dc_plan_dict["field_name"])
```

For opt-out rates, the UI will send absolute rates as decimals (already divided by 100 in buildConfigPayload). The orchestrator maps directly to dbt vars.
