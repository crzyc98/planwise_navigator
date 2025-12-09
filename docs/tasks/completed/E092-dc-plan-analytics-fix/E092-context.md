# Context: E092 DC Plan Analytics Fix

## Key Files
- `/workspace/planalign_api/services/analytics_service.py` - DC Plan analytics queries
- `/workspace/planalign_api/services/comparison_service.py` - Scenario comparison queries
- `/workspace/planalign_api/services/simulation_service.py` - Reference for fallback pattern
- `/workspace/dbt/models/marts/fct_workforce_snapshot.sql` - Data source

## Issues Found
1. Database path fallback missing in analytics/comparison services (exists in simulation_service)
2. Case sensitivity: data has lowercase `active`/`terminated`, queries expected uppercase

## Decisions
- Follow existing pattern from simulation_service.py for database fallback
- Use `UPPER()` function for case-insensitive matching
- Log warning when using global database

## Testing Verified
- API endpoint: `/api/workspaces/{id}/scenarios/{id}/analytics/dc-plan`
- Returns participation, contribution, deferral distribution data correctly
