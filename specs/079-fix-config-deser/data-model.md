# Data Model: SimulationConfig Deserialization

**Feature**: 079-fix-config-deser
**Date**: 2026-03-18
**Status**: Phase 1 Design

---

## Entity Definitions

### 1. SimulationConfig

**Purpose**: Represents the complete configuration for a workforce simulation, including timing, growth targets, termination rates, promotion parameters, and compensation adjustments.

**Current Location**: `config/schema.py`

**Fields** (from Pydantic v2 model):

| Field | Type | Validation | Required | Description |
|-------|------|-----------|----------|-------------|
| `start_year` | int | ge=2020, le=2050 | ✓ | Simulation start year |
| `end_year` | int | ge=2020, le=2050, > start_year | ✓ | Simulation end year |
| `random_seed` | int | ge=1 | Optional (default: 42) | Random seed for reproducibility |
| `target_growth_rate` | float | ge=-0.5, le=0.5 | Optional (default: 0.03) | Annual workforce growth rate |
| `total_termination_rate` | float | ge=0.0, le=1.0 | Optional (default: 0.12) | Overall annual termination rate |
| `new_hire_termination_rate` | float | ge=0.0, le=1.0, >= total_termination_rate | Optional (default: 0.25) | First-year termination rate |
| `promotion_budget_pct` | float | ge=0.0, le=0.5 | Optional (default: 0.15) | Percent of workforce eligible for promotion |
| `promotion_level_caps` | Dict[int, float] | - | Optional (default: {1: 0.20, 2: 0.15, 3: 0.10, 4: 0.05}) | Maximum promotion rates by level |
| `cola_rate` | float | ge=0.0, le=0.10 | Optional (default: 0.025) | Cost of living adjustment |
| `merit_budget_pct` | float | ge=0.0, le=0.10 | Optional (default: 0.04) | Merit increase budget as % of payroll |
| `promotion_increase_pct` | float | ge=0.0, le=0.50 | Optional (default: 0.15) | Salary increase on promotion |

**Key Validators**:
- `validate_end_year()`: Ensures end_year > start_year
- `validate_new_hire_term_rate()`: Ensures new_hire_termination_rate >= total_termination_rate

**Current Issues**:
- No explicit `extra='ignore'` setting (uses Pydantic default)
- No `from_dict()` classmethod for robust dict→model conversion
- No validation on merged config dicts (accepts unknown keys)

**Changes Required** (Phase 1 Implementation):
1. Add `from_dict()` classmethod with key filtering
2. Optionally add `extra='ignore'` to Config class for defensive programming
3. Improve error handling in from_dict() to provide diagnostic context

---

### 2. ConfigMerge (Transient - Result Handler Context)

**Purpose**: Represents merged configuration after scenario overrides are applied during result archiving.

**Context**: Studio applies scenario-specific config overrides that are merged with base SimulationConfig.

**Attributes**:
- **source_config**: Original SimulationConfig object
- **overrides**: Dict[str, Any] - Scenario-specific overrides
- **merged_dict**: Dict[str, Any] - Result of merging source_config + overrides

**Problem**: merged_dict may contain:
- Extra keys not in SimulationConfig (from Studio overrides)
- Decimal values (if serialized with model_dump() not model_dump(mode='json'))
- Missing required fields (if merge operation is incomplete)

**Validation Requirements**:
- Must filter unknown keys before constructing SimulationConfig
- Must convert Decimal values to floats before deserialization
- Must handle missing optional fields gracefully (use model defaults)

---

### 3. RunMetadata (Archive Record)

**Purpose**: Captures configuration and execution context for audit trails and result archiving.

**Location**: Saved in run archive directory after simulation completion

**Key Fields**:
- `config`: Serialized SimulationConfig (must use model_dump(mode='json') for Decimal→float conversion)
- `run_id`: Unique identifier for the simulation run
- `start_time`: Timestamp of run start
- `end_time`: Timestamp of run completion
- `success`: Boolean indicating if run completed successfully
- `seed`: Random seed used for reproducibility
- `error_message`: If run failed, the error message (now with full diagnostic context)

**Deserialization Flow**:
1. Load RunMetadata from archive
2. Extract config dict from metadata
3. Call `SimulationConfig.from_dict(config_dict)` to reconstruct config
4. Handle deserialization errors gracefully (new error logging)

