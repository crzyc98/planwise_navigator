# Result Handler API Contract

**Feature**: 079-fix-config-deser
**Date**: 2026-03-18
**Type**: Internal API (result handler completion hook)

---

## Overview

This contract documents the internal API contract for result handler execution. No public-facing API changes are introduced by this bug fix; the fix is internal to error handling and metadata archiving.

---

## Internal Contract: Result Handler Execution

### Input Contract

**Function**: `export_results_to_excel()` and related result handlers
**Location**: `planalign_api/services/simulation/result_handlers.py`

**Parameters**:
```python
def export_results_to_excel(
    scenario_path: Path,
    scenario_name: str,
    config: Dict[str, Any],  # May contain unknown keys from scenario overrides
    seed: int,
    run_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Export simulation results after successful completion."""
```

**Input Validation**:
- `scenario_path`: Must be an existing directory
- `scenario_name`: Non-empty string
- `config`: Dict that may contain:
  - Valid SimulationConfig fields
  - Extra keys from scenario overrides (Studio-specific)
  - Decimal values (from model_dump() not model_dump(mode='json')) — **Fixed by this PR**
  - Missing optional fields (uses Pydantic defaults)
- `seed`: Integer random seed
- `run_dir`: Optional existing directory

### Output Contract

**Returns**:
- `Optional[Path]`: Path to generated Excel file if successful
- `None`: If export fails (logged with diagnostic context)

**Side Effects**:
- Logs result handler progress to logger
- Creates Excel export in scenario/run directory
- Saves run metadata (config, state, audit trail)
- **NEW**: Error logs include full exception context (not just "from_dict")

### Error Handling (Updated by this PR)

**Before**:
```python
except Exception as e:
    logger.warning(f"Could not create SimulationConfig from dict: {e}")
    # Error message truncated to "from_dict" method name
    # Operator cannot diagnose the root cause
```

**After**:
```python
except TypeError as e:
    logger.error(
        f"Type mismatch in config: {type(e).__name__}: {e} "
        f"(cause: Decimal values not converted to float)"
    )
except ValidationError as e:
    logger.error(f"Invalid config: {type(e).__name__}: {e}")
except Exception as e:
    logger.error(
        f"Unexpected error deserializing config: "
        f"{type(e).__name__}: {e}",
        exc_info=True
    )
    # Now includes actionable diagnostics for <5 min diagnosis
```

---

## Public API: Studio Endpoints (No Changes)

This bug fix does not introduce new endpoints or modify existing Studio API contracts.

**Existing Endpoints** (unchanged):
- `GET /api/workspaces/{workspace_id}/runs/{run_id}` - Retrieve run metadata
- `GET /api/workspaces/{workspace_id}/runs/{run_id}/config` - Get run configuration
- `POST /api/workspaces/{workspace_id}/runs/{run_id}/retry` - Retry run

**Config Deserialization** (internal, hidden from API):
- Studio API deserializes run config for display
- Uses `SimulationConfig.from_dict()` (NEW: with key filtering)
- If deserialization fails, returns error response (NO CHANGE to response schema)

---

## Data Flow Contract

### Before Fix

```
Run Completion
    ↓
Result Handler receives config dict
    ↓
TRY: SimulationConfig.from_dict(config)
    ↓ (error)
CATCH: log "Could not create SimulationConfig from dict: from_dict"
    ↓
Operator confused: "What's wrong? What does 'from_dict' mean?"
Debugging delayed (>5 min diagnosis time)
```

### After Fix

```
Run Completion
    ↓
Archiver: config.model_dump(mode='json') → floats not Decimals
    ↓
Result Handler receives config dict (Decimals already converted)
    ↓
TRY: SimulationConfig.from_dict(config)
    ├─ Filters unknown keys
    ├─ Uses defaults for missing optional fields
    └─ Returns reconstructed config OR error
    ↓
IF SUCCESS: Metadata archived with config ✓
    ↓
IF ERROR: Log "Type mismatch in config: TypeError: Decimal type..."
    ↓
Operator can diagnose immediately (<5 min)
    ↓ (if Decimal issue)
"Ah! model_dump(mode='json') not used upstream. Fixed!"
```

---

## Integration Points

**Modified Components**:
1. `planalign_api/services/simulation/result_handlers.py` - Error logging
2. `config/schema.py` - SimulationConfig.from_dict() classmethod
3. Archiver module (TBD in implementation) - Use model_dump(mode='json')
4. Logger module (TBD in implementation) - Use model_dump(mode='json')

**Unchanged Components**:
- Studio API endpoints
- Run archiving directory structure
- RunMetadata schema (config field still receives serialized dict)
- Database schema (DuckDB tables unchanged)

---

## Testing Contract

**Must Test**:
- ✅ Error logging includes exception type and message
- ✅ from_dict() accepts config dicts with unknown keys (filtered)
- ✅ from_dict() accepts config dicts with missing optional fields (defaults used)
- ✅ from_dict() raises ValidationError for missing required fields (with context)
- ✅ Config serialization uses model_dump(mode='json') to convert Decimals
- ✅ Roundtrip serialization→deserialization preserves config values

**Test Files**:
- `tests/unit/test_config_deser_error_logging.py` - Error logging
- `tests/unit/test_config_from_dict.py` - Key filtering
- `tests/integration/test_config_serialization_roundtrip.py` - Roundtrip

---

## Backward Compatibility

**Breaking Changes**: None
- Error logging format changes (improvement, not breaking)
- `from_dict()` now filters keys gracefully (backward compatible)
- Serialization using `model_dump(mode='json')` is transparent to callers

**Deprecations**: None

**Upgrade Path**: Deploy bug fix; no data migration needed

---

## Monitoring & Observability

**Metrics to Track**:
- Count of result handler completions (should remain stable)
- Count of deserialization failures (should drop to near-zero after fix)
- Error log patterns (should show specific exception types, not generic "from_dict")

**Logging**:
- Result handler completion: INFO level
- Deserialization failure: ERROR level with full context
- Unknown keys filtered: DEBUG level (optional)

---

## Related Contracts

- **Issue #235**: Decimal JSON serialization contract (must use `model_dump(mode='json')`)
- **E074 Error Handling**: Enterprise transparency requirement for error messages
- **CLAUDE.md Section 4**: Type-safe configuration contract
