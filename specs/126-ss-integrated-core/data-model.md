# Phase 1 Data Model: Social Security Integrated Employer Core Contribution

**Feature**: `126-ss-integrated-core` | **Date**: 2026-07-30

---

## 1. Statutory limits seed — `dbt/seeds/config_irs_limits.csv`

One column added to the existing year-indexed limits table.

| Column | Type | Notes |
|---|---|---|
| `social_security_wage_base` | `integer` | Social Security taxable wage base for `limit_year`, in whole dollars |

- Published anchors: **2024 = 168600**, **2025 = 176100**. The 2026 value is taken from the SSA announcement at implementation time (FR-002); see research R6 for why the neighbouring 2026 cells are not a usable precedent.
- Rows already flagged `is_estimated = true` (2027+) carry a projected value using a constant annual dollar increment, matching the form of the other estimated columns (FR-003). The flag is unchanged by this feature.
- Type declared in `dbt/seeds/schema.yml` and `dbt/dbt_project.yml` (research R5 — convention, not load-bearing).

**Consumed by**: the existing `irs_compensation_limits` CTE in `int_employer_core_contributions.sql`, which already reads this seed for `compensation_limit`. The new column joins on the same row; no new join is introduced.

---

## 2. Configuration — `employer_core_contribution.integration`

A new group beside `status`, `contribution_rate`, and the schedules. It does **not** replace or interact with them (FR-005); it reads the base rate they resolved.

```yaml
employer_core_contribution:
  enabled: true
  status: 'flat'              # unchanged — resolves the BASE rate
  contribution_rate: 0.03
  integration:
    enabled: false            # default off (FR-006); off ⇒ byte-identical output (FR-007)
    level_mode: 'ss_wage_base'  # ss_wage_base | percent_of_ss_wage_base | fixed_dollar
    level_value: null         # percentage (0-100] or dollars (>0); required by the latter two modes
    disparity_rate: 0.0       # additional rate on excess compensation
```

### `CoreIntegrationSettings` (Pydantic v2, `planalign_orchestrator/config/workforce.py`)

Modelled on the existing `AgeCoreTier` in the same module.

| Field | Type | Constraints |
|---|---|---|
| `enabled` | `bool` | default `False` |
| `level_mode` | `Literal["ss_wage_base", "percent_of_ss_wage_base", "fixed_dollar"]` | default `"ss_wage_base"` |
| `level_value` | `Optional[float]` | `> 0`; **required** when `level_mode != "ss_wage_base"`; for `percent_of_ss_wage_base` additionally `<= 100`; must be `None` or ignored for `ss_wage_base` |
| `disparity_rate` | `float` | `>= 0`; decimal fraction (0.027 = 2.7%) |

**Model-level rules** (`@model_validator(mode="after")`, structural only — no year data needed):
- `level_mode != "ss_wage_base"` and `level_value is None` → error naming the mode.
- `enabled` and `disparity_rate == 0` → **allowed**, produces no disparity (spec edge case), not an error.
- `not enabled` → all other fields unvalidated beyond type; a disabled group never blocks a run.

### `validate_core_integration(core_config, start_year, end_year)` — §401(l) enforcement

Invoked from the existing `SimulationConfig.validate_core_age_schedules` validator in `config/loader.py`, which is renamed to reflect that it now covers both schedules and integration. Runs for **both** config shapes:
- direct YAML: `employer_core_contribution.integration`
- Studio: `dc_plan.core_integration_*` (see contracts)

Returns `None`; raises `ValueError` with the message contract in `contracts/configuration-and-ui.md`.

**Algorithm** (per FR-012/FR-013, research R2/R3/R8):

```
if not enabled: return
base_rate = min_schedule_rate(core_config)          # research R8
for year in start_year..end_year:
    wage_base = wage_base_for(year)                 # read from seed CSV, research R2
    level     = resolve_level(level_mode, level_value, wage_base)   # research R7
    factor    = permitted_disparity_factor(level, wage_base)
    limit     = min(base_rate, factor)
    if disparity_rate > limit: raise ValueError(<message contract>)  # names year, limit, bound constraint
```

### `resolve_level(mode, value, wage_base) -> int`

| Mode | Level |
|---|---|
| `ss_wage_base` | `wage_base` |
| `percent_of_ss_wage_base` | `round_half_up(wage_base * value / 100)` — whole dollars (research R7) |
| `fixed_dollar` | `round_half_up(value)` |

The identical rule is implemented in SQL (§4) so the validated level and the administered level cannot diverge.

### `permitted_disparity_factor(level, wage_base) -> float`

Pure function of two numbers; the sole home of the §401(l) safe-harbor table (FR-013). Isolating it means a correction to the table touches one function and its table-driven tests.

| Condition on `level` | Factor |
|---|---|
| `level > wage_base` | **not permitted** — raises, naming the wage base |
| `level == wage_base` | `0.057` |
| `0.8 * wage_base < level < wage_base` | `0.054` |
| `max(0.2 * wage_base, 10000) < level <= 0.8 * wage_base` | `0.043` |
| `level <= max(0.2 * wage_base, 10000)` | `0.057` |

