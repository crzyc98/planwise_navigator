# Phase 0 Research: SimulationConfig Deserialization Fix

**Date**: 2026-03-18
**Feature**: 079-fix-config-deser
**Goal**: Resolve technical unknowns and identify best practices for robust config deserialization

---

## Research Tasks

### 1. Root Cause Analysis: from_dict() Failure

**Finding**: Examined result_handlers.py lines 66-68 and related code.

**Current Error Handling**:
```python
try:
    sim_config = SimulationConfig.from_dict(config)
except Exception as e:
    logger.warning(f"Could not create SimulationConfig from dict: {e}")
```

**Issue**: When `str(e)` is called on the exception, it resolves to the method name "from_dict" rather than the actual error message. This happens when:
1. The exception is being caught by a broad `except Exception` clause
2. The exception's `__str__` method is minimal (e.g., Pydantic v2 ValidationError)
3. OR the exception object itself doesn't have a meaningful string representation

**Root Causes (Confirmed from Issue #240)**:
1. **Decimal/Type Mismatch** (Primary): `model_dump()` retains Decimal objects; from_dict() receives Decimal instead of expected string/float. Related to Issue #235.
2. **Unknown Keys**: Config merging in Studio adds keys that SimulationConfig doesn't expect. Pydantic raises ValidationError.
3. **Missing Required Fields**: Config dict is incomplete after merging, missing required fields.

**Decision**: All three causes are possible. Implementation must handle all three.

**References**:
- Issue #235: JSON serialization of Decimal values
- Issue #240: SimulationConfig.from_dict() failure
- CLAUDE.md Section 7: Error handling (E074) - Enhanced diagnostics

---

### 2. Pydantic v2 Best Practices: Dict→Model Conversion with Unknown Keys

**Finding**: Researched Pydantic v2 documentation and project patterns.

**Pydantic v2 Behavior**:
- By default, Pydantic v2 raises `ValidationError` when encountering unknown fields (if `extra='forbid'`)
- With `extra='ignore'`, unknown fields are silently dropped
- With `extra='allow'`, unknown fields are stored as attributes

**SimulationConfig Current State** (from config/schema.py):
- Uses `BaseModel` without explicit `extra=` setting
- Default behavior: depends on Pydantic's default (typically `extra='ignore'`)
- Has Pydantic v1-style `@validator` decorators (need to be updated to v2 if refactoring)

**Recommended Approach**:
1. **Option A**: Explicitly set `extra='ignore'` in SimulationConfig.Config to silently drop unknown keys during deserialization
2. **Option B**: Add a classmethod `from_dict()` that filters keys before model construction (explicit filtering is more transparent)
3. **Option C**: Use Pydantic v2's `model_validate()` with `from_attributes=True` for explicit control

**Decision**: Implement Option B (classmethod with explicit filtering). Rationale:
- More transparent: unknown keys are explicitly filtered, not silently ignored
- Better error messages: we can log which keys were dropped
- Aligns with CLAUDE.md enterprise transparency principle
- Easier to test and debug

**Implementation Pattern**:
```python
@classmethod
def from_dict(cls, data: dict) -> "SimulationConfig":
    # Filter to known fields only
    known_fields = cls.model_fields.keys()
    filtered_data = {k: v for k, v in data.items() if k in known_fields}
    # Construct with validation
    return cls(**filtered_data)
```

**Reference**: Pydantic v2 documentation, CLAUDE.md Section 9 (Coding Standards) - Type hints and validation

---

### 3. Python Exception Handling Best Practices

**Finding**: Exception handling patterns in Python and Pydantic v2.

**Problem Analysis**:
```python
except Exception as e:
    logger.warning(f"Could not create SimulationConfig from dict: {e}")
    # Issue: str(e) may return just "from_dict" (method name)
```

**Root Issue**:
- Some exception types have minimal `__str__` representations
- Pydantic v2's `ValidationError` has complex `__str__` but might not be called correctly
- Better approach: capture both exception type and message

**Best Practice Solution**:
```python
except Exception as e:
    logger.warning(
        f"Could not create SimulationConfig from dict: "
        f"{type(e).__name__}: {e}"
    )
    # Or more detailed:
    import traceback
    logger.warning(f"Error: {traceback.format_exc()}")
```

**CLAUDE.md Alignment**: Section 7 (E074 - Enhanced Error Handling) requires:
- Exception type included in diagnostic message
- Execution context provided
- Resolution hints (when applicable)

**Implementation Pattern**:
```python
try:
    config = SimulationConfig.from_dict(config_dict)
except TypeError as e:
    logger.error(
        f"Type mismatch in config: {type(e).__name__}: {e} "
        f"(common cause: Decimal values not converted to float)"
    )
except ValueError as e:
    logger.error(
        f"Invalid config value: {type(e).__name__}: {e}"
    )
except KeyError as e:
    logger.error(
        f"Missing or unknown config field: {type(e).__name__}: {e}"
    )
except Exception as e:
    logger.error(
        f"Unexpected error in config deserialization: "
        f"{type(e).__name__}: {e}",
        exc_info=True  # Include full traceback
    )
```

**Reference**: Python logging documentation, CLAUDE.md E074 error handling patterns

---

### 4. Upstream Serialization: model_dump(mode='json') Usage

**Finding**: Identified where Decimal serialization must occur.

**Issue #235 Context**: JSON serialization of Decimal values fails because:
- `config.model_dump()` returns dict with Decimal objects still intact
- `json.dumps()` cannot serialize Decimal objects natively
- Solution: Use `config.model_dump(mode='json')` to convert Decimals to floats

**Where to Apply model_dump(mode='json')**:

1. **Run Archiver** (archives run metadata after simulation):
   - File: `planalign_api/services/simulation/run_archiver.py` (or similar)
   - Current: Likely uses `config.model_dump()` or direct dict conversion
   - Change: Use `config.model_dump(mode='json')` to ensure Decimals→floats

2. **Logger** (logs configuration during initialization):
   - File: `planalign_orchestrator/observability/logger.py` (or similar)
   - Current: Likely uses `config.model_dump()`
   - Change: Use `config.model_dump(mode='json')` before JSON serialization

3. **Run Summary** (result handler - this feature):
   - File: `planalign_api/services/simulation/result_handlers.py`
   - Current: Merges config dict for archiving
   - Change: Ensure upstream code uses `model_dump(mode='json')` before calling from_dict()

**Implementation Pattern**:
```python
# Before: config.model_dump() - Decimals stay as Decimal objects
serialized_config = config.model_dump()  # Contains Decimal objects

# After: config.model_dump(mode='json') - Decimals converted to floats
serialized_config = config.model_dump(mode='json')  # Decimals → float

# Result: from_dict() receives floats, not Decimals
reconstructed = SimulationConfig.from_dict(serialized_config)
```

**Reference**: Pydantic v2 documentation on `model_dump()`, Issue #235, CLAUDE.md Section 4 (Type-Safe Configuration)

---

### 5. Three-Step Implementation Strategy

**Consolidated Decision** based on research above:

**Step 1: Improve Error Logging** (Immediate - no API changes)
- **File**: `planalign_api/services/simulation/result_handlers.py:66-68`
- **Change**: Capture `type(e).__name__` and full `str(e)` in log message
- **Impact**: Enables rapid diagnosis without code changes
- **Test**: Unit test that triggers deserialization failure and verifies error message content

**Step 2: Robust Config Deserialization** (Backward compatible)
- **File**: `config/schema.py` - Add classmethod to SimulationConfig
- **Change**: Implement `from_dict()` classmethod with key filtering
- **Alternative**: Add `extra='ignore'` to Config class
- **Impact**: Silent filtering of unknown keys, no exceptions raised
- **Test**: Unit tests for from_dict() with various dict shapes (all keys, extra keys, missing optional keys)

**Step 3: Upstream Serialization** (Coordinates with #235)
- **Files**: Identify and update call sites that use `model_dump()` → `model_dump(mode='json')`
- **Likely**: Run archiver, logger, result handler
- **Impact**: Ensures Decimal→float conversion before deserialization
- **Test**: Integration test that simulates config serialization→deserialization roundtrip

---

## Phase 0 Conclusions

✅ **All unknowns resolved. Ready for Phase 1 design.**

### Key Decisions Made:

| Unknown | Decision | Rationale |
|---------|----------|-----------|
| Error logging approach | Capture `type(e).__name__` + `str(e)` + optional `exc_info=True` | Aligns with E074 enterprise transparency; provides actionable diagnostics |
| Unknown key handling | Implement classmethod `from_dict()` with explicit filtering | More transparent than silent ignore; enables debugging |
| Decimal serialization | Use `model_dump(mode='json')` upstream before from_dict() | Coordinates with Issue #235 solution; prevents type mismatches |
| Module structure | No new modules; localized changes to existing files | Minimizes scope; follows modular architecture principle |

### Technical Approach Confirmed:

1. ✅ Error logging (Step 1): Enhanced exception details in result_handlers.py
2. ✅ Key filtering (Step 2): Classmethod in SimulationConfig for robust deserialization
3. ✅ Serialization (Step 3): Upstream use of `model_dump(mode='json')` to convert Decimals
4. ✅ Testing: Unit tests for error handling, key filtering, and integration tests for roundtrip serialization

---

**Next Phase**: Phase 1 Design will create:
- `data-model.md`: Config and metadata entity definitions
- `contracts/`: API contracts for result handler endpoints (if applicable)
- `quickstart.md`: Developer guide for testing the fix
