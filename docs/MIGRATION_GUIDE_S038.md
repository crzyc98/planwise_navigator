# Migration Guide: Legacy Runner → PlanAlign Orchestrator (S038)

This guide helps you migrate from the legacy `run_multi_year.py` approach to the modular PlanAlign Orchestrator introduced in the S038 stories.

## What Changed
- New package: `planalign_orchestrator/` with focused modules:
  - `config`, `utils`, `dbt_runner`, `registries`, `validation`, `reports`, `pipeline`, `cli`, `factory`, `migration`.
- Standardized dbt execution via `DbtRunner` with streaming and retries.
- Typed configuration loader with env overrides and dbt var mapping.
- Registry management for enrollment and deferral escalation.
- Validation framework and audit/reporting utilities.
- Pipeline orchestrator coordinates multi‑year workflows with checkpoints.
- CLI commands for running, validating, and inspecting checkpoints.

## Quick Start (New Orchestrator)
- Validate configuration
  - `python -m planalign_orchestrator validate -c config/simulation_config.yaml`
- Dry‑run (echo dbt commands), verbose
  - `python -m planalign_orchestrator run -c config/simulation_config.yaml --dry-run -v`
- Run specific years and resume from last checkpoint
  - `python -m planalign_orchestrator run --years 2025-2027 --resume`
- Show last checkpoint
  - `python -m planalign_orchestrator checkpoint -c config/simulation_config.yaml`

## Mapping: Legacy → New
- `run_dbt_command(...)` → `DbtRunner.execute_command([...], simulation_year=YYYY, dbt_vars=...)`
- `extract_dbt_vars_from_config(...)` → `planalign_orchestrator.config.to_dbt_vars(cfg)`
- `ExecutionMutex` (shared_utils) → `planalign_orchestrator.utils.ExecutionMutex`
- Direct `duckdb.connect(...)` → `DatabaseConnectionManager.transaction()` or `execute_with_retry(...)`
- Ad‑hoc prints/summaries → `reports.YearAuditor`, `reports.ConsoleReporter`, `reports.MultiYearReporter`
- Hand‑rolled loops → `pipeline.PipelineOrchestrator` orchestrates stages + validation + reporting

## Optional Config Additions
For full provenance, add these to `config/simulation_config.yaml` (optional but recommended):
```yaml
scenario_id: "baseline_2025"
plan_design_id: "default_plan"
```
You can enforce these via `SimulationConfig.require_identifiers()` when needed.

## Step‑by‑Step Migration
1) Sanity check config
- `python -m planalign_orchestrator validate -c config/simulation_config.yaml`

2) Dry‑run pipeline (no dbt execution)
- `python -m planalign_orchestrator run -c config/simulation_config.yaml --dry-run -v`

3) Run with dbt
- `python -m planalign_orchestrator run -c config/simulation_config.yaml`

4) Inspect results
- Per‑year JSON: `reports/year_<YEAR>.json`
- Multi‑year CSV: `reports/multi_year_summary_<START>_<END>.csv`

5) Compare outputs (optional)
- Query counts from `fct_yearly_events` and `fct_workforce_snapshot` for key years and compare to legacy runner outputs.

## Checkpoints & Resume
- Location: `.navigator_checkpoints/`
- Last checkpoint
  - `python -m planalign_orchestrator checkpoint -c config/simulation_config.yaml`
- Clean/sanitize (basic)
  - `from planalign_orchestrator.migration import MigrationManager; MigrationManager().migrate_checkpoints()`

## Rollback Plan
- The legacy `run_multi_year.py` remains unchanged; you can continue using it.
- Keep `simulation_backup.duckdb` for safe fallback.
- Clear `.navigator_checkpoints/` if resuming causes confusion (files are small JSONs).

## Programmatic Usage (Factory)
```python
from planalign_orchestrator.factory import create_orchestrator

orchestrator = create_orchestrator(
    "config/simulation_config.yaml",
    threads=8,
    db_path="simulation.duckdb",
)
summary = orchestrator.execute_multi_year_simulation()
print(summary.growth_analysis)
```

## Known Differences / Notes
- Validation rules are explicit and configurable; pipeline can stop on ERROR severity (`--fail-on-validation-error`).
- Reporting emits structured JSON/CSV artifacts, making comparisons easier.
- Event generation stage is parallel‑safe via `DbtRunner.run_models()` where appropriate.

## Troubleshooting
- dbt not found: use `--dry-run` to validate orchestration without dbt, then ensure `dbt` is on PATH.
- Stale checkpoints: run `MigrationManager().migrate_checkpoints()` to sanitize.
- Permissions: ensure you can write to `reports/` and `.navigator_checkpoints/`.

---
For broader context and API details, see `planalign_orchestrator/README.md` and the S038 stories in `docs/stories/`.
