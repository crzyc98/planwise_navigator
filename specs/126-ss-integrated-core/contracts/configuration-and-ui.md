# Phase 1 Contracts: Configuration, Export, Validation, and UI

**Feature**: `126-ss-integrated-core` | **Date**: 2026-07-30

Four contracts. The first two are the surfaces a user configures; the third is the seam between them and dbt; the fourth is what a user sees when they get it wrong.

---

## Contract 1 — Direct YAML (`config/simulation_config.yaml`, scenario configs)

```yaml
employer_core_contribution:
  enabled: true
  status: 'flat'                        # unchanged: resolves the BASE rate
  contribution_rate: 0.03

  # NEW — permitted disparity (§401(l)) modifier. Composes with any status.
  integration:
    enabled: true
    level_mode: 'ss_wage_base'          # ss_wage_base | percent_of_ss_wage_base | fixed_dollar
    level_value: null                   # required unless level_mode is ss_wage_base
    disparity_rate: 0.027               # decimal fraction; 0.027 = 2.7%
```

**Guarantees**:
- Omitting the `integration` block entirely is identical to `integration: {enabled: false}`, which is identical to today's behaviour for every `status` (FR-007).
- The block is accepted under every `status` value with no per-status keys or branching (FR-011).
- `integration` never affects eligibility — only the amount an already-eligible employee receives (spec Assumption 4).

**Rejected at load** (`ValueError`, before any simulation work):
- `level_value` absent when `level_mode` requires it.
- `level_value <= 0`, or `> 100` under `percent_of_ss_wage_base`.
- `disparity_rate < 0`.
- `disparity_rate` exceeding the §401(l) limit in any simulated year — Contract 4.
- A level above the taxable wage base in any simulated year.

---

## Contract 2 — Studio (`dc_plan` payload)

The Studio writes flat `dc_plan` keys, which `to_dbt_vars` merges into the same engine vars.

| `dc_plan` key | Type | Notes |
|---|---|---|
| `core_integration_enabled` | boolean | default `false` |
| `core_integration_level_mode` | string | one of the three modes |
| `core_integration_level_value` | number \| null | percentage or dollars; `null` for `ss_wage_base` |
| `core_integration_disparity_rate` | number | **decimal fraction** — `buildConfigPayload` divides the form percentage by 100 |
| `core_integration_disparity_rate_percent` | number | accepted alternative; normalized to a decimal fraction |

**One normalizer, two callers.** `normalize_dc_plan_integration` in `permitted_disparity.py` is used by *both* config validation (`loader.py`) and dbt-var export (`export.py`). This is not tidiness — if validation read the decimal key while the UI wrote the percent key, an illegal 8% rate would read as `0.0` and pass. Pinned by `test_studio_percent_disparity_key_is_not_a_validation_bypass`.

**Both directions must work**, and each fails differently:
- *Validates but never exported* → the run succeeds and computes no integration at all. Pinned by `test_studio_dc_plan_integration_reaches_dbt_vars`.
- *Exported but never validated* → an illegal allocation runs and produces a cost figure. Pinned by the Studio half of `test_illegal_integration_is_rejected_for_direct_and_studio_shapes`.

#522's commit records a precedence bug where no Studio-configured design ever reached the NDT check — the reason both shapes carry explicit tests here.

---

## Contract 3 — dbt variables

| Var | Type | Default |
|---|---|---|
| `employer_core_integration_enabled` | boolean | `false` |
| `employer_core_integration_level_mode` | string | `'ss_wage_base'` |
| `employer_core_integration_level_value` | float \| null | `null` |
| `employer_core_integration_disparity_rate` | float | `0.0` |

**Guarantees**:
- All four have model-side defaults via `var('...', <default>)`, so `int_employer_core_contributions` compiles and runs unchanged against a config that predates this feature.
- Rates cross as decimal fractions (unlike tier schedules, which the `_transform_*` helpers convert to percentages for the macros).
- The vars participate in the config fingerprint the same way the existing `employer_core_*` vars do, so changing an integration setting registers as config drift (Feature 109) rather than silently reusing a stale database.

---

## Contract 4 — Validation error messages

FR-014 requires the message to name the applicable limit, the configured rate, and **which constraint bound**, so a user can fix the configuration without opening the regulation. This is a contract because SC-006 tests assert on its content.

**Shape**:

```
Employer core integration: disparity_rate {rate:.2%} exceeds the maximum permitted
under IRC §401(l) for simulation year {year}. The maximum is {limit:.2%}
(the lesser of the base contribution rate {base_rate:.2%} and the permitted
disparity factor {factor:.2%} for an integration level of ${level:,} against a
taxable wage base of ${wage_base:,}). Bound by: {"base rate" | "disparity factor"}.
```

**Worked examples** (matching the spec's Story 3 acceptance scenarios):

| Configuration | Message names |
|---|---|
| base 3%, disparity 8%, level = wage base | maximum **3.00%**, bound by **base rate** (factor is 5.70%) |
| base 8%, disparity 6%, level = wage base | maximum **5.70%**, bound by **disparity factor** |
| base 8%, disparity 5%, level = 50% of wage base | maximum **4.30%**, bound by **disparity factor** — the *reduced* factor, not 5.70% |
| level above the wage base | a distinct message naming the level and the wage base; the level itself is impermissible, so no factor is quoted |

**Guarantees**:
- Raised as `ValueError` from Pydantic validation, so it surfaces through the existing config-error path in both the CLI and the API — no new error type, no new handling.
- Never a warning, never a clamp (FR-015).
- Names the **first** violating year (research R3), so a multi-year `fixed_dollar` configuration reports the specific year rather than "some year".

---

## Contract 5 — Plan design description (FR-020)

`derivePlanSummary` (`ScenarioCostComparison.tsx:95`) builds `core` from `core_status` and falls through to `` `Flat ${core_contribution_rate_percent}% of eligible compensation.` `` at line 118. An integrated design therefore renders **identically to a flat one**, so the two scenarios being compared would carry the same label while showing different costs. That is the specific defect FR-020 exists to prevent, and it is the one Studio change in scope.

Integration appends a clause to whatever the status produced, which is what makes it a modifier rather than a fifth branch:

| Configuration | Rendered |
|---|---|
| flat 3%, integration off | `Flat 3% of eligible compensation.` *(unchanged — FR-007 extends to the prose)* |
| flat 3%, integrated at the wage base, 2.7% | `Flat 3% of eligible compensation, plus 2.7% above the Social Security wage base.` |
| graded, integrated at 80% of the wage base, 2% | `Graded by service, 1%–3% of eligible compensation, plus 2% above 80% of the Social Security wage base.` |
| flat 3%, integrated at $150,000, 2.7% | `Flat 3% of eligible compensation, plus 2.7% above $150,000.` |

**`PlanDesignModal`** — gains an integration block beside the existing schedule blocks, shown only when integration is enabled, listing the resolved integration level (via `formatIntegrationLevel`) and the disparity rate. It follows the layout of the `age_banded` block #522 added, and renders for **any** core status rather than being nested under one.

**Guarantee**: with integration disabled, both surfaces render byte-identically to today.
