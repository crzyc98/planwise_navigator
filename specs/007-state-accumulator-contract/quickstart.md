# Quickstart: Temporal State Accumulator Contract

**Feature**: 007-state-accumulator-contract
**Date**: 2025-12-14

## Overview

This feature formalizes the temporal state accumulator pattern where Year N depends on Year N-1 data. The system now validates year dependencies at runtime and fails fast with clear error messages if dependencies are violated.

## Quick Reference

### What Changed

1. **New validation before STATE_ACCUMULATION**: Pipeline checks that prior year data exists before executing state accumulator models
2. **New error type**: `YearDependencyError` provides actionable messages when validation fails
3. **New registry**: `StateAccumulatorRegistry` tracks all temporal accumulator models

### What Stays the Same

- Year 2025 → 2026 → 2027 execution order (now enforced, not just expected)
- `int_enrollment_state_accumulator` behavior (consolidates latest event per employee)
- `int_deferral_rate_state_accumulator` behavior (reads previous year correctly)
- Checkpoint recovery flow (now with dependency chain validation)

---

## Usage Examples

### Normal Multi-Year Simulation (No Change)

```bash
# This works exactly as before
planalign simulate 2025-2027 --verbose

# Output includes validation confirmations:
# ✅ Year dependency validation passed for year 2026
# ✅ Year dependency validation passed for year 2027
```

### Attempting Out-of-Order Execution (New Behavior)

```bash
# This now fails fast instead of producing silent corruption
planalign simulate 2027 --start-year 2027

# Error output:
# ❌ YearDependencyError: Year 2027 depends on year 2026 data which has not been executed.
#
# Missing data for accumulators:
#   - int_enrollment_state_accumulator (0 rows for year 2026)
#   - int_deferral_rate_state_accumulator (0 rows for year 2026)
#
# Resolution: Run years in sequence: 2025 → 2026 → 2027
#             Or use --start-year 2026 if resuming from checkpoint.
```

### Checkpoint Recovery with Validation (New Behavior)

```bash
# Resume from checkpoint - now validates dependency chain first
planalign simulate 2027 --resume-from-checkpoint

# If year 2026 data was deleted:
# ❌ YearDependencyError: Checkpoint dependency chain broken.
#    Year 2027 checkpoint exists but year 2026 data is missing.
#
# Resolution: Re-run simulation from year 2026.
```

---

## For Developers

### Adding a New State Accumulator

If you create a new dbt model that follows the temporal state accumulator pattern (reads from `{{ this }}` for prior year data), register it:

```python
# In planalign_orchestrator/state_accumulator/__init__.py

from .contract import StateAccumulatorContract
from .registry import StateAccumulatorRegistry

# Register your new accumulator
StateAccumulatorRegistry.register(
    StateAccumulatorContract(
        model_name="int_your_new_accumulator",
        table_name="int_your_new_accumulator",
        prior_year_column="simulation_year",
        start_year_source="int_baseline_workforce",
        description="Tracks [what] across simulation years"
    )
)
```

### Testing Year Dependency Validation

```python
# tests/unit/test_state_accumulator_registry.py

from planalign_orchestrator.state_accumulator import (
    StateAccumulatorRegistry,
    StateAccumulatorContract,
    YearDependencyValidator,
    YearDependencyError,
)

def test_validation_fails_for_missing_prior_year(empty_db, minimal_config):
    """Test that validation fails when prior year data is missing."""
    validator = YearDependencyValidator(
        db_manager=empty_db,
        start_year=2025
    )

    with pytest.raises(YearDependencyError) as exc_info:
        validator.validate_year_dependencies(2026)

    assert "year 2025 data" in str(exc_info.value)

def test_validation_skipped_for_start_year(empty_db, minimal_config):
    """Test that start year has no prior dependency."""
    validator = YearDependencyValidator(
        db_manager=empty_db,
        start_year=2025
    )

    # Should not raise - start year has no dependency
    validator.validate_year_dependencies(2025)
```

### Running Tests

```bash
# Fast unit tests only
pytest -m fast tests/unit/test_state_accumulator_registry.py

# Integration tests (requires database)
pytest tests/integration/test_year_dependency_validation.py

# Full test suite
pytest --cov=planalign_orchestrator.state_accumulator
```

---

## API Reference

### StateAccumulatorContract

```python
from planalign_orchestrator.state_accumulator import StateAccumulatorContract

contract = StateAccumulatorContract(
    model_name="int_enrollment_state_accumulator",  # Required: dbt model name
    table_name="int_enrollment_state_accumulator",  # Required: database table
    prior_year_column="simulation_year",             # Default: "simulation_year"
    start_year_source="int_baseline_workforce",      # Required: initial state source
    description="Tracks enrollment state"            # Optional: documentation
)
```

### StateAccumulatorRegistry

```python
from planalign_orchestrator.state_accumulator import StateAccumulatorRegistry

# Register a contract
StateAccumulatorRegistry.register(contract)

# Get a contract by name
contract = StateAccumulatorRegistry.get("int_enrollment_state_accumulator")

# List all registered model names
names = StateAccumulatorRegistry.list_all()
# ['int_deferral_rate_state_accumulator', 'int_enrollment_state_accumulator']

# Get all registered table names
tables = StateAccumulatorRegistry.get_registered_tables()
# ['int_enrollment_state_accumulator', 'int_deferral_rate_state_accumulator']
```

### YearDependencyValidator

```python
from planalign_orchestrator.state_accumulator import YearDependencyValidator

validator = YearDependencyValidator(
    db_manager=my_db_manager,
    start_year=2025
)

# Validate before executing year 2026
validator.validate_year_dependencies(2026)  # Raises if 2025 data missing

# Get detailed missing year info
missing = validator.get_missing_years(2026)
# {'int_enrollment_state_accumulator': 0}  # 0 rows = missing

# Validate checkpoint dependency chain
validator.validate_checkpoint_dependencies(checkpoint_year=2027)
```

### YearDependencyError

```python
from planalign_orchestrator.state_accumulator import YearDependencyError

try:
    validator.validate_year_dependencies(2027)
except YearDependencyError as e:
    print(e.year)            # 2027
    print(e.missing_tables)  # {'int_enrollment_state_accumulator': 0, ...}
    print(e.resolution_hint) # "Execute year 2026 before year 2027"
```

---

## Troubleshooting

### Error: "Year X depends on year X-1 data which has not been executed"

**Cause**: You're trying to run a simulation year before its prerequisite year has been executed.

**Fix**: Run years in sequence from your start year:
```bash
planalign simulate 2025-2027  # Runs all years in order
```

### Error: "Checkpoint dependency chain broken"

**Cause**: You're resuming from a checkpoint, but some intermediate year's data was deleted from the database.

**Fix**: Either:
1. Re-run simulation from the missing year: `planalign simulate 2025-2027`
2. Or restore the database from backup if available

### Warning: New accumulator not being validated

**Cause**: You created a new state accumulator model but didn't register it.

**Fix**: Add registration in `planalign_orchestrator/state_accumulator/__init__.py` (see "Adding a New State Accumulator" above).

---

## Related Documentation

- [Specification](./spec.md) - Full feature requirements
- [Implementation Plan](./plan.md) - Architecture and design decisions
- [Data Model](./data-model.md) - Entity definitions and relationships
- [API Contracts](./contracts/state_accumulator_api.py) - Python interfaces
