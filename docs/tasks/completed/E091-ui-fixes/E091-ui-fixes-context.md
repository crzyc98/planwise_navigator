# E091 Context: Key Files and Decisions

**Last Updated**: 2025-12-08

## Key Files

### Primary Changes

| File | Lines | Purpose |
|------|-------|---------|
| `/workspace/planalign_api/services/simulation_service.py` | 236-237, 707 | Year extraction and compensation calculation |
| `/workspace/planalign_api/routers/simulations.py` | 109-110 | Year extraction with hardcoded defaults |

### Frontend Components

| File | Lines | Purpose |
|------|-------|---------|
| `/workspace/planalign_studio/components/AnalyticsDashboard.tsx` | 215 | Consumes avg_compensation from API |
| `/workspace/planalign_studio/components/ConfigStudio.tsx` | 150-156 | Default form data with endYear: 2027 |

### Config/Storage

| File | Purpose |
|------|---------|
| `/workspace/planalign_api/storage/workspace_storage.py` | Config merge logic |

## Key Decisions

1. **Use `prorated_annual_compensation`** instead of `current_compensation` for average compensation metric
   - Rationale: More accurate for partial-year employees (new hires, terminated)
   - Represents actual earnings, not hypothetical full-year salary

2. **Add debug logging** to trace year range flow
   - Will help identify where year range gets lost or overwritten

## Data Flow

```
UI (ConfigStudio)
  → API (simulations.py)
    → SimulationService
      → CLI subprocess
        → PipelineOrchestrator
```

Year defaults at each layer: `2027` if not explicitly set.
