# Troubleshooting Guide for Work Machine Setup

This guide helps resolve common issues when setting up Fidelity PlanAlign Engine on your work machine after pulling the E072/E074/E075 changes.

## Issue 1: "No module named planalign_orchestrator.checkpoint_manager"

### Cause
This error occurs due to:
1. **Stale Python cache** (.pyc files from old code structure)
2. **Package not installed in editable mode** after pulling changes
3. **Wrong Python environment** activated

### Solution

Run these commands **in order**:

```bash
# 1. Clear all Python cache
./scripts/clear_cache.sh

# Or manually:
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# 2. Make sure you're in the virtual environment
source venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate    # Windows

# 3. Reinstall the package in editable mode
pip install -e .

# 4. Verify installation
python -c "from planalign_orchestrator.checkpoint_manager import CheckpointManager; print('✅ Import successful')"

# 5. Test the CLI
planwise --help
```

## Issue 2: Import errors after E072 refactoring

### Old Import (WRONG)
```python
from planalign_orchestrator.pipeline import PipelineOrchestrator
```

### New Import (CORRECT)
```python
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
```

### Fix
The code has been updated, but if you modified any custom scripts, update them to use the correct import.

## Issue 3: "planwise command not found"

### Solution
```bash
# Reinstall in editable mode
pip install -e .

# Verify planwise is in your PATH
which planwise

# If not found, use the full path
venv/bin/planwise --help
```

## Issue 4: Git-ignored database files

### What happened
The simulation creates database files that are git-ignored:
- `dbt/simulation.duckdb`
- `data/parquet/events/simulation_year=*/`

### Solution
These files will be created when you run your first simulation:

```bash
planalign simulate 2025-2026
```

## Issue 5: Work machine-specific performance

### Optimization for work laptops
Edit `config/simulation_config.yaml`:

```yaml
multi_year:
  optimization:
    level: "medium"        # Not "high"
    max_workers: 1         # Single-threaded
    batch_size: 500        # Smaller batches
    memory_limit_gb: 4.0   # Conservative limit
```

## Quick Setup Checklist for Work Machine

Run this sequence after `git pull`:

```bash
# 1. Clear cache
./scripts/clear_cache.sh

# 2. Activate virtual environment
source venv/bin/activate  # macOS/Linux

# 3. Update dependencies (in case requirements changed)
pip install -r requirements.txt -r requirements-dev.txt

# 4. Reinstall package
pip install -e .

# 5. Verify imports
python -c "
from planalign_orchestrator.checkpoint_manager import CheckpointManager
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from planalign_orchestrator.exceptions import NavigatorError
from planalign_orchestrator.error_catalog import get_error_catalog
print('✅ All critical imports successful')
"

# 6. Test CLI
planalign health

# 7. Run a quick simulation test
planalign simulate 2025 --dry-run

# 8. Run full 2-year simulation
planalign simulate 2025-2026
```

## Testing the Workforce Growth Bug Fix

After setup is complete, test the growth calculation:

```bash
# Run 2-year simulation
planalign simulate 2025-2026

# Check the output for:
# - Total employees should grow year-over-year
# - Active employees should grow by ~3% annually
# - CAGR should be around 2.9-3.0%

# Expected results:
# Year 2025: ~9,900 total, ~6,970 active
# Year 2026: ~10,200 total, ~7,170 active
# CAGR: ~2.9%
```

## Debugging Tips

### Check which Python is being used
```bash
which python
python --version  # Should be 3.11.x
```

### Check if package is installed
```bash
pip show planwise-navigator
# Should show: Location: /path/to/planalign_engine
```

### Check module accessibility
```bash
python -c "import planalign_orchestrator; print(planalign_orchestrator.__file__)"
# Should show: /path/to/planalign_engine/planalign_orchestrator/__init__.py
```

### Verify all new modules exist
```bash
ls -la planalign_orchestrator/pipeline/
# Should show:
# - __init__.py
# - workflow.py
# - event_generation_executor.py
# - state_manager.py
# - year_executor.py
# - hooks.py
# - data_cleanup.py
```

## Still Having Issues?

If the above steps don't work:

1. **Create a fresh virtual environment**:
   ```bash
   rm -rf venv
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt -r requirements-dev.txt
   pip install -e .
   ```

2. **Check for conflicting installations**:
   ```bash
   pip list | grep planwise
   pip list | grep navigator
   ```

3. **Verify file permissions**:
   ```bash
   ls -la planalign_orchestrator/*.py
   # All files should be readable (r--)
   ```

4. **Check for syntax errors**:
   ```bash
   python -m py_compile planalign_orchestrator/checkpoint_manager.py
   ```

## Reference: What Changed in E072

The major structural change was splitting the monolithic `pipeline.py` into:

- **Old structure**: `planalign_orchestrator/pipeline.py` (2,478 lines)
- **New structure**:
  - `planalign_orchestrator/pipeline_orchestrator.py` (1,220 lines) - Main coordinator
  - `planalign_orchestrator/pipeline/` (package with 6 modules)

This is why clearing the Python cache is critical - old .pyc files may reference the old structure.

## Expected First Run Output

After successful setup, `planalign simulate 2025-2026` should show:

```
🚀 Running 2-year simulation
💰 Compensation Parameters:
⏳ Executing simulation with progress monitoring...

🚀 Fidelity PlanAlign Engine Multi-Year Simulation
   Period: 2025 → 2026 (2 years)
   Random Seed: 42
   Target Growth: 3.0%

🔄 Starting simulation year 2025
...
✅ Multi-year simulation completed successfully
```

Total duration should be around 90 seconds.
