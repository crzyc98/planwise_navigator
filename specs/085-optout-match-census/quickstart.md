# Developer Quickstart: Match Census for Opt-Out Rate Configuration

**Branch**: `085-optout-match-census`

## What This Feature Does

Adds a "Match Census" button to the Opt-Out Assumptions panel in PlanAlign Studio. When clicked, it calculates a suggested opt-out rate from the census non-participant rate, filtered to employees hired within a configurable lookback window (default 3 years). The analyst previews the result and optionally applies it.

## Files to Create

| File | Purpose |
|------|---------|
| `planalign_api/models/opt_out.py` | Pydantic request/response models |
| `planalign_api/services/opt_out_service.py` | Census analysis service |
| `tests/test_opt_out_analysis.py` | Unit + integration tests |

## Files to Modify

| File | Change |
|------|--------|
| `planalign_api/services/sql_security.py` | Add `CENSUS_DEFERRAL_COLUMNS` frozenset and extend `ALL_CENSUS_COLUMNS` |
| `planalign_api/routers/bands.py` | Add new `POST /{workspace_id}/analyze-opt-out-rate` endpoint + import |
| `planalign_studio/services/api.ts` | Add `analyzeOptOutRate` function and `OptOutRateAnalysisResult` interface |
| `planalign_studio/components/config/DCPlanSection.tsx` | Add "Match Census" button, state, and preview panel |

## Running the Feature

```bash
# Start the full stack
planalign studio

# Test the new endpoint directly
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/analyze-opt-out-rate \
  -H "Content-Type: application/json" \
  -d '{"file_path": "uploads/census_2024.csv", "lookback_years": 3}'

# Run the new tests
pytest tests/test_opt_out_analysis.py -v
pytest -m fast  # ensure no regressions
```

## Key Implementation Notes

1. **Enrollment detection**: An employee is a non-participant when `deferral_rate = 0 OR deferral_rate IS NULL`. This matches the dbt staging model (`stg_census_data.sql:141`).

2. **Lookback anchor**: Use `MAX(hire_date)` in the census file, not today's date. Census files are historical snapshots.

3. **Active filter**: Only include employees where the `active` column indicates active employment. Use case-insensitive matching (`'active'`, `'y'`, `'1'`, `true`).

4. **SQL safety**: All census column names used in dynamic SQL must be validated via `validate_column_name_from_set()` against the `CENSUS_DEFERRAL_COLUMNS` and `CENSUS_HIRE_DATE_COLUMNS` sets.

5. **Frontend state pattern**: Mirror `TurnoverSection.tsx` — three state vars (`analyzing`, `analysis`, `analysisError`), a `handleMatchCensus` async function, a `handleApply` that updates `dcOptOutRateTarget`, and a dismiss/close button.

6. **Re-fetch on lookback change**: When the user changes `lookback_years` in the preview panel, automatically re-call the API. Debounce input changes by ~500ms to avoid excessive requests.

7. **No dbt changes**: This feature only reads the raw census file in-memory via DuckDB. It does not touch dbt models or the simulation database.

## Test Strategy

- **Unit tests**: `OptOutAnalysisService` with small in-memory DuckDB fixtures (enrolled/non-enrolled employees, null tenure cases, empty lookback window)
- **Integration tests**: FastAPI test client calling the endpoint with a real CSV fixture
- **Fast suite**: All new unit tests tagged `@pytest.mark.fast`
