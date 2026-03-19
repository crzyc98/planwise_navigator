# Developer Quickstart: SimulationConfig Deserialization Fix

**Feature**: 079-fix-config-deser
**Target Audience**: Developers implementing the fix
**Time to Setup**: ~10 minutes

---

## Overview

This quickstart guides you through testing and implementing the three-step fix for SimulationConfig deserialization failures in the result handler.

**What you'll do**:
1. ✅ Understand the current failure mode
2. ✅ Set up test cases for each step
3. ✅ Implement error logging improvement
4. ✅ Implement robust key filtering
5. ✅ Verify upstream serialization

---

## Prerequisites

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Install development dependencies
uv pip install -e ".[dev]"

# Verify pytest is available
pytest --version
```

---

## Step 0: Reproduce the Current Error

### 0a. Run Existing Tests

```bash
# Run fast test suite to verify baseline
pytest -m fast --tb=short
```

Look for any tests related to config deserialization. You may find tests already exist that demonstrate the failure.

### 0b. Examine Current Error Handling

Navigate to the error location:

```bash
# Look at the current error handling
cat planalign_api/services/simulation/result_handlers.py | grep -A 5 "from_dict"
```

**Current code** (lines 66-68):
```python
try:
    sim_config = SimulationConfig.from_dict(config)
except Exception as e:
    logger.warning(f"Could not create SimulationConfig from dict: {e}")
```

**Problem**: The error message is truncated to just the method name "from_dict".

---

## Step 1: Test Error Logging Improvement

### 1a. Create Unit Test for Error Logging

Create file: `tests/unit/test_config_deser_error_logging.py`

```python
"""Test error logging for config deserialization failures."""

import logging
import pytest
from decimal import Decimal
from config.schema import SimulationConfig

def test_from_dict_with_decimal_value_error_message(caplog):
    """Test that error logging includes exception type and details.

    This test verifies Step 1 of the fix: improved error logging.
    """
    # Create config dict with Decimal instead of float
    invalid_config = {
        "start_year": 2025,
        "end_year": 2026,
        "cola_rate": Decimal("0.025"),  # Decimal, not float
    }

    # Simulate the result handler's try-except block
    with caplog.at_level(logging.WARNING):
        try:
            config = SimulationConfig.from_dict(invalid_config)
        except Exception as e:
            # NEW: Improved error logging that captures exception details
            error_msg = f"Could not create SimulationConfig from dict: {type(e).__name__}: {e}"
            logging.getLogger("result_handlers").warning(error_msg)

    # Assert that error log contains useful information
    # Should include "TypeError" or "ValidationError", not just "from_dict"
    assert "TypeError" in caplog.text or "ValidationError" in caplog.text
    assert "Could not create" in caplog.text

def test_from_dict_with_unknown_key_error_message(caplog):
    """Test error logging for unknown keys."""
    config_with_extra = {
        "start_year": 2025,
        "end_year": 2026,
        "unknown_field": "should_be_ignored",  # Unknown key
    }

    # After Step 2 implementation, this should not raise
    # But for Step 1, we just want good error messages
    with caplog.at_level(logging.WARNING):
        try:
            config = SimulationConfig.from_dict(config_with_extra)
        except Exception as e:
            error_msg = f"Could not create SimulationConfig from dict: {type(e).__name__}: {e}"
            logging.getLogger("result_handlers").warning(error_msg)

    # Error message should be detailed enough to diagnose the problem
    assert len(caplog.text) > 50  # Message should be informative
```

### 1b. Run the Test

```bash
pytest tests/unit/test_config_deser_error_logging.py -v
```

Expected result: Tests should fail initially (demonstrating the problem), then pass after implementation.

---

## Step 2: Test Robust Key Filtering

### 2a. Create Unit Test for from_dict() Robustness

Create file: `tests/unit/test_config_from_dict.py`

```python
"""Test SimulationConfig.from_dict() robustness."""

import pytest
from config.schema import SimulationConfig

