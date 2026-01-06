# Research: SQLParse Token Limit Fix

**Feature Branch**: `011-sqlparse-token-limit-fix`
**Date**: 2026-01-06

## Problem Analysis

### Root Cause Investigation

The error "Maximum number of tokens exceeded (10000)" occurs because:

1. **sqlparse 0.5.4** introduced `MAX_GROUPING_TOKENS = 10000` as DoS protection
2. **fct_workforce_snapshot.sql** is 1,085 lines of complex SQL with Jinja templating
3. **Year 2+** compiles to more tokens than Year 1 because:
   - Year 1 branch: Uses `int_baseline_workforce` (simpler CTE)
   - Year 2+ branch: Uses `int_active_employees_prev_year_snapshot` with temporal logic (larger compiled SQL)
4. **Current fix doesn't work** because dbt runs as a subprocess with its own Python interpreter

### Current Fix Analysis

The existing fix in `/workspace/planalign_orchestrator/__init__.py`:

```python
# Configure sqlparse limits for large SQL models
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass  # Older sqlparse versions don't have this setting
```

**Why it fails**: When `DbtRunner` spawns dbt via `subprocess.Popen()`, the dbt process has:
- Its own Python interpreter
- Its own module imports
- Its own sqlparse module with default limits

The configuration in the parent process is NOT inherited by the subprocess.

## Solution Research

### Option 1: Pin sqlparse to 0.5.4

**Decision**: REJECTED

**Rationale**:
- sqlparse 0.5.4 still has `MAX_GROUPING_TOKENS = 10000` (the limit was introduced in 0.5.4, not 0.5.5)
- The dbt discourse suggests pinning to 0.5.4 fixes the issue for some users, but our SQL is still hitting the 10,000 limit
- This is a temporary workaround that will break when sqlparse patches are needed

**Alternatives considered**: Pin to sqlparse <0.5.4 - this would lose years of security patches

### Option 2: dbt conftest.py Hook

**Decision**: CONSIDERED - Viable but narrow scope

**Rationale**:
- pytest uses `conftest.py` for configuration
- dbt uses pytest internally for some operations
- Adding `dbt/conftest.py` with sqlparse configuration would run before tests

**Alternatives considered**: This only works for dbt test operations, not dbt run/build

### Option 3: usercustomize.py / sitecustomize.py

**Decision**: REJECTED

**Rationale**:
- `sitecustomize.py` runs before any Python code in the interpreter
- Would require modifying site-packages, which violates NFR-006 (no permanent environment changes)
- Conflicts with other customizations

**Alternatives considered**: `usercustomize.py` in PYTHONUSERBASE - complex setup

### Option 4: Environment Variable via DbtRunner

**Decision**: REJECTED

**Rationale**:
- sqlparse does NOT support environment variable configuration for MAX_GROUPING_TOKENS
- Would require forking sqlparse or submitting upstream PR (long timeline)

**Alternatives considered**: Proposing upstream PR to sqlparse - viable long-term but not immediate fix

### Option 5: Python -c Wrapper Script

**Decision**: REJECTED

**Rationale**:
- Replace dbt executable with `python -c "import sqlparse...; import dbt; dbt.main()"`
- Complex, fragile, and breaks dbt's argument parsing

**Alternatives considered**: Shell wrapper script - same issues

### Option 6: dbt Initialization Hook via conftest.py in pytest root

**Decision**: CONSIDERED - Viable for pytest-based testing

**Rationale**:
- Adding conftest.py at project root with sqlparse configuration
- pytest imports conftest.py before running tests

**Alternatives considered**: Only works for pytest, not production dbt commands

### Option 7: PYTHONSTARTUP Environment Variable

**Decision**: REJECTED

**Rationale**:
- PYTHONSTARTUP only runs for interactive Python sessions
- dbt runs in non-interactive mode

### Option 8: sitecustomize.py in Virtual Environment

**Decision**: SELECTED - Best balance of reliability and scope

**Rationale**:
- Python's `sitecustomize.py` is automatically imported when the interpreter starts
- Placing it in `.venv/lib/python3.11/site-packages/` configures sqlparse BEFORE dbt loads
- Works for ALL Python invocations in the venv (dbt run, dbt test, dbt build, etc.)
- Scope is limited to the project's virtual environment (satisfies NFR-006)
- Idempotent and graceful fallback for older sqlparse versions

**Implementation**:
```python
# .venv/lib/python3.11/site-packages/sitecustomize.py
"""Configure sqlparse token limits for large dbt models."""
try:
    import sqlparse.engine.grouping
    sqlparse.engine.grouping.MAX_GROUPING_TOKENS = 50000
except (ImportError, AttributeError):
    pass
```

**Alternatives considered**:
- dbt adapter hook - would require modifying dbt-duckdb internals
- dbt pre-hook - runs after compilation, too late

### Option 9: pyproject.toml build hook

**Decision**: CONSIDERED - Good for automated setup

**Rationale**:
- Add a post-install hook to `pyproject.toml` that creates sitecustomize.py
- Ensures configuration is applied when developers run `pip install -e .`

**Implementation**: Use `[project.scripts]` entry point or custom build backend

**Alternatives considered**: Manual documentation - less reliable

## Selected Approach

### Primary Solution: sitecustomize.py in venv + Installation Script

1. **Create sitecustomize.py**: Script that configures sqlparse limits
2. **Modify setup process**: Ensure sitecustomize.py is installed during `pip install -e .`
3. **Keep __init__.py fix**: As defense-in-depth for any in-process dbt calls
4. **Add documentation**: Update CLAUDE.md with troubleshooting guidance

### Implementation Plan

1. **Phase 1**: Create `scripts/install_sqlparse_fix.py` helper
2. **Phase 2**: Update `pyproject.toml` post-install hook
3. **Phase 3**: Update CLAUDE.md with documentation
4. **Phase 4**: Add tests to verify fix works

### Verification

```bash
# Test that sitecustomize.py is loaded
python -c "import sqlparse.engine.grouping; print(f'MAX_GROUPING_TOKENS={sqlparse.engine.grouping.MAX_GROUPING_TOKENS}')"
# Expected: MAX_GROUPING_TOKENS=50000

# Test dbt subprocess
cd dbt && dbt run --select fct_workforce_snapshot --vars '{"simulation_year": 2026}'
# Expected: Success without token errors
```

## Sources

- [sqlparse Issue #828 - MAX_GROUPING_TOKENS limit](https://github.com/andialbrecht/sqlparse/issues/828)
- [dbt-core Issue #12303 - sqlparse 0.5.5 token limit bug](https://github.com/dbt-labs/dbt-core/issues/12303)
- [dbt Discourse - Maximum number of tokens exceeded](https://discourse.getdbt.com/t/dbt-run-error-maximum-number-of-tokens-exceeded/20495)
- [sqlparse API Documentation](https://sqlparse.readthedocs.io/en/latest/api.html)
- [Python sitecustomize.py Documentation](https://docs.python.org/3/library/site.html)
