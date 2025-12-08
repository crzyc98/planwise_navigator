# E092: Fix Excel Export Including Wrong Years

**Last Updated**: 2025-12-08
**Status**: In Progress
**Branch**: `feature/E092-excel-year-filter`
**Issue**: #83

## Summary

Excel export includes data from years outside the configured simulation range. When user configures 2025-2026, the downloaded Excel file shows 2027 data from previous simulation runs.

## Root Cause

The Excel exporter in `planalign_orchestrator/excel_exporter.py` queries ALL years from the database without filtering by the config's `start_year`/`end_year`.

## Fix Strategy

Add year range filtering to all Excel export queries:
1. `export_scenario_results()` - Extract years from config
2. `_write_workforce_sheets()` - Filter workforce data
3. `_calculate_summary_metrics()` - Filter summary
4. `_calculate_events_summary()` - Filter events

## Verification

1. Configure simulation for 2025-2026
2. Run simulation
3. Download Excel export
4. Verify only years 2025-2026 appear in all sheets
