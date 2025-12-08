# E091: UI Simulation Year Range and Compensation Calculation Fixes

**Last Updated**: 2025-12-08
**Status**: In Progress
**Branch**: `feature/E091-ui-year-range-compensation-fixes`

## Summary

Two issues identified in the PlanAlign Studio UI:
1. **Year Range Bug**: Running a 2025-2026 simulation in the UI still runs 2027
2. **Compensation Discrepancy**: Analytics page shows `AVG(current_compensation)` but user expects `AVG(prorated_annual_compensation)`

---

## Issue 1: Simulation Running Wrong Year (2027 instead of 2026)

### Root Cause Analysis

The year range flows through the system as follows:
1. UI sends config with `start_year`/`end_year` to API
2. API extracts years from merged config (line 109-110 in `simulations.py`)
3. SimulationService passes year range string to CLI subprocess (line 260)
4. CLI parses and passes to PipelineOrchestrator

**Potential causes:**
- **Default fallback to 2027**: If config isn't properly saved/merged, defaults kick in (`end_year=2027`)
- **Config not persisted**: UI may not be saving `end_year` override to scenario's `config_overrides`
- **Stale merged config**: `get_merged_config()` may be returning stale/default values

### Fix Strategy

1. Add logging to trace what year range is being received and passed
2. Verify that `config_overrides.simulation.end_year` is properly saved when user selects years in UI
3. Check if ConfigStudio properly updates and saves `endYear` to backend

---

## Issue 2: Average Compensation Calculation Mismatch

### Root Cause

The analytics dashboard uses `AVG(current_compensation)` but user expects `AVG(prorated_annual_compensation)`.

| Field | Description |
|-------|-------------|
| `current_compensation` | Year-end salary rate (what they'd earn at current rate for full year) |
| `prorated_annual_compensation` | Actual earnings adjusted for time worked |

### Fix Strategy

Change the query in `simulation_service.py` line 707 from:
```python
AVG(current_compensation) as avg_compensation
```
to:
```python
AVG(prorated_annual_compensation) as avg_compensation
```

---

## Verification Criteria

1. **Year Range**: Running a 2025-2026 simulation should only run years 2025 and 2026 (not 2027)
2. **Compensation**: `AVG(prorated_annual_compensation)` from analytics should match manual calculation from `fct_workforce_snapshot`
