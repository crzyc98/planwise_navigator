# Research: Unified Database Path Resolver

**Feature**: 005-database-path-resolver
**Date**: 2025-12-12

## Research Tasks

### 1. Existing Implementation Analysis

**Task**: Analyze the current duplicated database path resolution logic across the three services.

**Findings**:

| Service | File | Lines | Method |
|---------|------|-------|--------|
| AnalyticsService | `analytics_service.py` | 101-128 | `_get_database_path()` |
| ComparisonService | `comparison_service.py` | 91-112 | Inline in `_load_scenario_data()` |
| SimulationService | `simulation_service.py` | 765-790 | Inline in `get_results()` |

**Common Pattern**:
```python
# 1. Try scenario-specific database
scenario_path = self.storage._scenario_path(workspace_id, scenario_id)
db_path = scenario_path / "simulation.duckdb"

if db_path.exists():
    return db_path

# 2. Try workspace-level database
workspace_path = self.storage._workspace_path(workspace_id)
db_path = workspace_path / "simulation.duckdb"

if db_path.exists():
    return db_path

# 3. Fall back to project default (with warning)
project_root = Path(__file__).parent.parent.parent
db_path = project_root / "dbt" / "simulation.duckdb"

if db_path.exists():
    logger.warning("Using global database...")
    return db_path

return None
```

**Decision**: Extract this pattern into `DatabasePathResolver` class.
**Rationale**: DRY principle; single point of change for fallback logic.
**Alternatives Considered**:
- Mixin class: Rejected because services don't share a common base class
- Utility function: Rejected because stateless config (isolation mode) needs to be carried

---

### 2. Path Traversal Prevention Best Practices

**Task**: Research Python path traversal prevention patterns for workspace_id and scenario_id validation.

**Findings**:

Standard validation checks for path components:
1. Reject path separators (`/`, `\`, `os.sep`)
2. Reject null bytes (`\x00`)
3. Reject relative path components (`..`, `.`)
4. Reject absolute paths (starting with `/` or drive letter)
5. Length limits (prevent buffer overflow attacks)

**Decision**: Implement validation as a private method `_validate_identifier()` that raises or returns None.
**Rationale**: Centralizes security logic; fails fast before any filesystem operations.
**Alternatives Considered**:
- Regex validation: Rejected as overly complex; simple character checks suffice
- Separate validator class: Rejected as over-engineering for 2 string inputs

**Reference Pattern**:
```python
import re

_INVALID_CHARS = re.compile(r'[/\\:\x00]|\.\.|\.$|^\.')

def _validate_identifier(self, value: str, name: str) -> bool:
    if not value or _INVALID_CHARS.search(value):
        logger.warning(f"Invalid {name}: potential path traversal attempt")
        return False
    return True
```

---

### 3. Pydantic v2 Value Object Pattern

**Task**: Research Pydantic v2 patterns for immutable value objects (ResolvedDatabasePath).

**Findings**:

Pydantic v2 uses `model_config` for immutability:
```python
from pydantic import BaseModel, ConfigDict
from pathlib import Path
from typing import Optional, Literal

class ResolvedDatabasePath(BaseModel):
    model_config = ConfigDict(frozen=True)  # Immutable

    path: Optional[Path] = None
    source: Optional[Literal["scenario", "workspace", "project"]] = None
    warning: Optional[str] = None

    @property
    def exists(self) -> bool:
        return self.path is not None
```

**Decision**: Use Pydantic v2 with `frozen=True` for `ResolvedDatabasePath`.
**Rationale**: Type safety, serialization support, immutability guarantee.
**Alternatives Considered**:
- dataclass: Rejected because project standardizes on Pydantic
- NamedTuple: Rejected because less flexible for optional fields

---

### 4. Dependency Injection Pattern for FastAPI Services

**Task**: Research how existing services receive WorkspaceStorage and apply same pattern for resolver.

**Findings**:

Current pattern in services:
```python
class AnalyticsService:
    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage
```

Services are instantiated in routers:
```python
# In routers/analytics.py
storage = WorkspaceStorage()
analytics_service = AnalyticsService(storage)
```

**Decision**: Add `db_resolver: DatabasePathResolver` as a second constructor parameter with default factory.
**Rationale**: Backward compatible; services can be instantiated without resolver (uses default).
**Alternatives Considered**:
- FastAPI Depends(): Rejected because services aren't directly injected into routes
- Global singleton: Rejected because impedes testing

**Implementation Pattern**:
```python
class AnalyticsService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)
```

---

### 5. Isolation Mode Configuration

**Task**: Research enum patterns for isolation mode configuration.

**Findings**:

Python Enum with string values for configuration:
```python
from enum import Enum

class IsolationMode(str, Enum):
    SINGLE_TENANT = "single-tenant"  # Allow project fallback
    MULTI_TENANT = "multi-tenant"    # No project fallback
```

**Decision**: Use string Enum for `IsolationMode` with `SINGLE_TENANT` as default.
**Rationale**: Human-readable in logs/configs; type-safe in code.
**Alternatives Considered**:
- Boolean `allow_project_fallback`: Rejected as less self-documenting
- String literal type: Rejected because Enum is more explicit

---

### 6. WorkspaceStorage Protocol/Interface

**Task**: Determine if WorkspaceStorage needs abstraction for testing.

**Findings**:

WorkspaceStorage has these methods used by resolver:
- `_workspace_path(workspace_id: str) -> Path`
- `_scenario_path(workspace_id: str, scenario_id: str) -> Path`

For testing, we need to mock these without real filesystem.

**Decision**: Use Protocol (typing.Protocol) to define the interface for type hints; mock the class directly in tests.
**Rationale**: Protocol provides type safety without inheritance; simpler than ABC.
**Alternatives Considered**:
- ABC base class: Rejected because WorkspaceStorage exists and shouldn't be modified
- Duck typing only: Rejected because loses type safety benefits

**Implementation**:
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class WorkspaceStorageProtocol(Protocol):
    def _workspace_path(self, workspace_id: str) -> Path: ...
    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path: ...
```

---

## Summary

All technical decisions resolved. No NEEDS CLARIFICATION items remain.

| Decision | Choice | Impact |
|----------|--------|--------|
| Code location | `planalign_api/services/database_path_resolver.py` | Single file with class + model |
| Validation | Regex-based character rejection | Security: path traversal prevention |
| Value object | Pydantic v2 frozen model | Type safety, immutability |
| DI pattern | Optional constructor parameter with default | Backward compatible |
| Isolation mode | String Enum | Self-documenting configuration |
| Storage interface | Protocol for type hints | Testability without ABC modification |
