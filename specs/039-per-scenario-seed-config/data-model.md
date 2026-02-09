# Data Model: Per-Scenario Seed Configuration

**Branch**: `039-per-scenario-seed-config` | **Date**: 2026-02-09

## Entity: Scenario Config Overrides (Extended)

The existing `config_overrides` dict stored in `scenario.json` is extended with three new top-level sections.

### New Sections in config_overrides

```yaml
# scenario.json → config_overrides (or base_config.yaml for workspace defaults)
# Existing sections unchanged: simulation, compensation, workforce, dc_plan, advanced, data_sources

promotion_hazard:
  base_rate: 0.02                    # float, 0.0–1.0
  level_dampener_factor: 0.15        # float, 0.0–1.0
  age_multipliers:                   # list, exactly one per age band
    - age_band: "< 25"
      multiplier: 1.6               # float, >= 0.0
    - age_band: "25-34"
      multiplier: 1.4
    - age_band: "35-44"
      multiplier: 1.1
    - age_band: "45-54"
      multiplier: 0.7
    - age_band: "55-64"
      multiplier: 0.3
    - age_band: "65+"
      multiplier: 0.1
  tenure_multipliers:                # list, exactly one per tenure band
    - tenure_band: "< 2"
      multiplier: 0.5
    - tenure_band: "2-4"
      multiplier: 1.5
    - tenure_band: "5-9"
      multiplier: 1.8
    - tenure_band: "10-19"
      multiplier: 0.8
    - tenure_band: "20+"
      multiplier: 0.2

age_bands:                           # list, ordered by min_value ascending
  - band_id: 1
    band_label: "< 25"
    min_value: 0                     # int, first band must start at 0
    max_value: 25                    # int, must be > min_value
    display_order: 1
  - band_id: 2
    band_label: "25-34"
    min_value: 25
    max_value: 35
    display_order: 2
  - band_id: 3
    band_label: "35-44"
    min_value: 35
    max_value: 45
    display_order: 3
  - band_id: 4
    band_label: "45-54"
    min_value: 45
    max_value: 55
    display_order: 4
  - band_id: 5
    band_label: "55-64"
    min_value: 55
    max_value: 65
    display_order: 5
  - band_id: 6
    band_label: "65+"
    min_value: 65
    max_value: 120
    display_order: 6

tenure_bands:                        # list, ordered by min_value ascending
  - band_id: 1
    band_label: "< 2"
    min_value: 0
    max_value: 2
    display_order: 1
  - band_id: 2
    band_label: "2-4"
    min_value: 2
    max_value: 5
    display_order: 2
  - band_id: 3
    band_label: "5-9"
    min_value: 5
    max_value: 10
    display_order: 3
  - band_id: 4
    band_label: "10-19"
    min_value: 10
    max_value: 20
    display_order: 4
  - band_id: 5
    band_label: "20+"
    min_value: 20
    max_value: 99
    display_order: 5
```

### Validation Rules

**Promotion Hazard**:
- `base_rate`: float, 0.0 <= value <= 1.0
- `level_dampener_factor`: float, 0.0 <= value <= 1.0
- `age_multipliers`: list of exactly N items (matching number of age bands), each multiplier >= 0.0
- `tenure_multipliers`: list of exactly M items (matching number of tenure bands), each multiplier >= 0.0
- Section-level replacement: if present, entire `promotion_hazard` block is used (no partial merge with defaults)

**Age Bands**:
- List of band objects, ordered by `min_value` ascending
- First band `min_value` must be 0
- Each band: `max_value` > `min_value`
- No gaps: band[i].max_value == band[i+1].min_value
- No overlaps: ranges are [min, max) exclusive
- Section-level replacement: if present, entire `age_bands` list replaces default

**Tenure Bands**:
- Same rules as age bands

### Merge Behavior

```
Priority (highest to lowest):
1. scenario.config_overrides.promotion_hazard  (if key present)
2. workspace.base_config.promotion_hazard      (if key present)
3. Global CSV files in dbt/seeds/              (always present as fallback)

Same priority chain for age_bands and tenure_bands.
Each section is independent — overriding promotion_hazard does not require overriding bands.
```

### State Transitions

```
[No override] → User edits in UI → [Override present in config_overrides]
                                          ↓
                                   User saves → persisted to scenario.json
                                          ↓
                               Simulation starts → orchestrator writes CSV
                                          ↓
                                   dbt seed loads CSV into DuckDB
```

## Entity: Seed CSV Files (Derived, Ephemeral)

At simulation time, the orchestrator writes scenario-specific CSV files to `dbt/seeds/` before running `dbt seed`. These are **derived** from the merged config, not a source of truth.

### Files Written

| File | Source Config Key | Columns |
|------|-------------------|---------|
| `config_promotion_hazard_base.csv` | `promotion_hazard.base_rate`, `promotion_hazard.level_dampener_factor` | `base_rate`, `level_dampener_factor` |
| `config_promotion_hazard_age_multipliers.csv` | `promotion_hazard.age_multipliers` | `age_band`, `multiplier` |
| `config_promotion_hazard_tenure_multipliers.csv` | `promotion_hazard.tenure_multipliers` | `tenure_band`, `multiplier` |
| `config_age_bands.csv` | `age_bands` | `band_id`, `band_label`, `min_value`, `max_value`, `display_order` |
| `config_tenure_bands.csv` | `tenure_bands` | `band_id`, `band_label`, `min_value`, `max_value`, `display_order` |

### Lifecycle

1. **Before simulation**: Orchestrator reads merged config → writes CSVs to `dbt/seeds/`
2. **During simulation**: `dbt seed` loads CSVs into DuckDB tables
3. **After simulation**: CSVs remain in `dbt/seeds/` (overwritten by next simulation)

CSV files in `dbt/seeds/` are now treated as **ephemeral working copies**, not the source of truth. The source of truth is the workspace/scenario config.
