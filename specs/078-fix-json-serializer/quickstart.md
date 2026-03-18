# Quick Start: Testing the Decimal Serialization Fix

**Phase**: 1 - Design & Contracts
**Date**: 2026-03-18

## Reproduce the Bug (Before Fix)

**Current Status**: PipelineOrchestrator crashes with `TypeError: Object of type Decimal is not JSON serializable`

```bash
# Activate virtual environment
source .venv/bin/activate

# Try to run any simulation (will fail)
planalign simulate 2025 --dry-run

# Expected error:
# TypeError: Object of type Decimal is not JSON serializable
# at json.dumps() in logger.py:57
```

---

## Testing the Fix

### Unit Tests (Fast Track)

```bash
# Run only the Decimal serialization tests
pytest tests/test_decimal_serialization.py -v

# Expected output:
# test_model_dump_with_decimals PASSED
# test_decimal_conversion_to_float PASSED
# test_nested_decimal_in_list PASSED
# test_json_output_parsing PASSED
# test_large_decimal_precision PASSED
```

### Integration Test (Full Initialization)

```bash
# Run PipelineOrchestrator initialization test
pytest tests/test_pipeline_orchestrator.py::test_initialization_with_decimal_config -v

# Expected: Initialization completes without TypeError
```

### End-to-End Smoke Test

```bash
# Try a dry-run simulation (should succeed after fix)
planalign simulate 2025 --dry-run

# Expected: Simulation plan generated and logged successfully
```

---

## Verification Checklist

After implementing the fix, verify:

- [ ] **Unit Tests Pass**: All Decimal serialization tests pass in <10s
- [ ] **Integration Tests Pass**: PipelineOrchestrator initializes without errors
- [ ] **Smoke Test Passes**: `planalign simulate 2025 --dry-run` completes
- [ ] **Log Output Valid**: Configuration is logged to JSON with valid numeric representations
- [ ] **No Regressions**: Full test suite passes (`pytest`)
- [ ] **Code Coverage**: 90%+ coverage for affected modules (logger.py, run_summary.py)

---

## Implementation Steps (for developers)

### Step 1: Fix run_summary.py (Primary)

**File**: `planalign_orchestrator/run_summary.py`
**Line**: 129

```python
# Current (failing):
config_dict = config.model_dump()

# Change to:
config_dict = config.model_dump(mode='json')
```

### Step 2: Verify logger.py (No changes needed)

**File**: `planalign_orchestrator/logger.py`
**Line**: 57

No changes required. Once `run_summary.py` is fixed, the JSON passed to `logger.py` will already be serializable.

### Step 3: Verify pipeline_orchestrator.py (No changes needed)

**File**: `planalign_orchestrator/pipeline_orchestrator.py`
**Line**: 118

No changes required. This calls into `observability.set_configuration()` which uses `run_summary.py`.

### Step 4: Add Unit Tests

Create `tests/test_decimal_serialization.py` with tests for:

```python
import json
from decimal import Decimal
from pydantic import BaseModel

class TestDecimalSerialization:
    def test_model_dump_with_decimals(self):
        """Verify model_dump(mode='json') converts Decimals to floats"""
        class ConfigModel(BaseModel):
            salary: Decimal
            contribution_rate: Decimal

        config = ConfigModel(salary=Decimal("125000.50"), contribution_rate=Decimal("0.06"))

        # Test mode='json' conversion
        config_dict = config.model_dump(mode='json')
        assert isinstance(config_dict['salary'], float)
        assert isinstance(config_dict['contribution_rate'], float)
        assert config_dict['salary'] == 125000.50
        assert config_dict['contribution_rate'] == 0.06

    def test_json_output_parsing(self):
        """Verify JSON output can be parsed by standard parser"""
        class ConfigModel(BaseModel):
            salary: Decimal

        config = ConfigModel(salary=Decimal("125000.50"))
        config_dict = config.model_dump(mode='json')
        json_str = json.dumps(config_dict)

        # Should not raise TypeError
        parsed = json.loads(json_str)
        assert parsed['salary'] == 125000.50

    def test_nested_decimal_in_list(self):
        """Verify nested Decimals in collections are converted"""
        class ConfigModel(BaseModel):
            rates: list[Decimal]

        config = ConfigModel(rates=[Decimal("0.06"), Decimal("0.10")])
        config_dict = config.model_dump(mode='json')

        assert all(isinstance(r, float) for r in config_dict['rates'])
        assert config_dict['rates'] == [0.06, 0.10]

    def test_large_decimal_precision(self):
        """Verify precision handling for large Decimals"""
        class ConfigModel(BaseModel):
            amount: Decimal

        config = ConfigModel(amount=Decimal("999999999.99999999"))
        config_dict = config.model_dump(mode='json')
        json_str = json.dumps(config_dict)
        parsed = json.loads(json_str)

        # Acceptable loss due to float precision; still valid JSON
        assert isinstance(parsed['amount'], float)
        assert parsed['amount'] > 0
```

### Step 5: Run Full Test Suite

```bash
pytest -m fast  # Fast tests only (<10s)
pytest          # Full suite with integration tests
```

---

## Expected Behavior After Fix

### Configuration Logging

```python
# In PipelineOrchestrator.__init__()
observability.set_configuration(config)

# Logs to console/file:
{
  "simulation_year": 2025,
  "baseline_headcount": 1000,
  "salary_raise_pct": 0.03,
  "annual_salary": 125000.50,  # Now a float, not Decimal object
  "contribution_rate": 0.06,
  ...
}
```

### Simulation Execution

```bash
$ planalign simulate 2025 --dry-run
✓ Configuration validated
✓ Configuration logged successfully
✓ Simulation plan generated
  Year: 2025
  Events: ~2,500 expected
✓ Dry run complete

Total time: 0.34s
```

---

## Troubleshooting

### Still Getting TypeError After Fix?

1. Verify you edited `run_summary.py:129` correctly
2. Clear Python cache: `find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true`
3. Reinstall package: `uv pip install -e .`
4. Try again: `planalign simulate 2025 --dry-run`

### JSON Output Contains Decimal Objects?

This shouldn't happen after the fix. If it does:
1. Verify `model_dump(mode='json')` is being used (not `model_dump()`)
2. Check that the modified code is actually running (add a debug print if needed)
3. Ensure the cached bytecode is cleared (step 2 above)

### Test Coverage Not Meeting 90%?

Run with coverage reporting:
```bash
pytest tests/test_decimal_serialization.py --cov=planalign_orchestrator.logger --cov-report=term-missing
```

---

## Acceptance Criteria

Feature is complete when:

1. ✅ `planalign simulate 2025 --dry-run` runs without TypeError
2. ✅ Configuration is logged to JSON with valid float representations
3. ✅ All tests pass (fast + integration)
4. ✅ No regressions in existing simulations
5. ✅ Unit test coverage ≥90% for affected code paths