class TestFromDictRobustness:
    """Test that from_dict() handles various dict shapes gracefully."""

    def test_from_dict_with_all_valid_fields(self):
        """Test basic case: all valid fields."""
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
        }

        # Should succeed without filtering
        config = SimulationConfig.from_dict(config_dict)
        assert config.start_year == 2025
        assert config.end_year == 2026

    def test_from_dict_filters_unknown_keys(self):
        """Test that unknown keys are silently filtered.

        This tests Step 2 of the fix: key filtering.
        """
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            "random_seed": 42,
            "unknown_field_1": "should_be_ignored",
            "unknown_field_2": 999,
            "extra_scenario_override": {"some": "data"},
        }

        # Should succeed with key filtering (no exception)
        config = SimulationConfig.from_dict(config_dict)
        assert config.start_year == 2025
        # Unknown fields should not be accessible
        assert not hasattr(config, "unknown_field_1")

    def test_from_dict_with_missing_optional_fields(self):
        """Test that missing optional fields use defaults."""
        config_dict = {
            "start_year": 2025,
            "end_year": 2026,
            # Missing: random_seed, cola_rate, merit_budget_pct, etc.
        }

        # Should succeed using Pydantic defaults
        config = SimulationConfig.from_dict(config_dict)
        assert config.random_seed == 42  # Default value
        assert config.cola_rate == 0.025  # Default value

    def test_from_dict_with_missing_required_field(self):
        """Test that missing required fields raise ValidationError."""
        config_dict = {
            "start_year": 2025,
            # Missing: end_year (required)
        }

        # Should raise ValidationError
        with pytest.raises(Exception):  # ValidationError from Pydantic
            SimulationConfig.from_dict(config_dict)
```

### 2b. Run the Test

```bash
pytest tests/unit/test_config_from_dict.py -v
```

Expected: Key filtering tests should pass after Step 2 implementation.

---

## Step 3: Integration Test for Serialization Roundtrip

### 3a. Create Integration Test

Create file: `tests/integration/test_config_serialization_roundtrip.py`

```python
"""Integration test: config serialization and deserialization roundtrip."""

import pytest
from decimal import Decimal
from config.schema import SimulationConfig

def test_config_roundtrip_with_model_dump_json():
    """Test that config survives serialization roundtrip with model_dump(mode='json').

    This tests Step 3 of the fix: upstream serialization with Decimal→float conversion.
    """
    # Create original config
    original_config = SimulationConfig(
        start_year=2025,
        end_year=2026,
        random_seed=42,
        cola_rate=0.025,
    )

    # Serialize using model_dump(mode='json') - converts Decimal→float
    serialized_dict = original_config.model_dump(mode='json')

    # Verify Decimals are converted to floats in serialized form
    # (if any fields are Decimal in the original)
    for key, value in serialized_dict.items():
        if isinstance(value, float):
            assert not isinstance(value, Decimal)

    # Deserialize using from_dict() - should succeed without type errors
    reconstructed_config = SimulationConfig.from_dict(serialized_dict)

    # Verify reconstructed config matches original
    assert reconstructed_config.start_year == original_config.start_year
    assert reconstructed_config.end_year == original_config.end_year
    assert reconstructed_config.cola_rate == original_config.cola_rate

def test_config_roundtrip_with_scenario_overrides():
    """Test roundtrip with scenario-specific overrides.

    Simulates the Studio merging scenario overrides with base config.
    """
    original_config = SimulationConfig(
        start_year=2025,
        end_year=2026,
        target_growth_rate=0.03,
    )

    # Simulate Studio scenario override
    scenario_override = {
        "target_growth_rate": 0.05,  # Override
        "random_seed": 123,
        "scenario_name": "high_growth",  # Extra field from Studio
        "metadata": {"ui_settings": "..."},  # Extra field
    }

    # Serialize and merge (simulating Studio behavior)
    serialized = original_config.model_dump(mode='json')
    merged = {**serialized, **scenario_override}

    # Should survive deserialization despite extra keys
    reconstructed = SimulationConfig.from_dict(merged)

    assert reconstructed.target_growth_rate == 0.05
    assert reconstructed.start_year == 2025  # Original value preserved
