# Developer Quickstart: Workspace Export and Import

**Feature Branch**: `031-workspace-export`
**Date**: 2026-01-30

## Prerequisites

```bash
# Ensure you're on the feature branch
git checkout 031-workspace-export

# Activate virtual environment
source .venv/bin/activate

# Install new dependency (py7zr for 7z archive support)
uv pip install py7zr[all]
```

## Key Files to Modify

### Backend (Python/FastAPI)

| File | Purpose |
|------|---------|
| `planalign_api/models/export.py` | New Pydantic models for export/import |
| `planalign_api/services/export_service.py` | New service for archive operations |
| `planalign_api/routers/workspaces.py` | Add export/import endpoints |
| `planalign_api/storage/workspace_storage.py` | Add helper methods for export |

### Frontend (React/TypeScript)

| File | Purpose |
|------|---------|
| `planalign_studio/components/WorkspaceManager.tsx` | Add export/import UI |
| `planalign_studio/components/ExportProgressDialog.tsx` | New progress dialog |
| `planalign_studio/components/ImportDialog.tsx` | New import dialog |
| `planalign_studio/services/api.ts` | Add export/import API methods |

### Tests

| File | Purpose |
|------|---------|
| `tests/api/test_export_service.py` | Unit tests for export service |
| `tests/api/test_import_validation.py` | Unit tests for import validation |
| `tests/api/test_export_endpoints.py` | API endpoint tests |

## Development Workflow

### 1. Start the API Server

```bash
# Terminal 1: Run API in development mode
cd planalign_api
uvicorn main:app --reload --port 8000

# API docs available at http://localhost:8000/api/docs
```

### 2. Start the Frontend

```bash
# Terminal 2: Run frontend in development mode
cd planalign_studio
npm run dev

# Frontend available at http://localhost:5173
```

### 3. Create Test Workspace

```bash
# Use the CLI to ensure you have test data
planalign studio  # Opens browser, create a workspace with scenarios
```

### 4. Test Export (Manual)

```bash
# Export via curl
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/export \
  -o test_export.7z

# Verify archive contents
7z l test_export.7z  # List contents (requires 7-zip installed)

# Or using Python
python -c "import py7zr; print(py7zr.SevenZipFile('test_export.7z', 'r').getnames())"
```

### 5. Test Import (Manual)

```bash
# Validate archive
curl -X POST http://localhost:8000/api/workspaces/import/validate \
  -F "file=@test_export.7z"

# Import archive
curl -X POST http://localhost:8000/api/workspaces/import \
  -F "file=@test_export.7z"
```

## Running Tests

```bash
# Fast unit tests only
pytest -m fast tests/api/test_export_service.py -v

# Integration tests
pytest tests/api/test_export_endpoints.py -v

# Full test suite with coverage
pytest tests/api/test_export*.py tests/api/test_import*.py \
  --cov=planalign_api/services/export_service \
  --cov-report=html
```

## Common Development Tasks

### Adding a New Endpoint

1. Define Pydantic models in `planalign_api/models/export.py`
2. Implement service method in `planalign_api/services/export_service.py`
3. Add route in `planalign_api/routers/workspaces.py`
4. Add TypeScript types in `planalign_studio/services/api.ts`
5. Add API method in same file
6. Write tests

### Testing 7z Operations

```python
# Quick test in Python REPL
import py7zr
import tempfile
from pathlib import Path

# Create test archive
with tempfile.TemporaryDirectory() as tmpdir:
    # Create test file
    test_file = Path(tmpdir) / "test.txt"
    test_file.write_text("Hello, World!")

    # Create archive
    archive_path = Path(tmpdir) / "test.7z"
    with py7zr.SevenZipFile(archive_path, 'w') as archive:
        archive.write(test_file, "test.txt")

    # Verify archive
    with py7zr.SevenZipFile(archive_path, 'r') as archive:
        print(archive.getnames())  # ['test.txt']
```

### Debugging File Downloads

```javascript
// Frontend: Debug download response
const response = await fetch(`/api/workspaces/${workspaceId}/export`, {
  method: 'POST',
});
console.log('Content-Type:', response.headers.get('content-type'));
console.log('Content-Disposition:', response.headers.get('content-disposition'));

const blob = await response.blob();
console.log('Blob size:', blob.size);
```

## Architecture Notes

### Export Flow

```
User clicks Export
       ↓
POST /api/workspaces/{id}/export
       ↓
ExportService.export_workspace()
       ↓
1. Check for active simulations
2. Create temp directory
3. Copy workspace files
4. Generate manifest.json
5. Create 7z archive with py7zr
6. Return FileResponse
       ↓
Browser downloads file
```

### Import Flow

```
User selects file
       ↓
POST /api/workspaces/import/validate
       ↓
ExportService.validate_import()
       ↓
1. Check file size (< 1GB)
2. Verify 7z format
3. Read manifest.json
4. Check for name conflicts
5. Return validation result
       ↓
User confirms (handles conflicts)
       ↓
POST /api/workspaces/import
       ↓
ExportService.import_workspace()
       ↓
1. Extract to temp directory
2. Validate checksum
3. Generate new workspace UUID
4. Copy files to workspace storage
5. Register with WorkspaceStorage
6. Return success
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'py7zr'"

```bash
uv pip install py7zr[all]
```

### "Archive is corrupted"

Check if file was fully downloaded. 7z archives have CRC checks.

```python
import py7zr
try:
    with py7zr.SevenZipFile('archive.7z', 'r') as z:
        z.testzip()  # Returns None if OK
except Exception as e:
    print(f"Archive error: {e}")
```

### "File too large" error on import

The 1GB limit is enforced. Check file size before upload:

```python
import os
size_mb = os.path.getsize('archive.7z') / (1024 * 1024)
print(f"Archive size: {size_mb:.1f} MB")
```

### Frontend download not working

Ensure the API returns proper headers:

```python
from fastapi.responses import FileResponse

return FileResponse(
    path=archive_path,
    filename=f"{workspace_name}_{timestamp}.7z",
    media_type="application/x-7z-compressed"
)
```
