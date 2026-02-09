# API Contracts: Per-Scenario Seed Configuration

**Branch**: `039-per-scenario-seed-config` | **Date**: 2026-02-09

## Modified Endpoints

### PUT /api/workspaces/{workspace_id}/scenarios/{scenario_id}

**Change**: `config_overrides` payload extended to accept `promotion_hazard`, `age_bands`, and `tenure_bands` sections.

**Request** (ScenarioUpdate — extended):
```json
{
  "name": "Aggressive Promotions",
  "description": "Higher promotion rates scenario",
  "config_overrides": {
    "simulation": { "start_year": 2025, "end_year": 2029 },
    "compensation": { "cola_rate": 0.02 },
    "promotion_hazard": {
      "base_rate": 0.25,
      "level_dampener_factor": 0.15,
      "age_multipliers": [
        { "age_band": "< 25", "multiplier": 1.6 },
        { "age_band": "25-34", "multiplier": 1.4 },
        { "age_band": "35-44", "multiplier": 1.1 },
        { "age_band": "45-54", "multiplier": 0.7 },
        { "age_band": "55-64", "multiplier": 0.3 },
        { "age_band": "65+", "multiplier": 0.1 }
      ],
      "tenure_multipliers": [
        { "tenure_band": "< 2", "multiplier": 0.5 },
        { "tenure_band": "2-4", "multiplier": 1.5 },
        { "tenure_band": "5-9", "multiplier": 1.8 },
        { "tenure_band": "10-19", "multiplier": 0.8 },
        { "tenure_band": "20+", "multiplier": 0.2 }
      ]
    },
    "age_bands": [
      { "band_id": 1, "band_label": "< 25", "min_value": 0, "max_value": 25, "display_order": 1 },
      { "band_id": 2, "band_label": "25-34", "min_value": 25, "max_value": 35, "display_order": 2 },
      { "band_id": 3, "band_label": "35-44", "min_value": 35, "max_value": 45, "display_order": 3 },
      { "band_id": 4, "band_label": "45-54", "min_value": 45, "max_value": 55, "display_order": 4 },
      { "band_id": 5, "band_label": "55-64", "min_value": 55, "max_value": 65, "display_order": 5 },
      { "band_id": 6, "band_label": "65+", "min_value": 65, "max_value": 120, "display_order": 6 }
    ],
    "tenure_bands": [
      { "band_id": 1, "band_label": "< 2", "min_value": 0, "max_value": 2, "display_order": 1 },
      { "band_id": 2, "band_label": "2-4", "min_value": 2, "max_value": 5, "display_order": 2 },
      { "band_id": 3, "band_label": "5-9", "min_value": 5, "max_value": 10, "display_order": 3 },
      { "band_id": 4, "band_label": "10-19", "min_value": 10, "max_value": 20, "display_order": 4 },
      { "band_id": 5, "band_label": "20+", "min_value": 20, "max_value": 99, "display_order": 5 }
    ]
  }
}
```

**Validation (atomic — all-or-nothing)**:
- If `promotion_hazard` present: validate base_rate (0-1), level_dampener (0-1), multiplier counts match band counts, multipliers >= 0
- If `age_bands` present: validate no gaps, no overlaps, first starts at 0, max > min
- If `tenure_bands` present: same as age_bands
- If any validation fails → 422 Unprocessable Entity, no changes persisted

**Response 200** (success):
```json
{
  "id": "scenario-123",
  "workspace_id": "ws-456",
  "name": "Aggressive Promotions",
  "config_overrides": { "...full overrides including seed configs..." },
  "status": "not_run"
}
```

**Response 422** (validation failure):
```json
{
  "detail": {
    "message": "Validation failed",
    "errors": [
      { "section": "promotion_hazard", "field": "base_rate", "message": "Must be between 0 and 1" },
      { "section": "age_bands", "field": "bands[2]", "message": "Gap detected: band 2 max (30) != band 3 min (35)" }
    ]
  }
}
```

---

### PUT /api/workspaces/{workspace_id}

**Change**: `base_config` payload extended identically. Used for workspace-level default seed configs.

**Request** (WorkspaceUpdate — extended):
```json
{
  "base_config": {
    "simulation": { "start_year": 2025 },
    "promotion_hazard": { "...same structure as above..." },
    "age_bands": [ "...same structure as above..." ],
    "tenure_bands": [ "...same structure as above..." ]
  }
}
```

**Validation**: Same rules as scenario update. Atomic.

---

### GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/config

**Change**: Merged config response now includes `promotion_hazard`, `age_bands`, and `tenure_bands` resolved through the merge chain.

**Response 200**:
```json
{
  "simulation": { "start_year": 2025, "end_year": 2029 },
  "compensation": { "cola_rate": 0.02 },
  "promotion_hazard": {
    "base_rate": 0.25,
    "level_dampener_factor": 0.15,
    "age_multipliers": [ "..." ],
    "tenure_multipliers": [ "..." ]
  },
  "age_bands": [ "..." ],
  "tenure_bands": [ "..." ]
}
```

**Merge resolution**:
1. If scenario `config_overrides` has `promotion_hazard` → use it (section-level replace)
2. Else if workspace `base_config` has `promotion_hazard` → use it
3. Else → read from global CSV files in `dbt/seeds/` and include in response

Same chain for `age_bands` and `tenure_bands`.

---

## Deprecated Endpoints

These endpoints become **read-only** (GET preserved for backward compatibility, PUT removed):

### GET /api/workspaces/{workspace_id}/config/promotion-hazards

**Preserved** as convenience read — returns current global CSV values. Useful for displaying "global defaults" in UI.

### ~~PUT /api/workspaces/{workspace_id}/config/promotion-hazards~~

**Removed**. Promotion hazard saves now go through the unified scenario/workspace update endpoints.

### GET /api/workspaces/{workspace_id}/config/bands

**Preserved** as convenience read — returns current global CSV values.

### ~~PUT /api/workspaces/{workspace_id}/config/bands~~

**Removed**. Band saves now go through the unified scenario/workspace update endpoints.

---

## Unchanged Endpoints

### POST /api/workspaces/{workspace_id}/analyze-age-bands
### POST /api/workspaces/{workspace_id}/analyze-tenure-bands

**No change**. Census analysis still returns suggested band boundaries. The frontend applies suggestions to the current scenario's form state (not global CSVs).

---

## Frontend API Client Changes

### api.ts — Modified Functions

```typescript
// updateScenario() — config_overrides payload now includes seed configs
// No signature change needed; config_overrides is already Dict[str, Any]
updateScenario(workspaceId, scenarioId, {
  config_overrides: {
    ...existingOverrides,
    promotion_hazard: { base_rate, level_dampener_factor, age_multipliers, tenure_multipliers },
    age_bands: [...],
    tenure_bands: [...],
  }
})

// updateWorkspace() — base_config payload now includes seed configs
// Same pattern as above
```

### api.ts — Removed Functions

```typescript
// savePromotionHazardConfig() — REMOVED (saves go through updateScenario/updateWorkspace)
// saveBandConfigs() — REMOVED (saves go through updateScenario/updateWorkspace)
```

### api.ts — Preserved Functions

```typescript
// getPromotionHazardConfig() — PRESERVED (reads global defaults for fallback display)
// getBandConfigs() — PRESERVED (reads global defaults for fallback display)
// analyzeAgeBands() — PRESERVED (unchanged)
// analyzeTenureBands() — PRESERVED (unchanged)
```