```

### 3b. Run the Test

```bash
pytest tests/integration/test_config_serialization_roundtrip.py -v
```

Expected: Should pass after Steps 2-3 implementation.

---

## Implementation Checklist

Use this checklist as you implement each step:

### Step 1: Error Logging

- [ ] Open `planalign_api/services/simulation/result_handlers.py`
- [ ] Locate lines 66-68 (try-except block for from_dict)
- [ ] Change error logging to: `logger.warning(f"Could not create SimulationConfig from dict: {type(e).__name__}: {e}")`
- [ ] Optionally add `exc_info=True` to logger call for full traceback
- [ ] Run `pytest tests/unit/test_config_deser_error_logging.py -v` to verify
- [ ] Run `pytest -m fast` to ensure no regressions

### Step 2: Key Filtering

- [ ] Open `config/schema.py`
- [ ] Add classmethod to SimulationConfig:
  ```python
  @classmethod
  def from_dict(cls, data: dict) -> "SimulationConfig":
      """Create SimulationConfig from dict, filtering unknown keys."""
      known_fields = cls.model_fields.keys()
      filtered_data = {k: v for k, v in data.items() if k in known_fields}
      return cls(**filtered_data)
  ```
- [ ] Run `pytest tests/unit/test_config_from_dict.py -v` to verify
- [ ] Run `pytest -m fast` to ensure no regressions

### Step 3: Serialization

- [ ] Identify files that serialize SimulationConfig (search for `.model_dump()`)
- [ ] Update calls to use `model_dump(mode='json')` instead
- [ ] Common locations:
  - Archiver module (saves run metadata)
  - Logger module (logs configuration)
  - Result handlers (processes results)
- [ ] Run `pytest tests/integration/test_config_serialization_roundtrip.py -v` to verify
- [ ] Run `pytest -m fast` to ensure no regressions

### Final Verification

```bash
# Run all affected tests
pytest tests/unit/test_config_deser_error_logging.py \
        tests/unit/test_config_from_dict.py \
        tests/integration/test_config_serialization_roundtrip.py \
        -v

# Run full fast test suite
pytest -m fast --tb=short

# Run integration tests
pytest -m integration --tb=short
```

---

## Debugging Tips

### Error: "ValidationError: extra fields not permitted"

This occurs with `extra='forbid'` config. Solution: Either set `extra='ignore'` or implement key filtering in from_dict().

### Error: "TypeError: Object of type Decimal is not JSON serializable"

This occurs when Decimal values are still in the dict. Solution: Use `model_dump(mode='json')` upstream to convert Decimals to floats.

### Error: "from_dict() takes 1 positional argument but 2 were given"

This occurs if SimulationConfig doesn't have a from_dict() classmethod. Solution: Add the classmethod implementation (Step 2).

---

## References

- **Feature Specification**: `specs/079-fix-config-deser/spec.md`
- **Research Output**: `specs/079-fix-config-deser/research.md`
- **Data Model**: `specs/079-fix-config-deser/data-model.md`
- **Error Location**: `planalign_api/services/simulation/result_handlers.py:66-68`
- **Config Schema**: `config/schema.py`
- **Related Issue**: #235 (Decimal JSON serialization)
- **CLAUDE.md**: Section 4 (Type-Safe Configuration), Section 7 (Error Handling - E074)

---

## Next Steps After Implementation

1. ✅ All tests passing
2. ✅ Code review with team
3. ✅ Run full test suite: `pytest --cov=config --cov=planalign_api`
4. ✅ Manual testing with a multi-scenario batch run
5. ✅ Verify result metadata displays correctly in Studio UI
6. ✅ Merge to main and release

---

**Ready to start implementing?** Begin with Step 1 and follow the checklist above.
