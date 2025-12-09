# Plan: E092 DC Plan Analytics Page Fix

## Problem Summary
The DC Plan analytics page at `http://localhost:5173/#/analytics/dc-plan` shows no data due to two issues:

1. **Missing database fallback**: `analytics_service.py` and `comparison_service.py` don't fall back to `dbt/simulation.duckdb` (CLI database location)

2. **Case sensitivity bug**: SQL queries expect uppercase `'ACTIVE'`/`'TERMINATED'` but data contains lowercase `'active'`/`'terminated'`

## Solution Implemented

### Fix 1: Database Fallback
Added fallback to `dbt/simulation.duckdb` in:
- `planalign_api/services/analytics_service.py:_get_database_path()`
- `planalign_api/services/comparison_service.py:_load_scenario_data()`

### Fix 2: Case Sensitivity
Changed all `employment_status = 'ACTIVE'` to `UPPER(employment_status) = 'ACTIVE'` in both services.

## Files Modified
- `planalign_api/services/analytics_service.py`
- `planalign_api/services/comparison_service.py`

## Testing
API endpoint now returns proper data:
- Total eligible: 4,641
- Total enrolled: 3,683
- Participation rate: 79.36%
