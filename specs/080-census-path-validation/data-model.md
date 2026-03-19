# Phase 1 Data Model: Census Path Validation

**Date**: 2026-03-18
**Feature**: Enforce Census Path Validation on Simulation Start
**Branch**: `080-census-path-validation`

## Core Entities

### Entity 1: Scenario Configuration

**What it represents**: The merged configuration dictionary passed from Studio to the simulation service, containing all simulation parameters including census file path.

**Key Attributes**:
- `setup.census_parquet_path` (string, required): Absolute filesystem path to census parquet file
- `simulation.start_year` (int): Simulation start year (default: 2025)
- `simulation.end_year` (int): Simulation end year (default: 2027)
- `simulation.seed` (int): Random seed for reproducibility (default: 42)
- `scenario_id` (string): Unique identifier for the scenario (implicit, from API context)

**Validation Rules**:
- `census_parquet_path` MUST be present in config (non-null, non-empty)
- `census_parquet_path` MUST be a non-empty string (not whitespace-only)
- `census_parquet_path` MUST resolve to an existing file on the filesystem
- Path must be readable by the simulation service process

**State Transitions**:
- VALID: Path exists, file is readable → Proceed to simulation
- INVALID (missing): Path not in config → Raise ConfigurationError
- INVALID (not found): Path exists but file doesn't → Raise ConfigurationError
- INVALID (empty): census_parquet_path is empty string → Raise ConfigurationError

---

### Entity 2: Validation Context

**What it represents**: Runtime context captured when validation fails, including scenario information and diagnostic details.

**Key Attributes**:
- `scenario_id` (string): Which scenario failed validation
- `workspace_id` (string): Which workspace the scenario belongs to
- `census_path_provided` (string, optional): The path value that was provided
- `correlation_id` (string): Unique identifier for audit trail (8-char UUID)
- `timestamp` (datetime): When validation failed (ISO 8601 format)
- `error_type` (enum): "MISSING_PATH" or "FILE_NOT_FOUND"

**Relationships**:
- One Scenario Configuration → One Validation Context (when error occurs)
- Validation Context → Execution Context (per Constitution IV)

**Serialization**:
```python
@dataclass
class ValidationContext:
    scenario_id: str
    workspace_id: str
    census_path_provided: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error_type: Literal["MISSING_PATH", "FILE_NOT_FOUND"] = "MISSING_PATH"

    def to_context(self) -> ExecutionContext:
        """Convert to ExecutionContext for exception handling"""
        return ExecutionContext(
            scenario_id=self.scenario_id,
            correlation_id=self.correlation_id,
            timestamp=self.timestamp,
            metadata={
                "error_type": self.error_type,
                "workspace_id": self.workspace_id,
                "census_path": self.census_path_provided
            }
        )
```

---

### Entity 3: Configuration Error

**What it represents**: Exception raised when census path validation fails, containing user-friendly message and resolution guidance.

**Key Attributes**:
- `message` (string): User-facing error description (from FR-002, FR-004)
- `context` (ExecutionContext): Diagnostic context with correlation_id
- `category` (ErrorCategory): Always "CONFIGURATION" (per exception design)
- `severity` (ErrorSeverity): Always "ERROR" (user must intervene)
- `resolution_hints` (list[ResolutionHint]): Steps to resolve the error

**Error Messages**:

**For Missing Path** (FR-002):
```
census_parquet_path is required but was not found in the scenario config.
Ensure a census file has been uploaded to the scenario folder before running.
```

**For File Not Found** (FR-004):
```
Census file not found at '[absolute_path]'.
Upload a valid census parquet file to the scenario folder and retry.
```

**Example Resolution Hint**:
```python
ResolutionHint(
    title="Upload Census File to Scenario",
    description="A census parquet file must be uploaded to the scenario folder before running a simulation.",
    steps=[
        "1. Open PlanAlign Studio",
        "2. Navigate to the scenario that failed",
        "3. Upload a valid census parquet file using the 'Upload Files' button",
        "4. Retry the simulation"
    ],
    documentation_url="https://docs.fidelity.com/planalign/census-upload",
    automation_available=False,
    estimated_resolution_time="2-3 minutes"
)
```

