# Data Model: Configurable Auto-Enrollment Opt-Out Rates

**Branch**: `068-optout-rate-config` | **Date**: 2026-03-10

## Entities

### OptOutRateConfiguration

Represents the 8 demographic-segmented opt-out rates for a scenario.

| Field | Type | Range | Default | Description |
|-------|------|-------|---------|-------------|
| opt_out_rate_young | decimal | 0.00-1.00 | 0.35 | Ages 18-25 opt-out probability |
| opt_out_rate_mid | decimal | 0.00-1.00 | 0.20 | Ages 26-35 opt-out probability |
| opt_out_rate_mature | decimal | 0.00-1.00 | 0.15 | Ages 36-50 opt-out probability |
| opt_out_rate_senior | decimal | 0.00-1.00 | 0.10 | Ages 51+ opt-out probability |
| opt_out_rate_low_income | decimal | 0.00-1.00 | 0.40 | Income <$30k opt-out probability |
| opt_out_rate_moderate | decimal | 0.00-1.00 | 0.25 | Income $30k-$50k opt-out probability |
| opt_out_rate_high | decimal | 0.00-1.00 | 0.15 | Income $50k-$100k opt-out probability |
| opt_out_rate_executive | decimal | 0.00-1.00 | 0.05 | Income >$100k opt-out probability |

**Relationships**: Belongs to a Scenario Configuration (via `config_overrides.dc_plan`).

**State**: Immutable per simulation run. Changed only via UI save action before simulation.

### Scenario Configuration (extended)

Existing entity extended with opt-out rates nested under `dc_plan`.

```
config_overrides:
  dc_plan:
    auto_enroll: true
    default_deferral_percent: 6.0
    ...existing fields...
    opt_out_rate_young: 0.35        # NEW
    opt_out_rate_mid: 0.20          # NEW
    opt_out_rate_mature: 0.15       # NEW
    opt_out_rate_senior: 0.10       # NEW
    opt_out_rate_low_income: 0.40   # NEW
    opt_out_rate_moderate: 0.25     # NEW
    opt_out_rate_high: 0.15         # NEW
    opt_out_rate_executive: 0.05    # NEW
```

## Data Flow

```
UI (percentage, e.g., 35.0)
  → buildConfigPayload (decimal, e.g., 0.35)
    → API (dc_plan dict with decimal values)
      → Orchestrator export.py (maps to dbt vars)
        → dbt int_enrollment_events.sql (uses {{ var('opt_out_rate_*') }})
```

## Validation Rules

- All 8 rates must be between 0.00 and 1.00 inclusive
- Empty/null values fall back to defaults
- No inter-field dependencies (each rate is independent)
- Rates are stored as decimals internally, displayed as percentages in UI
