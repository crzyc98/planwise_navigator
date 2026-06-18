# Contract: Pydantic Configuration Schema

This is the configuration contract between the Studio UI / workspace API and the simulation config loader (`planalign_orchestrator/config/`). It supersedes the `tenure_match_tiers` contract for the `tenure_based` mode.

## `employer_match.employer_match_status`

Add `'tenure_graded'` as a valid value alongside the existing `'deferral_based'`, `'graded_by_service'`, `'tenure_based'`, `'points_based'`.

> Note: `'tenure_based'` remains a recognized value only for reading pre-existing saved configs during a migration window; new configurations should use `'tenure_graded'`. (Migration mechanics are a tasks-phase concern, not specified further here.)

## `employer_match.tenure_graded_bands`

```jsonc
[
  {
    "min_years": 0,
    "max_years": 10,
    "tiers": [
      { "employee_min": 0.00, "employee_max": 0.02, "match_rate": 1.00 },
      { "employee_min": 0.02, "employee_max": 0.08, "match_rate": 0.50 }
    ]
  },
  {
    "min_years": 10,
    "max_years": null,
    "tiers": [
      { "employee_min": 0.00, "employee_max": 0.02, "match_rate": 1.00 },
      { "employee_min": 0.02, "employee_max": 0.10, "match_rate": 0.50 }
    ]
  }
]
```

### Validation contract (enforced by Pydantic `model_validator`, raises `ValueError` on violation)

1. Required, non-empty when `employer_match_status == 'tenure_graded'`.
2. Each band's `tiers` list is required and non-empty.
3. Each band's `tiers` list must start at `employee_min = 0.00` and be contiguous (no gap, no overlap) up to its highest `employee_max`.
4. Across the band list, `min_years` must start at 0 and be contiguous (no gap, no overlap); exactly one band may have `max_years = null` (the unbounded top band).
5. No upper limit on number of bands or tiers per band.

### Backward-compatibility contract

Any previously-saved single-tier `TenureMatchTier` entry (`{min_years, max_years, match_rate, max_deferral_pct}`) is representable as:

```jsonc
{
  "min_years": <min_years>,
  "max_years": <max_years>,
  "tiers": [
    { "employee_min": 0.00, "employee_max": <max_deferral_pct / 100>, "match_rate": <match_rate / 100> }
  ]
}
```

## Output contract: dbt vars (`_export_employer_match_vars`)

```jsonc
{
  "employer_match_status": "tenure_graded",
  "tenure_graded_bands": [
    {
      "min_years": 0,
      "max_years": 10,
      "tiers": [
        { "employee_min": 0.00, "employee_max": 0.02, "match_rate": 1.00 },
        { "employee_min": 0.02, "employee_max": 0.08, "match_rate": 0.50 }
      ]
    },
    {
      "min_years": 10,
      "max_years": null,
      "tiers": [
        { "employee_min": 0.00, "employee_max": 0.02, "match_rate": 1.00 },
        { "employee_min": 0.02, "employee_max": 0.10, "match_rate": 0.50 }
      ]
    }
  ]
}
```

Decimal convention note: unlike the existing `tenure_match_tiers` export (which keeps `rate`/`max_deferral_pct` as whole-number percentages, e.g. `50`, and divides by 100 inside the SQL macro), `tenure_graded_bands` tiers are exported already in decimal form (`0.50`, `0.02`) to match the convention already used by the existing `match_tiers` var consumed by `deferral_based` mode. This keeps the new macro consistent with the pattern it most closely extends.

## Contract: dbt macro `get_tenure_graded_match_tiers(tenure_graded_bands)`

**Input**: the `tenure_graded_bands` var (list of band dicts as above).

**Output**: SQL fragment producing a row set with columns `band_min_years, band_max_years, employee_min, employee_max, match_rate` — one row per tier across all bands — suitable for use inside `CROSS JOIN (...) AS tier`.

**Consumer-side join contract**: callers MUST additionally filter `WHERE ec.years_of_service >= tier.band_min_years AND (tier.band_max_years IS NULL OR ec.years_of_service < tier.band_max_years)` before aggregating, so each employee is scored only against their own band's tiers.

## Contract: `fct_employer_match_events` (no schema change)

The new mode populates the existing columns with `formula_type = 'tenure_graded'`; no new columns are added to the fact table. Downstream cost reporting/scenario comparison consumers require no changes (satisfies SC-004).
