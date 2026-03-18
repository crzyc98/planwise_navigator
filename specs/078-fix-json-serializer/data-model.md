# Data Model: Decimal Serialization in Configuration

**Phase**: 1 - Design & Contracts
**Date**: 2026-03-18
**Status**: In Progress

## Affected Pydantic Models

These Pydantic v2 models contain Decimal fields that require JSON serialization:

### 1. SimulationConfig (Primary)

**Location**: `planalign_orchestrator/config.py`

**Fields with Decimal**:
- Various compensation/financial fields (annual salary, benefits, contributions, etc.)
- Match rates and plan contribution percentages
- Vesting schedules

**Serialization Point**: `run_summary.py:129` - when config is dumped for logging

**Fix Application**:
```python
# Before (fails with TypeError)
config_dict = config.model_dump()
json_str = json.dumps(config_dict)

# After (succeeds)
config_dict = config.model_dump(mode='json')
json_str = json.dumps(config_dict)
```

### 2. Related Models

**Models that may contain Decimals**:
- `EmployeeRecord` - salary, benefits amounts
- `PlanDesign` - match percentages, contribution rates
- `WorkforceParameters` - demographic percentages, growth rates
- Any event payload with financial amounts

**All these models** inherit the same serialization pattern via Constitution V (Type-Safe Configuration).

---

## Serialization Boundaries

### Current (Broken) Flow

```
SimulationConfig (Pydantic with Decimal fields)
    ↓
config.model_dump()  ← Returns dict with Decimal objects
    ↓
json.dumps(config_dict)  ← FAILS: TypeError on Decimal
    ↓ (CRASH)
PipelineOrchestrator.__init__() fails
```

### Fixed Flow

```
SimulationConfig (Pydantic with Decimal fields)
    ↓
config.model_dump(mode='json')  ← Returns dict with float values
    ↓
json.dumps(config_dict)  ← SUCCESS: floats are JSON-serializable
    ↓
observability.set_configuration() logs successfully
```

---

## State & Validation Rules

### Configuration Validation

- All Decimal fields use Pydantic v2 `Field` validators with `Decimal` type hints
- Validation happens at model instantiation (config load time)
- JSON output (floats) is for logging/display only; in-memory objects retain Decimal precision

### Edge Cases Handled

| Case | Behavior | Test Coverage |
|------|----------|---------------|
| Nested Decimals (list/dict) | `mode='json'` recursively converts | test_nested_decimal_list() |
| Very large Decimals | Converted to float (acceptable precision loss for logs) | test_large_decimal_precision() |
| Decimal(0) or special values | Converted to 0.0, -0.0, etc. | test_decimal_edge_cases() |
| None/optional Decimals | Converted to null in JSON | test_optional_decimal() |

---

## Data Flow Through System

### Year Simulation Pipeline

1. **Load Config** (Pydantic models loaded from YAML) → Decimals in memory ✅
2. **PipelineOrchestrator.__init__()**
   - Calls `observability.set_configuration()`
   - Uses `config.model_dump(mode='json')` ← FIX APPLIED HERE
   - Logs to JSON successfully ✅
3. **Execute Year** - All calculations use in-memory Decimal objects ✅
4. **Generate Events** - Event payloads preserve Decimal precision ✅
5. **Audit Trail** - Original Decimals logged with events ✅

### Serialization Touch Points

| Component | Operation | Serialization Method | Status |
|-----------|-----------|----------------------|--------|
| run_summary.py | Config logging | `model_dump(mode='json')` | ✅ FIX |
| logger.py | JSON encoding | `json.dumps()` | ✅ FIXED BY UPSTREAM |
| pipeline_orchestrator.py | Config tracking | Uses run_summary | ✅ FIXED BY UPSTREAM |
| observability.py | Telemetry | Uses run_summary | ✅ FIXED BY UPSTREAM |

---

## Pydantic v2 Mode='json' Behavior

**What `mode='json'` does**:
- Recursively converts non-JSON-serializable types:
  - `Decimal` → `float`
  - `datetime` → ISO 8601 string
  - `UUID` → string
  - `date` → ISO 8601 string
  - Custom serializers via `field_serializer` decorators
- Returns standard Python dict (ready for `json.dumps()`)
- Does NOT call `json.dumps()` itself

**Why this is the right approach**:
1. **Type-Safe**: Pydantic validates at load time, converts at serialization time
2. **Future-Proof**: Any new Pydantic types automatically supported
3. **Modular**: Each model specifies its own serialization via `field_serializer`
4. **Transparent**: Original values preserved in-memory, only JSON output changed

---

## No Breaking Changes

- Configuration models remain unchanged
- Decimal arithmetic in simulations unaffected
- JSON output format compatible with existing parsers
- All tests continue to pass with this change

---

## Next Steps

1. Implement fix in `run_summary.py:129`
2. Verify `logger.py` and `pipeline_orchestrator.py` work without changes
3. Add unit tests for all edge cases
4. Run full test suite to confirm no regressions
