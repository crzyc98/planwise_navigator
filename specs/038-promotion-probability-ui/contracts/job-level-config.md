# API Contract: Job Level Configuration

## No New Endpoints

This feature does **not** add new API endpoints. It extends the existing workspace/scenario save payload with a new field.

## Modified Payload: `PUT /api/workspaces/{workspace_id}`

### Request Body (partial — `base_config.new_hire.job_level_compensation`)

**Before (current)**:
```json
{
  "base_config": {
    "new_hire": {
      "job_level_compensation": [
        {
          "level": 1,
          "name": "Staff",
          "min_compensation": 56000,
          "max_compensation": 80000
        }
      ]
    }
  }
}
```

**After (with promotion_probability)**:
```json
{
  "base_config": {
    "new_hire": {
      "job_level_compensation": [
        {
          "level": 1,
          "name": "Staff",
          "min_compensation": 56000,
          "max_compensation": 80000,
          "promotion_probability": 0.12
        }
      ]
    }
  }
}
```

### Backward Compatibility

- The `promotion_probability` field is **optional** in the API payload
- If absent, the frontend falls back to hardcoded defaults (matching CSV seed values)
- Existing saved workspaces without `promotion_probability` in their YAML continue to load correctly — the frontend load path uses `d.promotion_probability` with a fallback
- The YAML serializer (via `yaml.dump`) handles the new field automatically — no backend model changes required

## Modified Payload: `PUT /api/workspaces/{workspace_id}/scenarios/{scenario_id}`

Same structure as above, but under `config_overrides.new_hire.job_level_compensation`.

## Data Contract

| Field | Type | Required | Range | Default |
|-------|------|----------|-------|---------|
| `promotion_probability` | float | No | 0.00–1.00 | See defaults per level |

**Defaults by level**: L1=0.12, L2=0.08, L3=0.05, L4=0.02, L5=0.01