Boundary conventions, each pinned by a unit test (SC-006):
- At exactly `wage_base` → 5.7% (not the 5.4% band).
- At exactly `0.8 * wage_base` → 4.3% (upper bound of the 4.3% band is inclusive).
- At exactly `max(0.2 * wage_base, 10000)` → 5.7% (the floor band is inclusive).
- The `$10,000` term is a floor on the 20% threshold, so for a wage base below $50,000 the floor dominates. Not reachable with real wage bases; tested with a synthetic value to pin the `max()`.

---

## 3. dbt variable contract

Exported by `_export_core_contribution_vars` (and the parallel `dc_plan` path) in `planalign_orchestrator/config/export.py`. Flat vars, matching the existing `employer_core_*` convention.

| dbt var | Type | Default when absent |
|---|---|---|
| `employer_core_integration_enabled` | boolean | `false` |
| `employer_core_integration_level_mode` | string | `'ss_wage_base'` |
| `employer_core_integration_level_value` | float / null | `null` |
| `employer_core_integration_disparity_rate` | float | `0.0` |

Rates cross this boundary as **decimal fractions**, unlike the tier schedules, which `_transform_age_tiers` converts to percentages for the macros. This is deliberate: `employer_core_contribution_rate` is already exported as a decimal fraction, and the disparity rate is its peer, not a tier field.

---

## 4. Model output — `int_employer_core_contributions`

Five columns added to the existing table materialization. No other model changes; nothing new propagates to `fct_workforce_snapshot` or `fct_yearly_events`.

| Column | Type | Meaning |
|---|---|---|
| `ss_wage_base` | `integer` | Taxable wage base for the simulation year, as read from the seed |
| `integration_level_applied` | `integer` | The resolved level, or `NULL` when integration is disabled |
| `excess_compensation` | `decimal` | `GREATEST(0, recognized_comp - integration_level)`; `0` when disabled |
| `base_core_amount` | `decimal` | `ROUND(base_rate * recognized_comp, 2)` |
| `disparity_core_amount` | `decimal` | `ROUND(disparity_rate * excess_compensation, 2)`; `0` when disabled |

These follow the established `irs_401a17_limit` / `irs_401a17_limit_applied` pattern — the value used, alongside the evidence of whether it bound. `integration_level_applied` is `NULL` rather than `0` when disabled so that "no integration" is distinguishable from "a level of zero".

### Computation order (the three pinned decisions)

```
recognized_comp   = LEAST(prorated_annual_compensation, irs_401a17_limit)   -- cap FIRST (FR-009)
excess_comp       = GREATEST(0, recognized_comp - integration_level)        -- level NOT prorated (FR-010)
base_core_amount  = ROUND(base_rate * recognized_comp, 2)
disparity_amount  = ROUND(disparity_rate * excess_comp, 2)
employer_core_amount = base_core_amount + disparity_amount                  -- exact sum (FR-018)
```

- **FR-009**: the cap is applied inside `recognized_comp`, which is the input to the subtraction. The existing model already computes `LEAST(comp, irs_401a17_limit)` inline in the amount expression; the integration CTE lifts that into a named column so the ordering is visible rather than implied.
- **FR-010**: `integration_level` is derived from `ss_wage_base` and the config alone. It is **not** passed through the mid-year proration at `int_employer_core_contributions.sql:~103-128`, which prorates only compensation. A mid-year hire compares partial-year pay against the full-year level and therefore may receive no disparity.
- **FR-007**: when integration is disabled the Jinja emits today's single-`ROUND` expression verbatim and the five columns are constants (research R1).

### Invariants (assertable in SQL)

| Invariant | Source |
|---|---|
| `base_core_amount + disparity_core_amount = employer_core_amount` for every row | FR-018 / SC-004 |
| `excess_compensation = 0 ⟹ disparity_core_amount = 0` | SC-005 |
| `eligible_for_core = false ⟹ all three amounts = 0` | spec edge case |
| `excess_compensation <= recognized_comp` and `>= 0` | definitional |
| integration disabled ⟹ result set identical to pre-feature run | FR-007 / SC-002 |

---

## 5. Studio form state

Added to `FormData` in `planalign_studio/components/config/types.ts`, mirroring how `dcCoreAgeSchedule` was added by #522.

| Field | Type | Maps to `dc_plan` payload key |
|---|---|---|
| `dcCoreIntegrationEnabled` | `boolean` | `core_integration_enabled` |
| `dcCoreIntegrationLevelMode` | `CoreIntegrationLevelMode` | `core_integration_level_mode` |
| `dcCoreIntegrationLevelValue` | `number \| null` | `core_integration_level_value` (forced to `null` for `ss_wage_base`) |
| `dcCoreIntegrationDisparityRate` | `number` | `core_integration_disparity_rate` (÷100 in `buildConfigPayload`) |

The form carries the disparity rate as a **percentage** and divides by 100 on the way out, matching `core_contribution_rate_percent` and the tier editors. The engine only ever sees decimal fractions — see contract 2 on why both the validator and the exporter must normalize through one function.

**Placement**: the editor renders for *every* contribution type, after the four status-specific schedule editors and before core eligibility. That placement is the UI expression of FR-005 — integration modifies whichever base rate the schedule above resolved, so nesting it inside one status would misrepresent the design.
