# Contract: CI Job & Developer Interface

## Pytest interface

| Surface | Contract |
|---|---|
| Marker | `multi_year_invariants` registered in `pyproject.toml`; all suite tests also carry `integration` |
| Local command | `pytest -m multi_year_invariants -v` — the single documented command (FR-013) |
| Isolation | All DBs under pytest tmp dirs; `DATABASE_PATH` set by fixtures only; the suite never opens `dbt/simulation.duckdb` (SC-004) |
| Cleanup | Tmp DBs removed on pass (pytest tmp retention); on failure, copies preserved under `var/test-artifacts/113/` (git-ignored `var/`) |
| Simulation failure | Reported as an errored setup fixture with the orchestrator's exception (stage, model, resolution hint per E074); invariant tests are skipped, not failed (FR-014) |

## CI job (`.github/workflows/ci.yml`)

| Surface | Contract |
|---|---|
| Job name | `multi-year-invariants` (name is part of the required-checks contract; renames need branch-protection updates) |
| Trigger | Every pull request (and pushes to `main`, matching existing jobs) |
| Steps | checkout → Python 3.11 → uv + dep cache (mirrors existing jobs) → `pytest -m multi_year_invariants -v` |
| Blocking | Added to required status checks from day one (spec assumption; no advisory phase) |
| Failure artifact | `actions/upload-artifact` with `if: failure()` uploading `var/test-artifacts/113/*.duckdb` (+ the rendered diagnostics log), retention ≥ 7 days (FR-012, acceptance 1.5) |
| Budget | Job timeout 20 min; expected runtime < 15 min (SC-002) — breach is a performance regression to investigate, not a timeout to raise |
| Concurrency | Safe to run in parallel with other jobs/runs — no shared state outside the runner workspace |
