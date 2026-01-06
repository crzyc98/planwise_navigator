# Quickstart: SQLParse Token Limit Fix

## Problem

When running multi-year simulations, Year 2+ fails with:
```
Maximum number of tokens exceeded (10000)
```

This is caused by sqlparse 0.5.4+ DoS protection limiting SQL parsing to 10,000 tokens, while `fct_workforce_snapshot.sql` compiles to ~13,668 tokens in Year 2+.

## Quick Fix (Automatic!)

The fix is **automatic** - it installs on first import of `planalign_orchestrator`:

```bash
# Just run any planalign command or import the package:
planalign health

# Or:
python -c "import planalign_orchestrator"

# You'll see this message on first run:
# ✓ Auto-installed sqlparse fix to /path/to/site-packages
#   Restart your Python interpreter for subprocess dbt to use the fix.
```

Then restart your terminal/Python and verify:

```bash
python -c "import sqlparse.engine.grouping; print(f'MAX_GROUPING_TOKENS={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}')"
# Expected output: MAX_GROUPING_TOKENS=50000
```

## Verify Fix Works

```bash
# Test multi-year simulation
planalign simulate 2025-2027 --verbose

# Or test dbt directly
cd dbt && dbt run --select fct_workforce_snapshot --vars '{"simulation_year": 2026}' --threads 1
```

## What the Fix Does

1. **Auto-installs on first import** of `planalign_orchestrator`
2. **Creates _sqlparse_config.py** in `.venv/lib/pythonX.Y/site-packages/`
3. **Creates sqlparse_config.pth** which imports the config module at Python startup
4. **Configures sqlparse** before dbt loads:
   ```python
   import sqlparse.engine.grouping
   sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
   ```
5. **Applies to all Python processes** in the virtual environment

## Troubleshooting

### Fix Not Applied?

```bash
# Check if .pth file exists
ls -la .venv/lib/python*/site-packages/sqlparse_config.pth
ls -la .venv/lib/python*/site-packages/_sqlparse_config.py

# If missing, just import the package:
python -c "import planalign_orchestrator"

# Or run the manual install script:
python scripts/install_sqlparse_fix.py
```

### Wrong Python Version?

The fix is Python version-agnostic. It automatically detects your Python version:

```bash
# Find correct site-packages path
python -c "import site; print(site.getsitepackages())"
```

### Still Getting Token Errors?

1. Restart your terminal (clears cached Python imports)
2. Verify you're using the project venv: `which python`
3. Check sqlparse version: `pip show sqlparse`

## After Recreating Virtual Environment

After running `uv venv` or recreating the venv, just import the package once:

```bash
pip install -e .
python -c "import planalign_orchestrator"
# Restart terminal, done!
```

## Background

- sqlparse 0.5.4 added DoS protection with 10,000 token limit
- `fct_workforce_snapshot.sql` has 1,085 lines with complex Jinja
- Year 2+ compiles to more tokens due to temporal logic branches
- The .pth file runs before any imports, including dbt subprocesses
