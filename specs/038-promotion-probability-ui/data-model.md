# Data Model: Promotion Hazard Configuration UI

## Entity: PromotionHazardBase

Single-row configuration for global promotion parameters.

| Field | Type | Range | Display | Storage (CSV) |
|-------|------|-------|---------|---------------|
| `base_rate` | float | 0.00–1.00 | Percentage (0–100%) | Decimal |
| `level_dampener_factor` | float | 0.00–1.00 | Percentage (0–100%) | Decimal |

**Source**: `dbt/seeds/config_promotion_hazard_base.csv`

**Current values**:
```csv
base_rate,level_dampener_factor
0.02,0.15
```

## Entity: PromotionHazardAgeMultiplier

Per-age-band multiplier (6 rows).

| Field | Type | Range | Display | Editable |
|-------|------|-------|---------|----------|
| `age_band` | string | Band label | Read-only text | No |
| `multiplier` | float | >= 0 | Decimal (e.g., 1.6) | Yes |

**Source**: `dbt/seeds/config_promotion_hazard_age_multipliers.csv`

**Current values**:
| Age Band | Multiplier |
|----------|-----------|
| < 25 | 1.6 |
| 25-34 | 1.4 |
| 35-44 | 1.1 |
| 45-54 | 0.7 |
| 55-64 | 0.3 |
| 65+ | 0.1 |

## Entity: PromotionHazardTenureMultiplier

Per-tenure-band multiplier (5 rows).

| Field | Type | Range | Display | Editable |
|-------|------|-------|---------|----------|
| `tenure_band` | string | Band label | Read-only text | No |
| `multiplier` | float | >= 0 | Decimal (e.g., 1.5) | Yes |

**Source**: `dbt/seeds/config_promotion_hazard_tenure_multipliers.csv`

**Current values**:
| Tenure Band | Multiplier |
|-------------|-----------|
| < 2 | 0.5 |
| 2-4 | 1.5 |
| 5-9 | 1.8 |
| 10-19 | 0.8 |
| 20+ | 0.2 |

## Container: PromotionHazardConfig

Groups all three entities for API transport.

```
PromotionHazardConfig {
  base: PromotionHazardBase          // 1 object (2 fields)
  age_multipliers: AgeMultiplier[]   // 6 objects
  tenure_multipliers: TenureMultiplier[]  // 5 objects
}
```

## Conversion Rules

| Parameter | CSV Storage | UI Display | Conversion |
|-----------|-----------|------------|------------|
| base_rate | 0.02 | 2 (%) | display = stored * 100; save = display / 100 |
| level_dampener_factor | 0.15 | 15 (%) | display = stored * 100; save = display / 100 |
| age multiplier | 1.6 | 1.6 | No conversion (displayed as-is) |
| tenure multiplier | 0.5 | 0.5 | No conversion (displayed as-is) |

## Promotion Probability Formula

```
probability = base_rate * tenure_multiplier * age_multiplier * max(0, 1 - level_dampener * (level - 1))
```

Capped at 1.0. This formula is implemented in `dbt/models/dimensions/dim_promotion_hazards.sql`.
