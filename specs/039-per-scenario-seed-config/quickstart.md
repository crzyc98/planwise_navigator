# Quickstart: Per-Scenario Seed Configuration

**Branch**: `039-per-scenario-seed-config` | **Date**: 2026-02-09

## What This Feature Does

Makes promotion hazard rates and age/tenure band definitions configurable per-scenario instead of globally shared. Unifies all config saves into a single button.

## Key Changes Summary

### Backend (4 areas)

1. **Validation layer** (`planalign_api/services/`): Add Pydantic validators for promotion hazard and band configs that can validate these sections as part of the unified scenario update.

2. **Merged config resolution** (`planalign_api/storage/workspace_storage.py`): Extend `get_merged_config()` to fall back to global CSV values when `promotion_hazard` / `age_bands` / `tenure_bands` are absent from both scenario overrides and workspace base config.

3. **Orchestrator seed injection** (`planalign_orchestrator/pipeline_orchestrator.py`): Before `dbt seed`, read merged config and write scenario-specific CSV files to `dbt/seeds/`. Restore global defaults after simulation completes (or on error).

4. **API endpoint cleanup** (`planalign_api/routers/`): Remove PUT endpoints for promotion hazard and bands (saves now go through unified scenario/workspace update). Keep GET endpoints for reading global defaults.

### Frontend (3 areas)

1. **Unified form state** (`ConfigStudio.tsx`): Move promotion hazard and band config into `formData` so they participate in dirty tracking and the single save flow.

2. **Remove separate save buttons**: Delete "Save Band Configurations" and "Save Promotion Hazard" buttons. All saves go through the main "Save Changes" button.

3. **Copy from Scenario**: Extend the copy handler to include `promotion_hazard`, `age_bands`, and `tenure_bands` from the source scenario's config_overrides.

## File Impact Map

```
planalign_api/
  storage/workspace_storage.py     — MODIFY (merged config fallback to CSVs)
  routers/promotion_hazard.py      — MODIFY (remove PUT, keep GET)
  routers/bands.py                 — MODIFY (remove PUT, keep GET)
  routers/scenarios.py             — MODIFY (add seed config validation to update)
  services/promotion_hazard_service.py — MODIFY (add read-from-config method)
  services/band_service.py         — MODIFY (add read-from-config method)
  models/promotion_hazard.py       — KEEP (models reused for validation)

planalign_orchestrator/
  pipeline_orchestrator.py         — MODIFY (seed injection before dbt seed)

planalign_studio/
  components/ConfigStudio.tsx      — MODIFY (unified state, remove separate saves)
  services/api.ts                  — MODIFY (remove save functions, keep reads)

dbt/seeds/                         — NO CHANGE (files still exist as global defaults,
                                     overwritten per-simulation by orchestrator)
```

## Testing Strategy

1. **Unit tests**: Validation logic for promotion hazard and band configs
2. **Integration tests**: Merged config resolution (scenario → workspace → global CSV fallback)
3. **Integration tests**: Orchestrator seed injection (writes correct CSVs from merged config)
4. **E2E smoke test**: Save config with seed overrides → run simulation → verify scenario-specific values used
