# Quickstart: Orchestrator Modularization Phase 2

**Feature**: 034-orchestrator-modularization
**Date**: 2026-02-05

## Overview

This guide helps developers implement the orchestrator modularization by extracting setup and validation code into focused modules.

## Prerequisites

- Python 3.11 virtual environment activated
- All existing tests passing (`pytest -m fast` succeeds)
- Working directory: `/workspace`

## Quick Verification

```bash
# Verify current state before starting
source .venv/bin/activate
pytest -m fast  # Should pass all 87 tests
wc -l planalign_orchestrator/pipeline_orchestrator.py  # Should show ~1218 lines
```

## Implementation Steps

### Step 1: Create orchestrator_setup.py

```bash
# Create the new module file
touch planalign_orchestrator/orchestrator_setup.py
```

The module should contain:
- `setup_memory_manager()` - Extract from `_setup_adaptive_memory_manager()`
- `setup_parallelization()` - Extract from `_setup_model_parallelization()`
- `setup_hazard_cache()` - Extract from `_setup_hazard_cache_manager()`
- `setup_performance_monitor()` - Extract from `_setup_performance_monitoring()`

### Step 2: Update PipelineOrchestrator.__init__()

Replace inline setup calls with function calls:

```python
# Before (inline)
self._setup_adaptive_memory_manager()

# After (delegated)
from .orchestrator_setup import setup_memory_manager
self.memory_manager = setup_memory_manager(self.config, self.reports_dir, self.verbose)
```

### Step 3: Verify Phase 1

```bash
pytest -m fast
planalign simulate 2025 --dry-run
```

### Step 4: Create pipeline/stage_validator.py

```bash
touch planalign_orchestrator/pipeline/stage_validator.py
```

The module should contain the `StageValidator` class with:
- `validate_stage()` - Main entry point
- `_validate_foundation()` - FOUNDATION stage validation
- `_validate_event_generation()` - EVENT_GENERATION stage validation
- `_validate_state_accumulation()` - STATE_ACCUMULATION stage validation

### Step 5: Update _execute_year_workflow()

Replace inline validation with StageValidator:

```python
# Before (inline)
self._run_stage_validation(stage, year, fail_on_validation_error)

# After (delegated)
self.stage_validator.validate_stage(stage, year, fail_on_validation_error)
```

### Step 6: Update Exports

Update `planalign_orchestrator/pipeline/__init__.py`:
```python
from .stage_validator import StageValidator

__all__ = [
    # ... existing exports ...
    "StageValidator",
]
```

### Step 7: Final Verification

```bash
# Full test suite
pytest

# Full simulation
planalign simulate 2025-2027

# Line count verification
wc -l planalign_orchestrator/pipeline_orchestrator.py     # Target: 650-700
wc -l planalign_orchestrator/orchestrator_setup.py        # Target: ~250
wc -l planalign_orchestrator/pipeline/stage_validator.py  # Target: ~150

# API verification
python -c "from planalign_orchestrator import create_orchestrator; print('OK')"
```

## Success Criteria Checklist

- [ ] `pipeline_orchestrator.py` reduced to 650-700 lines
- [ ] `orchestrator_setup.py` contains ~250 lines
- [ ] `pipeline/stage_validator.py` contains ~150 lines
- [ ] All 256+ existing tests pass
- [ ] `planalign simulate 2025 --dry-run` succeeds
- [ ] Public API unchanged (constructor signature, properties)

## Troubleshooting

### Import Errors

If you see `ImportError` after extraction:
1. Check that new modules have correct imports at the top
2. Verify `__init__.py` exports are updated
3. Ensure no circular imports (new modules shouldn't import from `pipeline_orchestrator.py`)

### Test Failures

If tests fail after extraction:
1. Check that function signatures match exactly
2. Verify verbose output messages are preserved
3. Ensure return values are identical (especially `None` on failure)

### Line Count Off

If line counts don't match targets:
1. The targets are approximate (~250, ~150)
2. Minor variations (±20 lines) are acceptable
3. Focus on the total reduction (1,218 → 650-700)
