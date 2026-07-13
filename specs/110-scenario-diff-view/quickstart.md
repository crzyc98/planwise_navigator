# Quickstart: Studio Two-Scenario Diff View

**Feature**: 110-scenario-diff-view

All behavioral validation uses disposable isolated databases. Never run these checks against `dbt/simulation.duckdb`.

## 1. Activate the existing environment

```bash
source .venv/bin/activate
```

## 2. Run targeted backend tests first

```bash
pytest -m fast tests/test_comparison_dc_plan.py tests/test_config_diff_service.py tests/test_comparison_api.py -v
```

Expected: average compensation includes active employees only; configuration differences are deterministic and reuse effective merge semantics; missing metadata succeeds with unavailable provenance; duplicate/incomplete/missing scenarios return the contract's 400/404 responses; fixture database files are unchanged after reads.

## 3. Validate frontend types and production bundling

```bash
cd planalign_studio
npm run build
cd ..
```

Expected: the new route and API payloads compile without `any` in the new comparison/config-diff types.

## 4. Build two deliberate isolated scenarios

Create a disposable scenario directory under `/tmp/planalign-110/scenarios` containing `a.yaml` and `b.yaml`. Base both on `scenarios/baseline.yaml`, keep the same `simulation.random_seed`, growth, compensation, enrollment, and eligibility settings, and change only `employer_match.active_formula` in B to a valid alternate formula already present in the base configuration. Give A and B distinct `scenario_id` values.

Run both through the full multi-year pipeline:

```bash
planalign batch --scenarios a b \
  --scenarios-dir /tmp/planalign-110/scenarios \
  --output-dir /tmp/planalign-110/output \
  --clean --threads 1
```

Expected: both scenarios complete and each has its own isolated DuckDB under the disposable output directory. Do not copy either database into the repository.

## 5. Exercise the read-only contracts

Start Studio against a disposable workspace containing or importing those two completed scenario artifacts, then request:

```text
GET /api/workspaces/{workspace_id}/comparison?scenarios={a_id},{b_id}&baseline={a_id}
GET /api/workspaces/{workspace_id}/comparison/config-diff?scenario_a={a_id}&scenario_b={b_id}
```

See [comparison-api.yaml](./contracts/comparison-api.yaml) for the exact response shape.

Expected:

- Configuration differences contain exactly the deliberate employer-match lever (plus no cosmetic metadata).
- `seeds_match` is `true`; no seed-noise warning is required.
- Employer match cost differs by year where the formula affects participants.
- Headcount and average active-employee compensation deltas are zero for every common year.
- Participation and total employer cost reflect only effects actually produced by the changed formula.
- Each scenario's fingerprint, seed, and run timestamp are displayed when metadata exists.

## 6. Verify seed and legacy provenance states

Repeat the service/router fixture test with different latest seeds. Expected: `seeds_match=false` and the Studio header shows "differences may include seed noise."

Repeat with `run_metadata` absent in one fixture database. Expected: the endpoint remains successful, `seeds_match=null`, and that scenario is labeled "provenance unavailable."

Repeat with two run records whose fingerprints differ and whose latest record is not a full reset or calibration. Expected: per-scenario and top-level drift warnings are true.

## 7. Read-only assertion

For fixture and end-to-end databases, record file modification timestamps and/or checksums before calling both endpoints and compare them afterward. Expected: no scenario database, configuration file, or override file changes.

## 8. Broader local gates

```bash
ruff check planalign_api tests/test_comparison_dc_plan.py tests/test_config_diff_service.py tests/test_comparison_api.py
mypy planalign_api planalign_orchestrator planalign_cli planalign_core --ignore-missing-imports
pytest -m fast
```

The full suite is optional for the local loop but should run before merge when CI capacity permits.

## Implementation validation record (2026-07-12)

- Targeted backend plus acceptance suite: 25 tests passed.
- Fast suite: 1,588 tests passed and 632 were deselected in 112.28 seconds.
- Targeted Ruff and feature-file mypy checks: passed.
- Repository-wide mypy: still reports nine pre-existing errors in `planalign_api/run.py`, `planalign_api/routers/sync.py`, `planalign_api/services/vesting_service.py`, and `planalign_api/main.py`; none are in feature-changed files.
- Studio production build: passed; existing bundle-size and mixed static/dynamic import warnings remain unchanged.
- Isolated acceptance fixture: `tests/test_scenario_diff_acceptance.py` verifies the single match-formula delta, matching seeds, flat headcount/average compensation, and divergent employer match cost without writing to either database.
- Full `planalign batch` completed successfully for matching-seed scenarios A and B after wiring the orchestrator's active connection manager into `DbtRunner`; the regression is covered by `tests/integration/test_self_healing_integration.py`.
- Read-only verification against copies of the two generated scenario databases under `/tmp/planalign-110` returned exactly `employer_match.active_formula` as the config delta, `seeds_match=true`, no drift warning, zero headcount and average-compensation deltas in 2025 and 2026, and positive employer-match deltas of $9,108.50 and $8,120.87 respectively.
- The shared `dbt/simulation.duckdb` was not used or modified for behavioral validation.
