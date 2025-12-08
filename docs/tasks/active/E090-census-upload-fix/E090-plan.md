# E090: Fix Census File Upload → Simulation Integration

## Problem Statement
When users upload a census parquet file via PlanAlign Studio, the simulation does NOT use that uploaded file. Instead, it always uses the default `data/census_preprocessed.parquet`.

## Root Cause
Complete disconnect between file upload and simulation configuration:
1. Upload stores file at `workspaces/{workspace_id}/data/{filename}`
2. Simulation reads `setup.census_parquet_path` from config
3. Config never gets updated with uploaded file path
4. Falls back to default `data/census_preprocessed.parquet`

## Solution
When census file is uploaded:
1. Store file in workspace data directory
2. **Auto-update** workspace's `base_config.yaml` with `setup.census_parquet_path`
3. Resolve path to absolute before simulation
4. Add validation to ensure file exists

## Implementation Steps

### Phase 1: Core Integration
1. `file_service.py` - Return absolute path from `save_uploaded_file()`
2. `workspace_storage.py` - Add `update_base_config_key()` method
3. `files.py` router - Update workspace config after upload

### Phase 2: Path Resolution
4. `simulation_service.py` - Resolve census path, add validation, add logging

## User Decision
- **Census Scope**: Workspace-wide (uploaded file applies to all scenarios)
