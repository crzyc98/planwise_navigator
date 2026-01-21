# Quickstart: Remove Polars Event Factory

**Branch**: `024-remove-polars-pipeline`

## Overview

This feature removes the Polars event factory system. Since this is a deletion task (not new feature development), the quickstart focuses on verification steps rather than usage examples.

## Pre-Implementation Baseline

Before starting, record current state:

```bash
# Count test files
ls tests/test_*.py | wc -l

# Run baseline tests
pytest -m fast
cd dbt && dbt test --threads 1 && cd ..

# Check Polars references exist (should find matches)
grep -l "polars_event_factory" planalign_orchestrator/*.py
grep -l "polars_state_pipeline" planalign_orchestrator/*.py
```

## Post-Implementation Verification

### 1. CLI Verification

```bash
# Should NOT show --use-polars-engine or --polars-output
planalign simulate --help

# Should complete with SQL mode only
planalign simulate 2025

# Multi-year simulation
planalign simulate 2025-2027
```

### 2. Test Suite Verification

```bash
# Fast tests should pass (fewer tests due to Polars test deletion)
pytest -m fast

# dbt tests should pass
cd dbt && dbt test --threads 1 && cd ..
```

### 3. Codebase Verification

```bash
# Should return NO matches (all Polars files deleted)
find planalign_orchestrator -name "polars_*.py" 2>/dev/null

# Should return NO matches (all references removed)
grep -r "polars_event_factory" planalign_orchestrator/ 2>/dev/null
grep -r "polars_state_pipeline" planalign_orchestrator/ 2>/dev/null
grep -r "polars_integration" planalign_orchestrator/ 2>/dev/null

# Should return NO matches (tests deleted)
find tests -name "test_polars_*.py" 2>/dev/null
find tests -name "test_e077_*.py" 2>/dev/null
```

### 4. Frontend Verification

```bash
# Start Studio
planalign studio

# Open browser to http://localhost:5173
# Navigate to Configuration page
# Verify NO engine selector (Polars/Pandas radio buttons)
```

### 5. Legacy Workspace Test

```bash
# Create a workspace config with legacy Polars setting
echo '{"advanced": {"engine": "polars"}}' > /tmp/legacy_config.json

# The system should ignore this and use SQL mode without error
# (Implementation detail: verify no errors in simulation_service.py)
```

## Success Criteria Checklist

- [ ] `planalign simulate --help` shows no Polars-related options
- [ ] `planalign simulate 2025-2027` completes successfully
- [ ] `pytest -m fast` passes
- [ ] `dbt test --threads 1` passes
- [ ] No `polars_*.py` files in `planalign_orchestrator/`
- [ ] No Polars imports in remaining code
- [ ] Studio UI has no engine selector
- [ ] Legacy workspaces with `engine: 'polars'` don't cause errors

## Estimated Code Reduction

| Category | Lines Removed |
|----------|---------------|
| Core Polars modules | ~4,389 |
| Polars tests | ~3,570 |
| Benchmark scripts | ~1,935 |
| **Total** | **~9,894** |

Plus refactoring in 13 modified files (~500-800 lines of Polars-specific code removed).
