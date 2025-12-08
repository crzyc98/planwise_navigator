# E090: Task Checklist

**Last Updated**: 2025-01-08

## Implementation Tasks

- [x] **1. Update file_service.py**
  - Return absolute path from `save_uploaded_file()`
  - File: `planalign_api/services/file_service.py`

- [x] **2. Add update_base_config_key() to workspace_storage.py**
  - Method to update specific keys in base_config.yaml
  - File: `planalign_api/storage/workspace_storage.py`

- [x] **3. Update files router**
  - Call storage method to update config after successful upload
  - File: `planalign_api/routers/files.py`

- [x] **4. Update simulation_service.py**
  - Resolve census path to absolute before simulation
  - Add pre-flight validation (file exists check)
  - Add logging for census file path
  - File: `planalign_api/services/simulation_service.py`

## Testing Tasks

- [ ] **5. Manual test: Upload different census file**
  - Upload file via UI
  - Verify base_config.yaml updated
  - Run simulation
  - Check database for correct data

## Success Criteria

- [x] Uploaded census files are used in simulations
- [x] Census file path logged during simulation start
- [x] Error message if census file not found
- [x] Existing simulations continue working with default census
