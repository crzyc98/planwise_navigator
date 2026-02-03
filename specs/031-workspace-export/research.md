# Research: Workspace Export and Import

**Feature Branch**: `031-workspace-export`
**Date**: 2026-01-30

## 1. Workspace Architecture Analysis

### Decision: Leverage existing WorkspaceStorage infrastructure
**Rationale**: The existing workspace storage system in `planalign_api/storage/workspace_storage.py` provides a clean abstraction over the filesystem. Export/import should integrate with this rather than bypassing it.

**Alternatives considered**:
- Direct filesystem operations: Rejected because it would duplicate logic already in WorkspaceStorage
- Database-only export: Rejected because workspaces include YAML configs and JSON metadata

### Current Storage Structure
```
~/.planalign/workspaces/
├── [workspace-uuid]/
│   ├── workspace.json          # Metadata (name, description, dates)
│   ├── base_config.yaml        # Simulation configuration
│   ├── comparisons/            # Comparison results
│   └── scenarios/
│       └── [scenario-uuid]/
│           ├── scenario.json   # Scenario metadata
│           ├── overrides.yaml  # Config overrides
│           ├── simulation.duckdb  # Results database
│           └── results/        # Exported results
```

## 2. 7z Library Selection

### Decision: Use py7zr library
**Rationale**: py7zr is the only actively maintained pure Python library for 7z format. It provides:
- Cross-platform compatibility (macOS, Windows, Linux)
- No external binary dependencies
- Shutil integration for familiar API
- LZMA2 compression (good ratio for databases)
- Streaming support for memory-efficient operations

**Alternatives considered**:
- pylzma: Legacy, no longer maintained, py7zr is its successor
- subprocess with 7-zip: Requires external installation, not portable
- zipfile (standard library): Does not support 7z format (user requirement)
- lzma (standard library): Raw LZMA streams only, no 7z container support

### Installation
```bash
uv pip install py7zr[all]  # Includes all compression codecs
```

### Limitations to Address
- Cannot modify existing archives (must create new)
- Performance degrades with 100k+ files (not expected for workspaces)
- Memory: 300-700 MiB recommended for compression

## 3. Export Implementation Strategy

### Decision: Stream archive to temporary file, then serve via FileResponse
**Rationale**: FastAPI's FileResponse handles large files efficiently with proper chunked streaming. Creating the archive first ensures integrity before download starts.

**Alternatives considered**:
- StreamingResponse with on-the-fly compression: More complex, harder to report accurate progress, can't verify integrity
- Background task with download link: Adds complexity for typical workspace sizes (<500MB)

### Archive Contents
```
workspace_name_YYYYMMDD_HHMMSS.7z
├── manifest.json           # Version info, contents inventory
├── workspace.json          # Workspace metadata
├── base_config.yaml        # Simulation configuration
├── comparisons/            # All comparison results
└── scenarios/
    └── [scenario-name]/    # Human-readable names instead of UUIDs
        ├── scenario.json
        ├── overrides.yaml
        ├── simulation.duckdb
        └── results/
```

### Manifest Schema
```json
{
  "version": "1.0",
  "export_date": "2026-01-30T12:00:00Z",
  "app_version": "1.0.0",
  "workspace_id": "uuid",
  "workspace_name": "My Workspace",
  "contents": {
    "scenarios": ["scenario-1", "scenario-2"],
    "files": ["workspace.json", "base_config.yaml", ...],
    "total_size_bytes": 12345678
  }
}
```

## 4. Import Implementation Strategy

### Decision: Upload file, validate manifest, then extract
**Rationale**: Validation before extraction prevents partial imports and corrupted data. The manifest provides integrity checking.

**Alternatives considered**:
- Direct extraction with rollback: More complex, requires transaction-like behavior
- Streaming extraction: Harder to validate before commit

### Validation Steps
1. Check file size (reject >1GB per clarification)
2. Verify 7z format integrity
3. Read and validate manifest.json
4. Check version compatibility
5. Detect name conflicts with existing workspaces

### Name Conflict Resolution
Options presented to user:
1. Rename workspace (auto-suggest `name (2)`)
2. Replace existing workspace (with confirmation)
3. Cancel import

## 5. API Design

### New Endpoints

```
POST /api/workspaces/{workspace_id}/export
  → Returns: FileResponse (7z archive)
  → Query params: None (name from workspace)

POST /api/workspaces/bulk-export
  → Body: { "workspace_ids": ["uuid1", "uuid2"] }
  → Returns: StreamingResponse (sequential file downloads initiated client-side)

POST /api/workspaces/import
  → Body: multipart/form-data with file
  → Returns: { workspace_id, name, status, warnings }

POST /api/workspaces/import/validate
  → Body: multipart/form-data with file
  → Returns: { valid, manifest, conflicts, warnings }
```

## 6. Frontend Integration

### Decision: Extend WorkspaceManager component
**Rationale**: Export/import are workspace management operations that belong in the existing Manage Workspaces page. Consistent with user's original request.

**UI Elements**:
- Export button on each workspace card
- "Export Selected" button when checkboxes enabled
- "Import" button in page header
- Progress dialog for bulk operations
- Conflict resolution dialog for imports

## 7. Progress Tracking

### Decision: Polling-based progress for bulk operations
**Rationale**: WebSocket already exists for simulation telemetry; export/import operations are shorter and polling is simpler.

**Alternatives considered**:
- WebSocket: Overkill for 30-second operations
- No progress: Poor UX for bulk exports

### Progress Response
```json
{
  "operation": "bulk_export",
  "total": 5,
  "completed": 2,
  "current": "workspace-name",
  "status": "in_progress"
}
```

## 8. Error Handling

### Export Errors
| Error | Response |
|-------|----------|
| Workspace not found | 404 with message |
| Active simulation | 409 Conflict with message |
| Disk full | 507 Insufficient Storage |
| Compression error | 500 with details |

### Import Errors
| Error | Response |
|-------|----------|
| File too large (>1GB) | 413 Payload Too Large |
| Invalid 7z format | 400 Bad Request |
| Missing manifest | 400 Bad Request |
| Version incompatible | 400 with warning option to proceed |
| Name conflict | 409 with options |

## 9. Testing Strategy

### Unit Tests
- Manifest generation and parsing
- Archive creation and extraction (mock filesystem)
- Name conflict detection
- Validation logic

### Integration Tests
- Full export/import round-trip
- Bulk operations
- Error scenarios (invalid file, conflicts)

### Performance Tests
- 100MB workspace export time
- 1GB file import handling
- 10-workspace bulk export

## Summary

All technical questions resolved. Ready for Phase 1 design artifacts:
- data-model.md: Manifest schema, API request/response models
- contracts/: OpenAPI spec for new endpoints
- quickstart.md: Developer setup for testing export/import