**Relationships**:
- ConfigurationError contains ExecutionContext (n:1)
- ConfigurationError contains ResolutionHint[] (1:m)
- ConfigurationError is caught and converted to API error response (in exception handler)

---

## Data Flow

### Validation Flow

```
execute_simulation(workspace_id, scenario_id, config)
    │
    └─> _prepare_simulation(workspace_id, scenario_id, config)
            │
            └─> _validate_census(config)
                    │
                    ├─ Check: census_parquet_path exists in config?
                    │   NO  → raise ConfigurationError (MISSING_PATH)
                    │   YES → proceed
                    │
                    ├─ Check: is path non-empty string?
                    │   NO  → raise ConfigurationError (MISSING_PATH)
                    │   YES → proceed
                    │
                    └─ Check: file exists on filesystem?
                        NO  → raise ConfigurationError (FILE_NOT_FOUND)
                        YES → return success
```

### Error Handling Flow

```
execute_simulation() [async]
    │
    └─ try:
        │   _validate_census() → ConfigurationError
        │
        catch ConfigurationError as e:
            │
            ├─ Log: error with correlation_id and context
            ├─ Call: update_run_status(error_message=e.message)
            └─ UI displays: error_message to user
                        (via existing error field in run status)
```

---

## Validation Rules (from FR-001 to FR-007)

| Requirement | Entity | Validation Rule | Enforcement |
|---|---|---|---|
| FR-001 | Scenario Config | census_parquet_path MUST exist | ConfigurationError if missing |
| FR-002 | Configuration Error | Error message MUST match spec | String constant in code |
| FR-003 | Scenario Config | Path MUST resolve to existing file | Path.exists() check |
| FR-004 | Configuration Error | Error message MUST match spec | String constant in code |
| FR-005 | Validation Logic | NO fallback paths allowed | Remove all fallback logic |
| FR-006 | Error Propagation | Errors MUST surface in UI | Via update_run_status callback |
| FR-007 | Validation Context | Errors MUST be logged with context | ExecutionContext with scenario_id |

---

## Edge Case Handling

| Edge Case | Input | Expected Behavior | Error Type |
|---|---|---|---|
| Empty string path | `census_parquet_path: ""` | Raise ConfigurationError | MISSING_PATH |
| Whitespace-only path | `census_parquet_path: "   "` | Raise ConfigurationError | MISSING_PATH |
| Missing key | `setup: {}` (no census_parquet_path key) | Raise ConfigurationError | MISSING_PATH |
| Deleted file | Path exists at config time, deleted before validation | Raise ConfigurationError | FILE_NOT_FOUND |
| Permission denied | Path exists but unreadable | Raise ConfigurationError | FILE_NOT_FOUND (conservative) |
| Relative path | `census_parquet_path: "./census.parquet"` | Raise ConfigurationError (path must be absolute) | MISSING_PATH |
| Valid path | `census_parquet_path: "/workspace/scenario/census.parquet"` (file exists, readable) | Validation passes | N/A |

---

## Type-Safe Configuration (Per Constitution V)

```python
# Using Pydantic v2 (existing pattern in codebase)
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SetupConfig(BaseModel):
    """Setup configuration section"""
    census_parquet_path: Optional[str] = Field(
        default=None,
        description="Absolute path to census parquet file"
    )

    class Config:
        # Allow extra fields for extensibility
        extra = "allow"

class SimulationConfig(BaseModel):
    """Full simulation configuration"""
    setup: SetupConfig = Field(default_factory=SetupConfig)
    simulation: Dict[str, Any] = Field(default_factory=dict)
    # ... other config sections
```

**Validation Strategy**:
- Use existing `dict.get()` pattern (backward compatible)
- Check for both missing key AND empty/whitespace values
- Do NOT use Pydantic validation at config loading time (spec says post-merge)
- Validation occurs in `_validate_census()` before subprocess launch
