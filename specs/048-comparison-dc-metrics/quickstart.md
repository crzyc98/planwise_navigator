# Quickstart: DC Plan Metrics in Scenario Comparison

**Feature**: 048-comparison-dc-metrics
**Branch**: `048-comparison-dc-metrics`

## Prerequisites

```bash
source .venv/bin/activate
```

## Files to Modify

| File | Action | Description |
| ---- | ------ | ----------- |
| `planalign_api/models/comparison.py` | Extend | Add `DCPlanMetrics`, `DCPlanComparisonYear`; extend `ComparisonResponse` |
| `planalign_api/services/comparison_service.py` | Extend | Add DC plan query in `_load_scenario_data()`, add `_build_dc_plan_comparison()` and `_build_dc_plan_summary_deltas()` |
| `planalign_api/routers/comparison.py` | Minimal | Import new models (router itself needs no logic changes) |
| `tests/test_comparison_dc_plan.py` | New | Unit tests with in-memory DuckDB |

## Implementation Order

1. **Models first** (`comparison.py`): Add Pydantic models so type hints are available
2. **Tests second** (`test_comparison_dc_plan.py`): Write failing tests (TDD)
3. **Service logic** (`comparison_service.py`): Implement query + comparison builders
4. **Verify** tests pass

## Key Patterns to Follow

### SQL Query (from analytics_service.py)

```sql
SELECT
    simulation_year,
    COALESCE(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0
        / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0), 0) AS participation_rate,
    AVG(CASE WHEN is_enrolled_flag THEN current_deferral_rate ELSE NULL END) AS avg_deferral_rate,
    COALESCE(SUM(prorated_annual_contributions), 0) AS total_employee_contributions,
    COALESCE(SUM(employer_match_amount), 0) AS total_employer_match,
    COALESCE(SUM(employer_core_amount), 0) AS total_employer_core,
    COALESCE(SUM(employer_match_amount) + SUM(employer_core_amount), 0) AS total_employer_cost,
    COALESCE(SUM(prorated_annual_compensation), 0) AS total_compensation,
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) AS participant_count
FROM fct_workforce_snapshot
GROUP BY simulation_year
ORDER BY simulation_year
```

### Delta Calculation Pattern (from _build_workforce_comparison)

```python
# For each metric field in DCPlanMetrics:
delta_value = scenario_value - baseline_value
# For percentage deltas in summary:
delta_pct = (delta / abs(baseline)) * 100 if baseline != 0 else 0.0
```

### Test Fixture Pattern (from test_analytics_service.py)

```python
@pytest.fixture
def in_memory_conn():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE fct_workforce_snapshot (
            simulation_year INTEGER,
            employee_id VARCHAR,
            employment_status VARCHAR,
            is_enrolled_flag BOOLEAN,
            current_deferral_rate DOUBLE,
            prorated_annual_contributions DOUBLE,
            employer_match_amount DOUBLE,
            employer_core_amount DOUBLE,
            prorated_annual_compensation DOUBLE
        )
    """)
    yield conn
    conn.close()
```

## Running Tests

```bash
# Run only the new tests
pytest tests/test_comparison_dc_plan.py -v

# Run with the fast marker
pytest -m fast tests/test_comparison_dc_plan.py -v
```

## Verification

After implementation, verify the endpoint works:

```bash
# Start the API
planalign studio --api-only

# Request comparison (replace with real IDs)
curl "http://localhost:8000/api/workspaces/{workspace_id}/comparison?scenarios=baseline,alternative&baseline=baseline"
```

Check that the response includes `dc_plan_comparison` with per-year values and deltas, and `summary_deltas` includes `final_participation_rate` and `final_employer_cost`.
