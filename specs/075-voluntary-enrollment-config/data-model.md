# Data Model: Voluntary Enrollment Rate Configuration

**Feature**: 075-voluntary-enrollment-config
**Date**: 2026-03-18

## Entities

### VoluntaryEnrollmentRate (New Field on Existing Entity)

Added to `AutoEnrollmentSettings` (Pydantic BaseModel):

| Field | Type | Constraints | Default | Description |
|-------|------|-------------|---------|-------------|
| `voluntary_enrollment_rate` | `Optional[float]` | `ge=0, le=1` | `None` | Multiplier applied to demographic enrollment probabilities. 0.0 = no voluntary enrollment, 1.0 = full demographic rates, None = use defaults (equivalent to 1.0) |

### Enrollment Probability (Modified Calculation)

| Field | Source | Description |
|-------|--------|-------------|
| `base_enrollment_rate` | Age segment lookup | 0.30 (young), 0.55 (mid), 0.70 (mature), 0.80 (senior) |
| `income_multiplier` | Income segment lookup | 0.70–1.25 range |
| `job_level_multiplier` | Job level lookup | 0.90–1.20 range |
| `voluntary_enrollment_rate` | **NEW** - dbt variable | 0.0–1.0 multiplier from config |
| `final_enrollment_probability` | Calculated | `base × income × job_level × voluntary_rate` |

### Scenario Configuration (Existing - No Schema Change)

The `config_overrides.dc_plan` section in `scenario.json` gains:

| Field | Type | API Key | Description |
|-------|------|---------|-------------|
| Voluntary Enrollment Rate | number (0–1) | `voluntary_enrollment_rate` | Stored as decimal in config_overrides |

## State Transitions

```
None (not configured)
  → User sets rate (0.0–1.0) via UI
  → Persisted in scenario config_overrides
  → Exported as dbt variable
  → Applied as multiplier in enrollment SQL models

Rate cleared/removed
  → Reverts to None
  → COALESCE defaults to 1.0
  → Original demographic rates apply unchanged
```

## Validation Rules

1. Value must be between 0.0 and 1.0 inclusive (enforced by Pydantic `ge=0, le=1`)
2. Value is optional — `None` means "use default behavior"
3. UI presents as percentage (0–100%) and converts to decimal for storage
4. Independent of `auto_enrollment_enabled` flag — no cross-field validation needed
