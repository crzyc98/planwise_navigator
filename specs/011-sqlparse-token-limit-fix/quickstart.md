# Quickstart: SQLParse Token Limit Fix

## Problem

When running multi-year simulations, Year 2+ fails with:
```
Maximum number of tokens exceeded (10000)
```

This is caused by sqlparse 0.5.4+ DoS protection limiting SQL parsing to 10,000 tokens, while `fct_workforce_snapshot.sql` compiles to ~13,668 tokens in Year 2+.

## Quick Fix (1 minute)

Run the install script to configure sqlparse limits:

```bash
# From project root
python scripts/install_sqlparse_fix.py

# Verify the fix
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

1. **Creates _sqlparse_config.py** in `.venv/lib/pythonX.Y/site-packages/`
2. **Creates sqlparse_config.pth** which imports the config module at Python startup
3. **Configures sqlparse** before dbt loads:
   ```python
   import sqlparse.engine.grouping
   sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
   ```
4. **Applies to all Python processes** in the virtual environment

## Troubleshooting

### Fix Not Applied?

```bash
# Check if .pth file exists (replace X.Y with your Python version, e.g., 3.11 or 3.12)
ls -la .venv/lib/python*/site-packages/sqlparse_config.pth
ls -la .venv/lib/python*/site-packages/_sqlparse_config.py

# If missing, reinstall
python scripts/install_sqlparse_fix.py
```

### Wrong Python Version?

```bash
# Find correct site-packages path
python -c "import site; print(site.getsitepackages())"
```

### Still Getting Token Errors?

1. Restart your terminal (clears cached Python imports)
2. Verify you're using the project venv: `which python`
3. Check sqlparse version: `pip show sqlparse`

## Manual Fix (if script fails)

Create `.venv/lib/pythonX.Y/site-packages/_sqlparse_config.py` (where X.Y is your Python version):

```python
"""Configure sqlparse token limits for large dbt models.

This module is automatically imported via sqlparse_config.pth when Python starts.
It configures sqlparse to handle models with >10,000 SQL tokens.
"""
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass  # Older sqlparse versions
```

Then create `.venv/lib/pythonX.Y/site-packages/sqlparse_config.pth`:

```
# Configure sqlparse token limits for large dbt models
import _sqlparse_config
```

## Background

- sqlparse 0.5.4 added DoS protection with 10,000 token limit
- `fct_workforce_snapshot.sql` has 1,085 lines with complex Jinja
- Year 2+ compiles to more tokens due to temporal logic branches
- Python's sitecustomize.py runs before any imports, including dbt
