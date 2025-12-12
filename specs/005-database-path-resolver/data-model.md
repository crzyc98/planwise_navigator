# Data Model: Unified Database Path Resolver

**Feature**: 005-database-path-resolver
**Date**: 2025-12-12

## Entities

### 1. ResolvedDatabasePath

**Purpose**: Immutable value object containing the resolved database path and metadata about where it was found.

**Attributes**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | `Optional[Path]` | No | Resolved filesystem path to the database, or None if not found |
| `source` | `Optional[Literal["scenario", "workspace", "project"]]` | No | Level at which the database was found |
| `warning` | `Optional[str]` | No | Warning message (e.g., when using project fallback) |

**Validation Rules**:
- If `path` is not None, `source` must also be set
- If `source` is "project", `warning` should typically be populated
- Object is immutable after creation (Pydantic `frozen=True`)

**Computed Properties**:
- `exists: bool` - True if `path` is not None

---

### 2. IsolationMode

**Purpose**: Enum defining tenant isolation behavior for the resolver.

**Values**:

| Value | String | Description |
|-------|--------|-------------|
| `SINGLE_TENANT` | `"single-tenant"` | Allow fallback to project-level database (default) |
| `MULTI_TENANT` | `"multi-tenant"` | Stop at workspace level; no project fallback |

**Validation Rules**:
- Must be one of the defined enum values
- Default is `SINGLE_TENANT` for backward compatibility

---

### 3. DatabasePathResolver

**Purpose**: Stateless service class that resolves database paths using a fallback chain.

**Constructor Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `storage` | `WorkspaceStorageProtocol` | Yes | — | Storage abstraction for path construction |
| `isolation_mode` | `IsolationMode` | No | `SINGLE_TENANT` | Tenant isolation behavior |
| `project_root` | `Optional[Path]` | No | Auto-detect | Override for project root path |
| `database_filename` | `str` | No | `"simulation.duckdb"` | Database filename to search for |

**Attributes** (immutable after construction):
- All constructor parameters stored as private attributes
- `_project_db_path: Path` - Computed project-level database path

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `resolve` | `(workspace_id: str, scenario_id: str) -> ResolvedDatabasePath` | Main resolution method |
| `_validate_identifier` | `(value: str, name: str) -> bool` | Path traversal validation |
| `_detect_project_root` | `() -> Path` | Auto-detect project root |

---

### 4. WorkspaceStorageProtocol

**Purpose**: Protocol defining the interface required from storage implementations.

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `_workspace_path` | `(workspace_id: str) -> Path` | Get workspace directory path |
| `_scenario_path` | `(workspace_id: str, scenario_id: str) -> Path` | Get scenario directory path |

**Note**: This is a Protocol (structural typing), not an ABC. The existing `WorkspaceStorage` class already implements these methods.

---

## Relationships

```
┌─────────────────────────┐
│  DatabasePathResolver   │
│  (Service Class)        │
├─────────────────────────┤
│ - storage: Protocol     │──────┐
│ - isolation_mode: Enum  │      │
│ - project_root: Path    │      │
│ - database_filename:str │      │
├─────────────────────────┤      │
│ + resolve() → Result    │      │
└────────────┬────────────┘      │
             │                   │
             │ returns           │ uses
             ▼                   ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│  ResolvedDatabasePath   │   │ WorkspaceStorageProtocol│
│  (Value Object)         │   │ (Protocol)              │
├─────────────────────────┤   ├─────────────────────────┤
│ + path: Optional[Path]  │   │ _workspace_path()       │
│ + source: Literal[...]  │   │ _scenario_path()        │
│ + warning: Optional[str]│   └─────────────────────────┘
├─────────────────────────┤              ▲
│ + exists: bool          │              │ implements
└─────────────────────────┘              │
                               ┌─────────────────────────┐
                               │    WorkspaceStorage     │
                               │    (Existing Class)     │
                               └─────────────────────────┘
```

---

## State Transitions

The resolver is stateless. `ResolvedDatabasePath` is immutable. No state transitions apply.

**Resolution Algorithm Flow**:

```
Input: (workspace_id, scenario_id)
       │
       ▼
┌──────────────────────┐
│ Validate identifiers │
│ (path traversal)     │
└──────────┬───────────┘
           │ Invalid → Return(path=None, source=None, warning="...")
           ▼
┌──────────────────────┐
│ Check scenario path  │
│ {scenario}/simulation.duckdb
└──────────┬───────────┘
           │ Exists → Return(path=..., source="scenario")
           ▼
┌──────────────────────┐
│ Check workspace path │
│ {workspace}/simulation.duckdb
└──────────┬───────────┘
           │ Exists → Return(path=..., source="workspace")
           ▼
┌──────────────────────┐
│ Check isolation mode │
└──────────┬───────────┘
           │ MULTI_TENANT → Return(path=None, source=None)
           ▼
┌──────────────────────┐
│ Check project path   │
│ {project}/dbt/simulation.duckdb
└──────────┬───────────┘
           │ Exists → Return(path=..., source="project", warning="...")
           ▼
Return(path=None, source=None)
```

---

## Data Volume Assumptions

- Number of workspaces: 1-100 (enterprise deployment)
- Number of scenarios per workspace: 1-50
- Resolver is called per API request; no caching needed
- Path existence checks are O(1) filesystem operations
