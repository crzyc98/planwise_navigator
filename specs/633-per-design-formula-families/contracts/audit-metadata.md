# Contract: Per-Design Formula Family Audit Metadata

## Persistence target

The existing append-only DuckDB `run_metadata` relation gains one additive nullable `VARCHAR` column:

`design_formula_families_json`

No table, row-grain, archive-format, or public mart change is introduced. Historical rows remain
valid with `NULL`; each new simulation, batch, or calibration record populates the field.

## Canonical value

The value is compact JSON with design IDs ordered lexicographically. Each design has exactly two
keys, also serialized in stable order:

```json
{"legacy":{"core_family":"flat","match_family":"deferral_based"},"new_hires":{"core_family":"age_banded","match_family":"tenure_graded"}}
```

- Family values are the normalized effective values; `tenure_based` is recorded as
  `tenure_graded`.
- If a design inherits a run-global family because the per-design field was omitted, the inherited
  effective value is recorded.
- The design set exactly matches `SimulationConfig.get_plan_design_set()`.
- Changing either family continues to change `config_fingerprint` because the effective per-design
  payload remains part of the exported configuration.

## Compatibility and validation

- Schema evolution uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, consistent with existing
  `run_metadata` evolution.
- Existing records are never updated or backfilled.
- Tests assert canonical ordering, normalized aliases, inherited single-design defaults, exact design
  coverage, append-only retention, and fingerprint sensitivity.
