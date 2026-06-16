# Contract: dbt Variable — `start_year`

**Feature**: `098-tenure-match-tier-bug`
**Date**: 2026-06-15

## Purpose

Defines the canonical dbt variable for the simulation start year and the alias that must also be
exported to maintain backward compatibility with models that use an alternate key name.

---

## Canonical Variable: `start_year`

| Property | Value |
|---|---|
| **Key** | `start_year` |
| **Type** | integer (Python) / Jinja2 integer |
| **Source** | `cfg.simulation.start_year` (Python `int`) |
| **Exported by** | `planalign_orchestrator/config/export.py` |
| **Consumed by** | All dbt models that need to branch on "is this Year 1?" |

**Export pattern** (export.py, canonical):
```python
dbt_vars["start_year"] = int(cfg.simulation.start_year)
```

**Consumption pattern** (dbt models, canonical):
```sql
{% set start_year = var('start_year', 2025) | int %}
{% if simulation_year == start_year %}
    -- Year 1 path: read from census/baseline
{% else %}
    -- Year 2+ path: read from prior-year snapshot
{% endif %}
```

---

## Alias Variable: `simulation_start_year`

Added in this feature to ensure backward compatibility with `int_workforce_snapshot_optimized` (and
any future model that uses the non-standard name).

| Property | Value |
|---|---|
| **Key** | `simulation_start_year` |
| **Value** | Identical to `start_year` |
| **Source** | `cfg.simulation.start_year` (same value) |
| **Exported by** | `planalign_orchestrator/config/export.py` |

**Export pattern** (export.py, alias):
```python
dbt_vars["simulation_start_year"] = int(cfg.simulation.start_year)
```

**Rule**: New dbt models MUST use `var('start_year', 2025)`. The alias exists only for legacy
compatibility and should not be used in new models.

---

## Invariants

1. Both `start_year` and `simulation_start_year` MUST carry the same integer value in every dbt
   invocation.
2. The default value of `2025` in `var('start_year', 2025)` is the fallback when running dbt
   directly (e.g., `dbt run --select some_model`) without the orchestrator. Models must remain
   functional with this default.
3. The value MUST equal `cfg.simulation.start_year` — the first year in the simulation range, not
   the current simulation year (`simulation_year`).
