# Quickstart: Promotion Hazard Configuration UI

## Prerequisites

- Python 3.11 with virtual environment activated (`source .venv/bin/activate`)
- Node.js and npm (for frontend)
- PlanAlign Studio running (`planalign studio`)

## Files to Create (Backend)

| File | Purpose |
|------|---------|
| `planalign_api/models/promotion_hazard.py` | Pydantic models (5 classes) |
| `planalign_api/services/promotion_hazard_service.py` | CSV read/write/validate service |
| `planalign_api/routers/promotion_hazard.py` | GET/PUT endpoints |

## Files to Modify

| File | What to Change |
|------|---------------|
| `planalign_api/routers/__init__.py` | Export `promotion_hazard_router` |
| `planalign_api/main.py` | Register promotion hazard router |
| `planalign_studio/services/api.ts` | Add TS interfaces + `getPromotionHazardConfig` / `savePromotionHazardConfig` functions |
| `planalign_studio/components/ConfigStudio.tsx` | Add state, load hook, handlers, save handler, UI section |

## Implementation Order

### Step 1: Backend Models (`promotion_hazard.py`)

Create Pydantic models: `PromotionHazardBase`, `PromotionHazardAgeMultiplier`, `PromotionHazardTenureMultiplier`, `PromotionHazardConfig`, `PromotionHazardSaveResponse`.

### Step 2: Backend Service (`promotion_hazard_service.py`)

Follow `band_service.py` pattern:
- `__init__(self, dbt_seeds_dir)` with default path to `dbt/seeds/`
- `read_base_config()` → reads `config_promotion_hazard_base.csv`
- `read_age_multipliers()` → reads `config_promotion_hazard_age_multipliers.csv`
- `read_tenure_multipliers()` → reads `config_promotion_hazard_tenure_multipliers.csv`
- `read_all()` → returns `PromotionHazardConfig`
- `validate(config)` → returns list of error strings
- `save_all(config)` → validates + writes all 3 CSVs

### Step 3: Backend Router (`promotion_hazard.py`)

- `GET /{workspace_id}/config/promotion-hazards` → calls `service.read_all()`
- `PUT /{workspace_id}/config/promotion-hazards` → calls `service.save_all(request)`

### Step 4: Router Registration

- Add `from .promotion_hazard import router as promotion_hazard_router` to `routers/__init__.py`
- Add `app.include_router(promotion_hazard_router, ...)` to `main.py`

### Step 5: Frontend API Layer (`api.ts`)

Add TypeScript interfaces matching Pydantic models, plus:
```typescript
export async function getPromotionHazardConfig(workspaceId: string): Promise<PromotionHazardConfig>
export async function savePromotionHazardConfig(workspaceId: string, config: PromotionHazardConfig): Promise<PromotionHazardSaveResponse>
```

### Step 6: Frontend UI (`ConfigStudio.tsx`)

Add state variables (following band config pattern):
- `promotionHazardConfig`, `promotionHazardLoading`, `promotionHazardError`
- `promotionHazardSaveStatus`, `promotionHazardValidationErrors`

Add `useEffect` to load on workspace change. Add change handlers for base params and multipliers. Add save handler with client-side validation. Add UI section after Market Positioning (~line 2395) with:
- Base parameters (2 inline inputs for base rate % and level dampener %)
- Age multipliers table (6 rows: band label + multiplier input)
- Tenure multipliers table (5 rows: band label + multiplier input)
- Save button with loading/success/error states

## Testing

1. Start `planalign studio`
2. Open a workspace → Configuration page
3. Scroll to "Promotion Hazard" section (after Market Positioning)
4. Verify values match CSV seed data
5. Edit base rate from 2% to 5%, save, reload → verify persistence
6. Edit an age multiplier, save, reload → verify persistence
7. Test validation: enter negative multiplier → verify error shown
8. Run a simulation → verify `dim_promotion_hazards` uses updated values
