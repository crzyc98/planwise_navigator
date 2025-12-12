# Quickstart: Database Path Resolver

**Feature**: 005-database-path-resolver
**Date**: 2025-12-12

## Overview

The `DatabasePathResolver` unifies database path resolution logic across API services. It implements a fallback chain (scenario → workspace → project) with security validation and configurable isolation modes.

## Installation

No new dependencies required. Uses existing:
- Pydantic v2 (already in project)
- pathlib (stdlib)

## Basic Usage

```python
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    IsolationMode,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage

# Create storage and resolver
storage = WorkspaceStorage()
resolver = DatabasePathResolver(storage)

# Resolve a database path
result = resolver.resolve("workspace-123", "scenario-456")

if result.exists:
    import duckdb
    conn = duckdb.connect(str(result.path), read_only=True)
    # Use connection...
    conn.close()
else:
    print(f"No database found")
```

## Configuration Options

### Isolation Mode

```python
# Single-tenant (default): allows fallback to project database
resolver = DatabasePathResolver(storage, isolation_mode=IsolationMode.SINGLE_TENANT)

# Multi-tenant: stops at workspace level, no project fallback
resolver = DatabasePathResolver(storage, isolation_mode=IsolationMode.MULTI_TENANT)
```

### Custom Project Root

```python
from pathlib import Path

# Override project root for testing or custom deployments
resolver = DatabasePathResolver(
    storage,
    project_root=Path("/opt/planalign"),
)
```

## Integrating with Services

### Before (duplicated logic)

```python
class AnalyticsService:
    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def _get_database_path(self, workspace_id: str, scenario_id: str):
        # 30 lines of duplicated fallback logic...
        pass
```

### After (using resolver)

```python
from planalign_api.services.database_path_resolver import DatabasePathResolver

class AnalyticsService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def get_analytics(self, workspace_id: str, scenario_id: str):
        result = self.db_resolver.resolve(workspace_id, scenario_id)
        if not result.exists:
            return None
        # Use result.path...
```

## Working with Results

```python
result = resolver.resolve("ws1", "sc1")

# Check if database was found
if result.exists:
    print(f"Found at: {result.path}")
    print(f"Source level: {result.source}")  # "scenario", "workspace", or "project"

# Check for warnings (e.g., using shared project database)
if result.warning:
    logger.warning(result.warning)

# Handle not found
if not result.exists:
    logger.error(f"No database for workspace={workspace_id}, scenario={scenario_id}")
```

## Testing

### Unit Tests with Mocks

```python
from unittest.mock import MagicMock
from pathlib import Path
import tempfile

def test_scenario_level_resolution():
    # Create mock storage
    mock_storage = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        scenario_path = Path(tmpdir) / "scenarios" / "sc1"
        scenario_path.mkdir(parents=True)
        (scenario_path / "simulation.duckdb").touch()

        mock_storage._scenario_path.return_value = scenario_path
        mock_storage._workspace_path.return_value = Path(tmpdir)

        resolver = DatabasePathResolver(
            mock_storage,
            project_root=Path(tmpdir),
        )

        result = resolver.resolve("ws1", "sc1")

        assert result.exists
        assert result.source == "scenario"
        assert result.warning is None
```

### Testing Path Traversal Prevention

```python
def test_path_traversal_rejected():
    mock_storage = MagicMock()
    resolver = DatabasePathResolver(mock_storage)

    # These should all be rejected
    result = resolver.resolve("../etc", "passwd")
    assert not result.exists
    assert "path traversal" in result.warning.lower()

    result = resolver.resolve("workspace", "scenario/../../../etc/passwd")
    assert not result.exists
```

## Error Handling

The resolver returns `ResolvedDatabasePath` with `path=None` in these cases:

| Scenario | `source` | `warning` |
|----------|----------|-----------|
| Invalid workspace_id (path traversal) | `None` | Security warning |
| Invalid scenario_id (path traversal) | `None` | Security warning |
| No database at any level | `None` | `None` |
| Multi-tenant mode, no workspace db | `None` | `None` |

The resolver only raises exceptions for configuration errors at instantiation:
- `ValueError`: If project_root cannot be determined

## Migration Guide

1. Add resolver as optional constructor parameter (backward compatible)
2. Replace inline `_get_database_path()` calls with `self.db_resolver.resolve()`
3. Update result handling to use `ResolvedDatabasePath` properties
4. Remove old `_get_database_path()` method after migration complete
5. Run existing integration tests to verify backward compatibility
