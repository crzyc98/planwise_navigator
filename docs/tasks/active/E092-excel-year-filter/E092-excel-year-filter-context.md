# E092 Context

**Last Updated**: 2025-12-08

## Key Files

| File | Purpose |
|------|---------|
| `planalign_orchestrator/excel_exporter.py` | Main file to modify - all export queries |

## Key Methods to Modify

| Method | Line | Change |
|--------|------|--------|
| `export_scenario_results()` | 42-84 | Extract year range from config, pass to helpers |
| `_write_workforce_sheets()` | 246-279 | Add WHERE simulation_year BETWEEN ? AND ? |
| `_calculate_summary_metrics()` | 318-387 | Add year filter to GROUP BY query |
| `_calculate_events_summary()` | 389-413 | Add year filter |

## Query Changes

### Before (lines 256-259):
```python
years = self._query_to_df(
    conn,
    "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year",
)
```

### After:
```python
years = self._query_to_df(
    conn,
    "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot WHERE simulation_year BETWEEN ? AND ? ORDER BY simulation_year",
    params=[start_year, end_year],
)
```
