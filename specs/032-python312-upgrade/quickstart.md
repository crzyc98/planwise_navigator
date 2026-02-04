# Quickstart: Python 3.12 Upgrade Implementation

**Feature**: 032-python312-upgrade
**Estimated Effort**: 30-60 minutes
**Prerequisites**: Research complete (see research.md)

## Overview

This guide provides step-by-step instructions for upgrading the Fidelity PlanAlign Engine project to support Python 3.12.x while maintaining backward compatibility with Python 3.11.x.

## Implementation Steps

### Step 1: Update pyproject.toml (10 min)

**File**: `/workspace/pyproject.toml`

1. **Update Python version constraint** (line 6):
   ```toml
   requires-python = ">=3.11,<3.14"
   ```

2. **Update dev dependencies** (in `[project.optional-dependencies]` section):
   ```toml
   dev = [
       # ... keep existing ...
       "black>=24.3.0",      # was ==23.9.1
       "mypy>=1.10.0",       # was ==1.5.1
       "ipython>=8.18.0",    # was ==8.14.0
       "jupyter>=1.1.1",     # was ==1.0.0
   ]
   ```

### Step 2: Update requirements-dev.txt (5 min)

**File**: `/workspace/requirements-dev.txt`

Update the following lines:
```text
black>=24.3.0
mypy>=1.10.0
ipython>=8.18.0
jupyter>=1.1.1
```

### Step 3: Update CLAUDE.md (15 min)

**File**: `/workspace/CLAUDE.md`

1. **Technology Stack table** (Section 2):
   - Change `Python | CPython | 3.11.x` to `Python | CPython | 3.12.x`

2. **Quick Start section** (Section 3):
   - Update `uv venv .venv --python python3.11` to `uv venv .venv --python python3.12`

3. **Search and replace** all remaining Python version references:
   - Replace `Python 3.11` with `Python 3.12` (primary references)
   - Keep any `3.11` that appear in version constraint contexts (e.g., `>=3.11`)

4. **Active Technologies section** (near end):
   - Update all `Python 3.11` entries to `Python 3.12`

### Step 4: Update README.md (15 min)

**File**: `/workspace/README.md`

1. **Prerequisites section**:
   - Change "Python 3.11 or 3.12 (3.12 recommended)" to "Python 3.12 (recommended)"
   - Update note about Python 3.13+ if present

2. **Installation (Windows) section**:
   - Change `winget install --id Python.Python.3.12` (already correct)
   - Update verification command if needed

3. **Installation (macOS/Linux) section**:
   - Change `python3.11 -m venv` to `python3.12 -m venv`

4. **Technology Stack table**:
   - Update Python version from `3.11.x` to `3.12.x`

5. **Troubleshooting section**:
   - Update any Python 3.11 references to 3.12
   - Update virtual environment examples

### Step 5: Verify Installation (10 min)

Run these commands to verify the upgrade:

```bash
# 1. Create fresh Python 3.12 environment
python3.12 -m venv .venv-test
source .venv-test/bin/activate  # or .venv-test\Scripts\activate on Windows

# 2. Install project
pip install -e ".[dev]"

# 3. Verify imports
python -c "import planalign_orchestrator; import planalign_cli; import planalign_api; print('✅ Imports OK')"

# 4. Run health check
planalign health

# 5. Run fast tests
pytest -m fast

# 6. Verify dev tools
black --version
mypy --version
ipython --version

# 7. Cleanup test environment
deactivate
rm -rf .venv-test
```

### Step 6: Update CHANGELOG.md (5 min)

**File**: `/workspace/CHANGELOG.md`

Add entry under appropriate version:
```markdown
### Changed
- Updated Python version requirement to recommend Python 3.12.x (maintaining 3.11 compatibility)
- Upgraded development dependencies for Python 3.12 compatibility:
  - black 23.9.1 → 24.3.0+
  - mypy 1.5.1 → 1.10.0+
  - ipython 8.14.0 → 8.18.0+
  - jupyter 1.0.0 → 1.1.1+
```

## Validation Checklist

After completing all steps, verify:

- [ ] `pip install -e ".[dev]"` succeeds on Python 3.12
- [ ] `pip install -e ".[dev]"` succeeds on Python 3.11 (backward compat)
- [ ] `planalign health` reports success
- [ ] `pytest -m fast` passes all tests
- [ ] `planalign studio` starts without errors
- [ ] Documentation references Python 3.12 as recommended version
- [ ] No "3.11" appears as primary version (only in compatibility contexts)

## Rollback Plan

If issues are discovered:

1. Revert pyproject.toml changes
2. Revert requirements-dev.txt changes
3. Keep documentation changes (they're forward-compatible)
4. Re-run `pip install -e ".[dev]"` to restore old versions

## Files Modified Summary

| File | Changes |
|------|---------|
| `pyproject.toml` | Python constraint, dev dependency versions |
| `requirements-dev.txt` | Dev dependency versions |
| `CLAUDE.md` | Technology stack, quick start, active technologies |
| `README.md` | Prerequisites, installation instructions, troubleshooting |
| `CHANGELOG.md` | Version history entry |
