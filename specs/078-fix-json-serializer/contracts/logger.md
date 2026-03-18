# Logger Interface Contract

**Phase**: 1 - Design & Contracts
**Date**: 2026-03-18

## Purpose

Documents the contract for the JSON logger that must handle any Python serializable object and convert it to valid JSON. This contract ensures that all types passed to the logger are properly serializable.

## Logger Function Signature

```python
def json_dumps(log_data: dict) -> str:
    """
    Serialize a Python dictionary to valid JSON string.

    Args:
        log_data: Dictionary that MUST be JSON-serializable
                  (no Decimal, datetime, or custom objects)

    Returns:
        Valid JSON string parseable by json.loads()

    Raises:
        TypeError: If any value in log_data is not JSON-serializable
    """
```

## Input Contract

### What Callers MUST Provide

- **Type**: `dict` (or convertible to dict)
- **Keys**: str only (JSON requirement)
- **Values**: MUST be JSON-serializable types:
  - `None`
  - `bool`
  - `int`
  - `float`
  - `str`
  - `list` (containing serializable values)
  - `dict` (containing serializable values)

### What Callers MUST NOT Provide

❌ `Decimal`, `datetime`, `date`, `UUID`, `Path`, custom objects
❌ `set`, `tuple`, `frozenset`
❌ Functions, classes, modules

## Output Contract

### What Logger MUST Guarantee

- Returns valid JSON string
- String is parseable by `json.loads()`
- Represents the original data accurately:
  ```python
  json.loads(json_dumps(data)) == json_compatible_data
  ```
- No data loss for numeric types (ints/floats preserved)
- Throws `TypeError` if input violates contract

## Call Site Responsibility

**Before Calling Logger**:

Callers are responsible for converting non-JSON-serializable types to JSON-serializable ones:

```python
# ❌ BAD: Passing Decimal to logger
from decimal import Decimal
config = {"salary": Decimal("125000.50")}
json_str = json.dumps(config)  # TypeError!

# ✅ GOOD: Convert Decimal to float first
config = {"salary": 125000.50}
json_str = json.dumps(config)  # OK

# ✅ BEST: Use Pydantic's model_dump(mode='json')
config_dict = pydantic_model.model_dump(mode='json')
json_str = json.dumps(config_dict)  # OK, and handles all types
```

## Specific Implementation: run_summary.py

### Call Site: `run_summary.py:129`

```python
# Before (violates contract - passes Decimal):
config_dict = config.model_dump()  # Returns dict with Decimal values
log_data = {"config": config_dict, ...}
json_str = json.dumps(log_data)  # TypeError!

# After (honors contract - converts to floats):
config_dict = config.model_dump(mode='json')  # Converts Decimal → float
log_data = {"config": config_dict, ...}
json_str = json.dumps(log_data)  # OK - all values JSON-serializable
```

## Why This Pattern?

1. **Separation of Concerns**: Logger is responsible for JSON encoding only, not type conversion
2. **Error Location**: Type conversion errors caught at source (run_summary.py) where the data structure is created
3. **Pydantic Integration**: Leverages Pydantic v2's `mode='json'` for automatic type conversion
4. **Clarity**: Callers understand their serialization requirements

## Verification

This contract is verified by:
- Unit tests confirming JSON output is valid and parseable
- Type checking that all dict values are JSON-serializable
- Integration tests confirming logger is called with valid data

## No Breaking Changes

- Logger function signature unchanged
- Logger behavior unchanged (still produces valid JSON)
- Only requirement is that callers provide JSON-serializable dicts
- Callers in this codebase use `model_dump(mode='json')` which guarantees this
