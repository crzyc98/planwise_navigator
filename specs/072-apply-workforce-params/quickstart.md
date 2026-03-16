# Quickstart: Apply Workforce Parameters Across Scenarios

**Feature Branch**: `072-apply-workforce-params`

## What This Feature Does

Adds an "Apply Workforce Params" button to each scenario's config page. Analysts can push workforce assumptions (compensation, turnover, hiring, demographics) from the current scenario to multiple other scenarios in one action, while preserving each target's DC plan configuration.

## Development Setup

```bash
# Backend
source .venv/bin/activate
cd /workspace

# Frontend
cd planalign_studio
npm install
npm run dev
```

## Key Files to Modify

### Backend (3 files)
1. **`planalign_api/models/scenario.py`** — Add `WorkforceParamsApplyRequest` and `WorkforceParamsApplyResult` Pydantic models
2. **`planalign_api/routers/scenarios.py`** — Add `POST .../apply-workforce-params` endpoint
3. **`planalign_api/services/scenario_service.py`** — Add `apply_workforce_params()` method with read-merge-write logic

### Frontend (3 files)
1. **`planalign_studio/services/api.ts`** — Add `applyWorkforceParams()` API client function
2. **`planalign_studio/components/config/ApplyWorkforceParamsModal.tsx`** — New modal component (multi-select targets + confirmation)
3. **`planalign_studio/components/ConfigStudio.tsx`** — Add "Apply Workforce Params" button next to existing "Copy from Scenario"

## Testing

```bash
# Backend unit tests
pytest tests/test_apply_workforce_params.py -v

# Manual E2E test
planalign studio
# 1. Create 3+ scenarios with different configs
# 2. Open Scenario A config → click "Apply Workforce Params"
# 3. Select Scenarios B and C → Apply
# 4. Verify B and C have A's workforce params but original DC plan params
```

## Workforce vs. DC Plan Parameter Boundary

**Copied (workforce)**: `compensation.*`, `workforce.*`, `simulation.target_growth_rate`, `new_hire.*`, `promotion_hazard`, `age_bands`, `tenure_bands`

**Preserved (DC plan)**: `dc_plan.*`

**Excluded (identity/infra)**: `simulation.{name,start_year,end_year,random_seed}`, `data_sources.*`, `advanced.*`
