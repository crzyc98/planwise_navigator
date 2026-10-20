# Utility Scripts

Small standalone utilities that support development. Run them from the repo root with the venv active; the gitlink guard also runs in pre-commit and CI.

| Script | Purpose |
|--------|---------|
| `dev.py` | Check the active checkout and Python environment, then execute a command with its venv on PATH. |
| `check_worktree_gitlinks.py` | Reject `.worktrees/*` gitlinks in the Git index without inspecting nested checkout contents. |
| `check_fast_suite_runtime.py` | Fails when the fast pytest suite (`pytest -m fast`) exceeds its hard time budget — a guard against fast-suite bloat. |
| `create_census.py` | Generate a synthetic employee census parquet for development and testing. |
| `generate_fresh_census.py` | Generate a fresh `census_preprocessed.parquet` with different demographic characteristics. |
| `data_quality_auditor.py` | Comprehensive data-quality audit of a simulation database (pairs with the data-quality-auditor agent). |
| `install_sqlparse_fix.py` | Manual fallback installer for the sqlparse token-limit fix. Normally unnecessary — the fix auto-installs on first `import planalign_orchestrator`. |

## Nested development worktrees

Start a tool session with `python3 scripts/dev.py --check`. Run project commands as
`python3 scripts/dev.py -- python -m pytest ...`. Use `--require <path>` before
`--` to reject missing input paths before execution. The runner preserves cwd and
child exit codes; from `dbt/`, invoke `python3 ../scripts/dev.py -- dbt ... --threads 1`.
Continue to set an isolated `DATABASE_PATH` for behavioral validation.

For a worktree that predates this script, invoke the main checkout's `scripts/dev.py`
by absolute path while keeping cwd in the worktree. A local `.venv` takes precedence.
Without one, the runner can reuse the main checkout's environment only if Python
dependency declarations and `uv.lock` match. It puts the active checkout on
`PYTHONPATH` and verifies application import origin. Do not install or update packages
in a borrowed environment; dependency changes need an independently provisioned venv.
The preflight reports missing dbt and Studio packages but does not install them.
It checks core imports, not the complete dependency graph or every optional tool.

Keep nested checkouts under `.worktrees/`. Git ignores this directory, and Black,
Ruff, and pre-commit explicitly exclude it. Run `python scripts/check_worktree_gitlinks.py`
to check the prospective commit index; pre-commit and CI run the same guard.
If a gitlink is accidentally staged with `git add --force`, remove only its index
entry with `git rm --cached -- .worktrees/<name>`. This preserves the local checkout.

## History

This directory once held ~30 scripts. In July 2026 the one-off migrations, epic-era diagnostics, benchmark tooling, and an abandoned Claude-hook experiment were removed (along with their two dead CI workflows). If you need one back, it's in git history prior to that cleanup.

Compensation calibration scripts were superseded by the built-in `planalign calibrate` command (Feature 105).
