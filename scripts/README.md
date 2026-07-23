# Utility Scripts

Small standalone utilities that support development. None of these run in CI (`ci.yml` invokes no scripts); all are run manually from the repo root with the venv active.

| Script | Purpose |
|--------|---------|
| `check_fast_suite_runtime.py` | Fails when the fast pytest suite (`pytest -m fast`) exceeds its hard time budget — a guard against fast-suite bloat. |
| `create_census.py` | Generate a synthetic employee census parquet for development and testing. |
| `generate_fresh_census.py` | Generate a fresh `census_preprocessed.parquet` with different demographic characteristics. |
| `data_quality_auditor.py` | Comprehensive data-quality audit of a simulation database (pairs with the data-quality-auditor agent). |
| `install_sqlparse_fix.py` | Manual fallback installer for the sqlparse token-limit fix. Normally unnecessary — the fix auto-installs on first `import planalign_orchestrator`. |

## History

This directory once held ~30 scripts. In July 2026 the one-off migrations, epic-era diagnostics, benchmark tooling, and an abandoned Claude-hook experiment were removed (along with their two dead CI workflows). If you need one back, it's in git history prior to that cleanup.

Compensation calibration scripts were superseded by the built-in `planalign calibrate` command (Feature 105).
