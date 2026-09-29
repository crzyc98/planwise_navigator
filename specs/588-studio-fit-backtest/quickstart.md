# Quickstart: Studio Fit & Backtest (#588)

## Analyst flow (Studio)

1. Open **Run → Fit & Backtest** (`#/w/<workspace>/fit`).
2. **History**: upload 2–5 annual census files (e.g. `census_2022.csv` … `census_2025.csv`). Check each year, row count and sha256, plus the combined source digest. Fix any reported error, such as a gap, a duplicate year or a missing column.
3. **Configure**: choose the base scenario (it supplies the priors) and a mode: Fit, or Fit + Backtest. For a backtest, also pick the holdout and seeds. Adjust Advanced settings only when needed; any moved value is flagged.
4. **Review** the pre-run summary and click **Run**. Progress shows the stage, or "seed i of N" during a backtest. **Cancel** stops the job and removes its artifacts.
5. **Results**: fit summary, diagnostics with thin cells highlighted, provenance, the scorecard, and links to the full reports.
6. **Apply to new scenario**: pick the source scenario, review the diff, tick the required acknowledgements, and name the new scenario. The source scenario is never changed.

## Developer verification

```bash
source .venv/bin/activate
pytest -m fast tests/test_parameter_fitting.py tests/api/test_param_fit_*.py -q
pytest tests/api/test_param_fit_backtest_e2e.py -q        # slow: real isolated backtest
cd planalign_studio && node_modules/.bin/tsc --noEmit -p tsconfig.json \
  && node_modules/.bin/eslint . --max-warnings 0 && node_modules/.bin/vitest run
```

After changing API models, regenerate the OpenAPI snapshot and the TypeScript types (see `specs/115-api-contract-tests/quickstart.md`), then run `node_modules/.bin/openapi-typescript ../tests/api/snapshots/openapi_schema.json -o services/api.generated.ts --empty-objects-unknown` from `planalign_studio/`.

## CLI (unchanged)

`planalign fit <dir>` and `planalign backtest <dir>` keep their arguments, exit codes and output. The only additions:
- packs now also contain `diagnostics.json`
- backtest packs also contain `fit_report.md`
