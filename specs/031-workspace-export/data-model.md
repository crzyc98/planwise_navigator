# Data Model: Workspace Export and Import

**Feature Branch**: `031-workspace-export`
**Date**: 2026-01-30

## Entities

### 1. ExportManifest

The manifest file included in every workspace archive for integrity and version tracking.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| version | string | Yes | Manifest schema version (e.g., "1.0") |
| export_date | datetime | Yes | ISO 8601 timestamp when export was created |
| app_version | string | Yes | PlanAlign version that created the export |
| workspace_id | string | Yes | Original workspace UUID |
| workspace_name | string | Yes | Human-readable workspace name |
| contents | ManifestContents | Yes | Inventory of archive contents |

### 2. ManifestContents

Inventory section of the manifest for validation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| scenario_count | int | Yes | Number of scenarios included |
| scenarios | list[string] | Yes | List of scenario names |
| file_count | int | Yes | Total files in archive |
| total_size_bytes | int | Yes | Uncompressed size in bytes |
| checksum_sha256 | string | Yes | SHA256 of workspace.json for integrity |

### 3. ExportRequest (API Input)

Request model for single workspace export.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_id | string | Yes | UUID of workspace to export (from URL path) |

### 4. BulkExportRequest (API Input)

Request model for bulk export operation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_ids | list[string] | Yes | List of workspace UUIDs to export |

### 5. BulkExportStatus (API Output)

Progress tracking for bulk export operations.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| operation_id | string | Yes | Unique ID for tracking operation |
| status | enum | Yes | pending, in_progress, completed, failed |
| total | int | Yes | Total workspaces to export |
| completed | int | Yes | Number completed so far |
| current_workspace | string | No | Name of workspace currently being processed |
| results | list[ExportResult] | Yes | Results for completed exports |

### 6. ExportResult

Result for a single workspace export.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_id | string | Yes | UUID of exported workspace |
| workspace_name | string | Yes | Name of exported workspace |
| filename | string | Yes | Generated archive filename |
| size_bytes | int | Yes | Archive size in bytes |
| status | enum | Yes | success, failed |
| error | string | No | Error message if failed |

### 7. ImportValidationRequest (API Input)

Request to validate an archive before import.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | binary | Yes | Uploaded 7z archive (multipart/form-data) |

### 8. ImportValidationResponse (API Output)

Result of archive validation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| valid | bool | Yes | Whether archive is valid for import |
| manifest | ExportManifest | No | Parsed manifest if valid |
| conflict | ImportConflict | No | Conflict details if name collision |
| warnings | list[string] | Yes | Non-blocking warnings |
| errors | list[string] | Yes | Blocking errors (if invalid) |

### 9. ImportConflict

Details about a workspace name conflict.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| existing_workspace_id | string | Yes | UUID of conflicting workspace |
| existing_workspace_name | string | Yes | Name of existing workspace |
| suggested_name | string | Yes | Auto-generated alternative (e.g., "name (2)") |

### 10. ImportRequest (API Input)

Request to perform workspace import.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | binary | Yes | Uploaded 7z archive (multipart/form-data) |
| conflict_resolution | enum | No | rename, replace (required if conflict exists) |
| new_name | string | No | Custom name if conflict_resolution=rename |

### 11. ImportResponse (API Output)

Result of import operation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_id | string | Yes | UUID of imported workspace |
| name | string | Yes | Final workspace name |
| scenario_count | int | Yes | Number of scenarios imported |
| status | enum | Yes | success, partial (with warnings) |
| warnings | list[string] | Yes | Non-blocking issues encountered |

### 12. BulkImportStatus (API Output)

Progress tracking for bulk import operations.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| operation_id | string | Yes | Unique ID for tracking operation |
| status | enum | Yes | pending, in_progress, completed, failed |
| total | int | Yes | Total archives to import |
| completed | int | Yes | Number completed so far |
| current_file | string | No | Name of file currently being processed |
| results | list[ImportResponse] | Yes | Results for completed imports |

## State Transitions

### Export States
```
[Initiated] → [Compressing] → [Ready] → [Downloaded]
                    ↓
                [Failed]
```

### Import States
```
[Uploaded] → [Validating] → [Valid] → [Importing] → [Completed]
                   ↓              ↓           ↓
              [Invalid]    [Conflict] → [Resolved] → [Importing]
                                ↓
                          [Cancelled]
```

## Validation Rules

### Export Validation
- Workspace MUST exist
- Workspace MUST NOT have active simulation (check simulation status)
- User MUST have access to workspace

### Import Validation
- File size MUST NOT exceed 1GB (1,073,741,824 bytes)
- File MUST be valid 7z format
- Archive MUST contain manifest.json at root
- Manifest version MUST be compatible (≤ current version)
- Archive MUST contain workspace.json
- SHA256 checksum in manifest MUST match workspace.json

### Name Conflict Resolution
- If conflict_resolution = "rename":
  - new_name MUST be provided OR use suggested_name
  - new_name MUST be 1-100 characters
  - new_name MUST NOT conflict with existing workspaces
- If conflict_resolution = "replace":
  - Existing workspace is deleted before import
  - This is destructive and requires explicit confirmation

## Relationships

```
Workspace 1───* Scenario
    │
    └──── ExportManifest (embedded in archive)
              │
              └──── ManifestContents

BulkExportStatus 1───* ExportResult

BulkImportStatus 1───* ImportResponse
```

## Archive Structure

```
{workspace_name}_{YYYYMMDD_HHMMSS}.7z
├── manifest.json                    # ExportManifest
├── workspace.json                   # Original workspace metadata
├── base_config.yaml                 # Simulation configuration
├── comparisons/                     # Comparison results (if any)
│   └── *.json
└── scenarios/
    └── {scenario_name}/             # One directory per scenario
        ├── scenario.json            # Scenario metadata
        ├── overrides.yaml           # Config overrides
        ├── simulation.duckdb        # DuckDB results database
        └── results/                 # Exported results
            └── *.xlsx, *.csv
```

Note: Scenario directories use human-readable names instead of UUIDs for easier manual inspection. UUID mapping is preserved in scenario.json.
