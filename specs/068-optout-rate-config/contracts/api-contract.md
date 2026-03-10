# API Contract: Opt-Out Rate Configuration

**Branch**: `068-optout-rate-config` | **Date**: 2026-03-10

## Config Defaults Endpoint (Extended)

### GET /api/config/defaults

**Response** (extended enrollment section):

```json
{
  "enrollment": {
    "auto_enrollment": {
      "enabled": true,
      "default_deferral_rate": 0.06,
      "opt_out_rates": {
        "by_age": {
          "young": 0.35,
          "mid_career": 0.20,
          "mature": 0.15,
          "senior": 0.10
        },
        "by_income": {
          "low_income": 0.40,
          "moderate": 0.25,
          "high": 0.15,
          "executive": 0.05
        }
      }
    }
  }
}
```

## Scenario Configuration Payload (Extended)

### POST/PUT /api/workspaces/{id}/scenarios/{id}

**Request body** (`config_overrides.dc_plan` section, new fields only):

```json
{
  "config_overrides": {
    "dc_plan": {
      "opt_out_rate_young": 0.35,
      "opt_out_rate_mid": 0.20,
      "opt_out_rate_mature": 0.15,
      "opt_out_rate_senior": 0.10,
      "opt_out_rate_low_income": 0.40,
      "opt_out_rate_moderate": 0.25,
      "opt_out_rate_high": 0.15,
      "opt_out_rate_executive": 0.05
    }
  }
}
```

**Rules**:
- All values are decimals in range [0.00, 1.00]
- Omitted fields use defaults
- Null values treated as "use default"

## dbt Variable Contract

The orchestrator passes these variables to dbt:

| dbt Variable | Source Field | Type |
|-------------|-------------|------|
| `opt_out_rate_young` | `dc_plan.opt_out_rate_young` | float |
| `opt_out_rate_mid` | `dc_plan.opt_out_rate_mid` | float |
| `opt_out_rate_mature` | `dc_plan.opt_out_rate_mature` | float |
| `opt_out_rate_senior` | `dc_plan.opt_out_rate_senior` | float |
| `opt_out_rate_low_income` | `dc_plan.opt_out_rate_low_income` | float |
| `opt_out_rate_moderate` | `dc_plan.opt_out_rate_moderate` | float |
| `opt_out_rate_high` | `dc_plan.opt_out_rate_high` | float |
| `opt_out_rate_executive` | `dc_plan.opt_out_rate_executive` | float |
