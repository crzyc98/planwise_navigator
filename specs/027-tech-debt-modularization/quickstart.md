# Quickstart: Technical Debt Modularization

## Overview

This refactoring splits 4 large Python files into focused module packages while maintaining 100% backward compatibility.

## Before You Start

Ensure tests pass on the current codebase:

```bash
pytest -m fast
planalign health
```

## Refactoring Pattern

Each package follows this structure:

```python
# package/__init__.py
"""Package description."""
from .data_models import Model1, Model2
from .main_class import MainClass

__all__ = ["Model1", "Model2", "MainClass"]
```

```python
# original_file.py (backward compat wrapper)
"""Backward compatibility wrapper. Use package/ directly for new code."""
from package import Model1, Model2, MainClass

__all__ = ["Model1", "Model2", "MainClass"]
```

## Verification After Each Phase

```bash
# 1. Tests pass
pytest -m fast

# 2. System health
planalign health

# 3. Import compatibility
python -c "from planalign_orchestrator.performance_monitor import PerformanceMonitor"
```

## Phase Order

1. `monitoring/` - Split performance_monitor.py (lowest risk)
2. `resources/` - Split resource_manager.py (medium complexity)
3. `reports/` - Split reports.py (straightforward)
4. `simulation/` - Split simulation_service.py (highest complexity)

## Key Rules

- **Foundation first**: Create `data_models.py` before other modules
- **Relative imports**: Use `from .module import Class` within packages
- **Re-export everything**: Include all public symbols in `__init__.py`
- **Test after each module**: Don't proceed if tests fail
