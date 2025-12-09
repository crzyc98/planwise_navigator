# E090: Context and Key Files

**Last Updated**: 2025-01-08

## Key Files to Modify

| File | Purpose |
|------|---------|
| `planalign_api/services/file_service.py` | Returns absolute path from upload |
| `planalign_api/storage/workspace_storage.py` | Add config update method |
| `planalign_api/routers/files.py` | Update config after upload |
| `planalign_api/services/simulation_service.py` | Resolve paths, validation |

## Data Flow (Current - Broken)

```
Upload: POST /files/{workspace_id}/upload
  → FileService.save_uploaded_file()
  → Stored at: workspaces/{workspace_id}/data/{filename}
  → Returns: relative_path, metadata
  → ❌ Config NOT updated

Simulation: POST /simulations/{workspace_id}/{scenario_id}/run
  → storage.get_merged_config()
  → base_config.yaml + config_overrides
  → ❌ No census_parquet_path in either
  → Falls back to: data/census_preprocessed.parquet
```

## Data Flow (Fixed)

```
Upload: POST /files/{workspace_id}/upload
  → FileService.save_uploaded_file()
  → Returns: relative_path, metadata, absolute_path
  → ✅ storage.update_base_config_key("setup.census_parquet_path", absolute_path)
  → base_config.yaml updated

Simulation: POST /simulations/{workspace_id}/{scenario_id}/run
  → storage.get_merged_config()
  → ✅ Contains setup.census_parquet_path from uploaded file
  → Uses uploaded census file
```

## Key Code Locations

### File Upload (planalign_api/services/file_service.py:57-110)
```python
def save_uploaded_file(self, workspace_id, file_content, filename):
    # ... saves file ...
    return relative_path, metadata  # Need to also return absolute_path
```

### Config Merge (planalign_api/storage/workspace_storage.py:404-415)
```python
def get_merged_config(self, workspace_id, scenario_id):
    # Deep merge base config with overrides
    return self._deep_merge(workspace.base_config, scenario.config_overrides)
```

### dbt Variable Usage (planalign_orchestrator/config/export.py:163-174)
```python
cpp = setup.get("census_parquet_path")
if cpp:
    # Resolves to absolute path for dbt
    dbt_vars["census_parquet_path"] = str(cpp_path)
```

### dbt Model (dbt/models/staging/stg_census_data.sql:45)
```sql
FROM read_parquet('{{ var("census_parquet_path") }}')
```