**Changes Required**:
- Ensure config serialization uses `model_dump(mode='json')`
- Ensure deserialization errors are logged with full context
- Ensure run metadata is fully persisted even if config deserialization fails (non-blocking)

---

## State Transitions

### Config Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│ 1. CREATION                                              │
│ SimulationConfig created from YAML/JSON config file     │
│ via planalign_orchestrator.config.loader               │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ 2. SCENARIO OVERRIDE (Studio)                           │
│ Config merged with scenario-specific overrides          │
│ Result: ConfigMerge with extra/missing fields possible  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ 3. SERIALIZATION (Archiver)                             │
│ Config serialized for archiving                          │
│ MUST use model_dump(mode='json') to convert Decimals    │
│ Result: Dict with float values, no Decimal objects      │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ 4. ARCHIVING (Result Handler)                           │
│ Serialized config stored in RunMetadata                 │
│ Result: config_dict in archive with Decimals→floats     │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ 5. DESERIALIZATION (Result Handler / Studio UI)         │
│ config_dict loaded from RunMetadata                     │
│ NEW: from_dict() filters unknown keys + converts types  │
│ Result: Reconstructed SimulationConfig OR diagnostic    │
│         error log if deserialization fails              │
└─────────────────────────────────────────────────────────┘
```

---

## Validation Rules

### SimulationConfig Validation

| Rule | Validation Type | Error Message | Triggered By |
|------|-----------------|---------------|--------------|
| end_year > start_year | Cross-field | "end_year must be after start_year" | from_dict() or __init__() |
| new_hire_termination_rate >= total_termination_rate | Cross-field | "new_hire_termination_rate should be >= total_termination_rate" | from_dict() or __init__() |
| All float fields in valid ranges | Field-level | "[field] must be between [min] and [max]" | from_dict() or __init__() |
| All year fields in 2020-2050 range | Field-level | "[year] must be between 2020 and 2050" | from_dict() or __init__() |

### from_dict() Robustness

| Scenario | Current Behavior | New Behavior | Handling |
|----------|------------------|--------------|----------|
| Unknown keys in dict | Depends on Pydantic default | Silently filtered (logged for debugging) | Key filtering classmethod |
| Decimal values in dict | TypeError or silent error | Accepted if from_dict() receives floats (from model_dump(mode='json')) | Upstream serialization responsibility |
| Missing optional fields | Pydantic uses defaults | Pydantic uses defaults | No change needed |
| Missing required fields | ValidationError | Logged with context | Enhanced error handling |

---

## Entity Relationships

```
┌─────────────────┐
│ YAML/JSON       │
│ Config File     │
└────────┬────────┘
         │ loader.load_config()
         ▼
┌──────────────────────────────────────┐
│ SimulationConfig (Pydantic Model)     │
│ - Validated fields                    │
│ - Type safety (int, float, Dict)      │
└────────┬──────────────────────────────┘
         │ Studio.apply_scenario_overrides()
         ▼
┌──────────────────────────────────────┐
│ ConfigMerge (Transient)               │
│ - Original config                     │
│ - Scenario overrides                  │
│ - Merged dict (may have extra keys)   │
└────────┬──────────────────────────────┘
         │ config.model_dump(mode='json')
         ▼
┌──────────────────────────────────────┐
│ Dict[str, Any]                       │
│ - Serializable (floats not Decimals) │
│ - Archivable (JSON-compatible)       │
└────────┬──────────────────────────────┘
         │ archiver.save_run_metadata()
         ▼
┌──────────────────────────────────────┐
│ RunMetadata (Archive)                │
│ - config: serialized dict            │
│ - run_id, timestamps, etc.           │
└────────┬──────────────────────────────┘
         │ result_handler.process_run()
         ▼
┌──────────────────────────────────────┐
│ SimulationConfig.from_dict()         │
│ - Filter unknown keys                │
│ - Reconstruct model                  │
│ - Error handling with context        │
└──────────────────────────────────────┘
```

---

## References

- **Current Code**: `config/schema.py` - SimulationConfig definition
- **Error Location**: `planalign_api/services/simulation/result_handlers.py:66-68`
- **Related Issue**: #235 (Decimal JSON serialization)
- **CLAUDE.md Section**: Section 4 (Event Sourcing) and Section 9 (Type-Safe Configuration)
