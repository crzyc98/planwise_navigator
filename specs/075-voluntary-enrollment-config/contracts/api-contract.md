# API Contract: Voluntary Enrollment Rate

**Feature**: 075-voluntary-enrollment-config
**Date**: 2026-03-18

## Existing Endpoints (No New Endpoints Required)

### PUT /api/workspaces/{workspace_id}/scenarios/{scenario_id}

**Change**: `config_overrides.dc_plan` now accepts `voluntary_enrollment_rate`

**Request Body** (partial — only new field shown):
```json
{
  "config_overrides": {
    "dc_plan": {
      "voluntary_enrollment_rate": 0.40
    }
  }
}
```

**Validation**:
- Type: `number` (float)
- Range: `0.0` to `1.0` inclusive
- Optional: field can be omitted or set to `null` to use default behavior

**Response**: Standard `Scenario` response with updated `config_overrides`

### GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/config

**Change**: Merged config response includes `voluntary_enrollment_rate` when set

**Response** (partial — only new field shown):
```json
{
  "dc_plan": {
    "auto_enroll": true,
    "voluntary_enrollment_rate": 0.40
  }
}
```

When not configured, the field is absent from the response (not returned as `null`).

## dbt Variable Contract

### Variable: `voluntary_enrollment_rate`

| Property | Value |
|----------|-------|
| Name | `voluntary_enrollment_rate` |
| Type | float or null |
| Range | 0.0–1.0 |
| Default | `null` (in `dbt_project.yml`) |
| Behavior when null | `COALESCE(value, 1.0)` → no scaling applied |
| Consumed by | `int_voluntary_enrollment_decision.sql`, `int_proactive_voluntary_enrollment.sql` |
| Passed via | `dbt run --vars '{"voluntary_enrollment_rate": 0.40}'` |
