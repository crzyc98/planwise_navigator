# Research: Fix Census Validation Warning Persistence

## Root Cause Analysis

### Decision: Bug is in frontend file input handling
**Rationale**: The HTML `<input type="file">` element does not fire `onChange` when the user re-selects the same file, because the browser compares the new value to the current value and suppresses the event if they match. The current code (`DataSourcesSection.tsx:66-128`) never resets `fileInputRef.current.value` after a successful upload, so re-selecting the same filename is silently ignored.

**Alternatives considered**:
- Backend not regenerating warnings: **Ruled out** — existing tests (`test_file_validation.py:760-775`) confirm the backend produces fresh validation on every call.
- Async race condition: **Ruled out** — not relevant to the reported reproduction steps (sequential uploads).
- React state not clearing: **Ruled out** — lines 77-79 correctly clear warnings at the start of the onChange handler. The problem is that onChange never fires for same-filename re-selection.

### Decision: Reset file input value after each upload
**Rationale**: Setting `fileInputRef.current.value = ''` after the upload completes (in both success and error paths) ensures the browser treats the next file selection as a change, even if the filename is identical.

**Alternatives considered**:
- Using a `key` prop to force re-mount the input: Works but destroys/recreates the DOM element unnecessarily. Resetting `.value` is simpler and more targeted.
- Polling for file changes: Overengineered for this use case.

### Decision: Also reset on drag-and-drop
**Rationale**: The current component uses the same file input for drag-and-drop (the `<input>` element handles both). Resetting `.value` covers both interaction modes.

## Affected Files

| File | Change |
|------|--------|
| `planalign_studio/components/config/DataSourcesSection.tsx` | Reset `fileInputRef.current.value = ''` after upload success/error |

## No Backend Changes Required

The backend (`planalign_api/routers/files.py`, `planalign_api/services/file_service.py`) correctly regenerates validation on every upload. No changes needed.
