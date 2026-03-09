# Data Model: Fix Target Compensation Growth Persistence

**Feature**: 064-fix-comp-growth-persist
**Date**: 2026-03-09

## Entities

### FormData (Frontend — TypeScript)

**File**: `planalign_studio/components/config/types.ts`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `targetCompensationGrowth` | `number` | `5.0` | Target total compensation growth percentage (e.g., 7.5 = 7.5%) |

**New field** added to existing `FormData` interface alongside other compensation fields (`meritBudget`, `colaRate`, `promoIncrease`, etc.).

### Compensation Payload (API — JSON)

**File**: `planalign_studio/components/config/buildConfigPayload.ts`

```json
{
  "compensation": {
    "merit_budget_percent": 3.5,
    "cola_rate_percent": 2.0,
    "promotion_increase_percent": 12.5,
    "promotion_distribution_range_percent": 5.0,
    "promotion_budget_percent": 1.5,
    "promotion_rate_multiplier": 1.0,
    "target_compensation_growth_percent": 5.0
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_compensation_growth_percent` | `number` | `5.0` | Target compensation growth as percentage |

### Scenario Config Overrides (Backend — Python)

**File**: `planalign_api/models/scenario.py`

Stored within `config_overrides: Dict[str, Any]` under `compensation.target_compensation_growth_percent`. No schema change required (flexible dict). Optional: add to `ScenarioConfig` Pydantic model for documentation.

## Relationships

```
FormData.targetCompensationGrowth (frontend state)
    ↓ buildConfigPayload()
compensation.target_compensation_growth_percent (API payload)
    ↓ POST /api/scenarios/{id}
config_overrides.compensation.target_compensation_growth_percent (storage)
    ↓ GET /api/scenarios/{id}
cfg.compensation.target_compensation_growth_percent (hydration)
    ↓ ConfigContext useEffect
FormData.targetCompensationGrowth (frontend state restored)
```

## State Transitions

```
[Component Mount]
  → FormData.targetCompensationGrowth = DEFAULT (5.0)
  → If scenario loaded: override from cfg.compensation.target_compensation_growth_percent

[User Adjusts Slider]
  → FormData.targetCompensationGrowth = new value
  → Dirty tracking marks "compensation" section as changed

[User Clicks "Calculate Settings"]
  → Solver reads FormData.targetCompensationGrowth
  → Derives and sets meritBudget, colaRate, promoIncrease

[User Clicks "Save"]
  → buildConfigPayload includes target_compensation_growth_percent
  → API stores in config_overrides

[User Returns to Page]
  → ConfigContext hydrates FormData.targetCompensationGrowth from saved value
  → Slider displays persisted value
```

## Validation Rules

| Rule | Description |
|------|-------------|
| Type | Must be a number |
| Range | Implicitly bounded by slider min/max (UI enforced) |
| Default | 5.0 when field is missing (backward compatibility) |
| Null handling | `cfg.compensation?.target_compensation_growth_percent ?? 5.0` |
