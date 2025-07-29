# Session 2025-07-29: Multi-Year Orchestrator Dependency Fix

## Context
We successfully implemented the correct business logic for compensation events:
- **Merit events (July 15)** check for promotions first, then use year-end compensation
- **Promotions (February 1)** use previous year-end compensation
- **All event generation moved to dbt models only** (no more Python generation)

The orchestrator now calls `generate_simulation_events_via_dbt()` which runs dbt models in proper sequence.

## Current Issue
The multi-year orchestrator command fails:
```bash
python -m orchestrator_mvp.run_mvp --multi-year --force-clear --no-breaks
```

**Error:**
```
Runtime Error in model int_promotion_events (models/intermediate/events/int_promotion_events.sql)
Catalog Error: Table with name int_hazard_promotion does not exist!
LINE 97:     INNER JOIN simulation.main.int_hazard_promotion h
```

## Root Cause Analysis
The new dbt-only event generation approach requires these dependencies to be built first:

### Missing Dependencies for Promotion Events:
1. `int_hazard_promotion` - promotion probability lookup table
2. `int_employee_compensation_by_year` - compensation data source
3. All upstream dependencies of hazard models

### Missing Dependencies for Merit Events:
1. `int_hazard_merit` - merit raise probability lookup table
2. `int_effective_parameters` - dynamic parameter system
3. `config_raise_timing_distribution` - seed data for timing
4. Termination hazard config files (referenced by merit hazard model)

## Build Order Required
The correct build order should be:
1. **Seeds** → **Staging models** → **Foundation models**
2. **Hazard models** (`int_hazard_promotion`, `int_hazard_merit`)
3. **Parameter models** (`int_effective_parameters`)
4. **Compensation models** (`int_employee_compensation_by_year`)
5. **Event models** (promotion → merit → termination → hiring)
6. **Aggregate models** (`fct_yearly_events`, `fct_workforce_snapshot`)

## Current Multi-Year Orchestrator Issues
The `MultiYearSimulationOrchestrator` and our `generate_simulation_events_via_dbt()` function are trying to run event models without building their dependencies first.

### Files Needing Updates:
- `orchestrator_mvp/run_mvp.py` - `generate_simulation_events_via_dbt()` function
- `orchestrator_mvp/core/multi_year_orchestrator.py` - dependency build order
- Missing seed files for termination hazard models
- Missing `config_raise_timing_distribution` seed file

## Business Logic Status
✅ **CORE LOGIC IS CORRECT** - Merit events properly check for promotions first
✅ **DBT MODELS IMPLEMENTED** - All event models use correct compensation chain
✅ **ORCHESTRATOR UPDATED** - No more Python event generation

The remaining work is purely dependency/infrastructure issues, not business logic.

## Next Steps
1. Build missing `int_hazard_promotion` dependency
2. Fix multi-year orchestrator to build dependencies in correct order
3. Create or fix missing seed files
4. Test full orchestrator run

## Key Files Modified (Working Correctly)
- `dbt/models/intermediate/events/int_merit_events.sql` - Uses promotion-aware logic
- `dbt/models/intermediate/events/int_promotion_events.sql` - Uses compensation table
- `orchestrator_mvp/run_mvp.py` - New `generate_simulation_events_via_dbt()` function
