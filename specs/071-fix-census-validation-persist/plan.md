# Implementation Plan: Fix Census Validation Warning Persistence on Re-Upload

**Branch**: `071-fix-census-validation-persist` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/071-fix-census-validation-persist/spec.md`

## Summary

When re-uploading a corrected census CSV with the same filename, the browser's file input silently suppresses the `onChange` event because the input value hasn't changed. This causes previous validation warnings to persist. The fix is to reset `fileInputRef.current.value = ''` after each upload completes, ensuring every file selection triggers fresh validation.

## Technical Context

**Language/Version**: TypeScript (React/Vite frontend)
**Primary Dependencies**: React 18, Lucide React (icons)
**Storage**: N/A — transient React component state only
**Testing**: Manual testing (no frontend test framework currently configured)
**Target Platform**: Web browser (PlanAlign Studio)
**Project Type**: Web application (frontend component fix)
**Performance Goals**: Warnings clear within 200ms of upload start
**Constraints**: Single file change, no backend modifications
**Scale/Scope**: 1 file, ~3 lines of code changed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | No event store changes |
| II. Modular Architecture | PASS | Fix is scoped to a single component |
| III. Test-First Development | PASS | Manual test plan defined; no frontend test framework exists to write automated tests |
| IV. Enterprise Transparency | N/A | No logging/audit changes |
| V. Type-Safe Configuration | N/A | No config changes |
| VI. Performance & Scalability | PASS | No performance impact |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/071-fix-census-validation-persist/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Root cause analysis
├── data-model.md        # Transient state model
├── quickstart.md        # Testing quickstart
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
planalign_studio/
└── components/
    └── config/
        └── DataSourcesSection.tsx  # ONLY file modified
```

**Structure Decision**: Single-component bug fix. No new files, no structural changes.

## Implementation Detail

### Root Cause

`DataSourcesSection.tsx` line 66-128: The `<input type="file">` element's `onChange` handler correctly clears warnings (lines 77-79), but the handler never fires when re-selecting the same filename because the browser compares the new selection against the input's current `.value` property. Since `.value` is never reset, the browser sees no change and suppresses the event.

### Fix

Add `fileInputRef.current.value = ''` in both the success and error paths of the upload handler (after lines 121 and 126 respectively). This ensures:

1. After a successful upload, re-selecting the same file triggers `onChange`
2. After a failed upload, re-selecting the same file triggers `onChange`
3. The file input is always ready to accept the next selection

### Code Change (DataSourcesSection.tsx)

**Success path** — after line 121 (`setUploadMessage(...)`) and before the closing `}` of the try block:
```typescript
// Reset file input so re-selecting the same file triggers onChange
if (fileInputRef.current) fileInputRef.current.value = '';
```

**Error path** — after line 126 (`setDataQualityWarnings([])`) and before the closing `}` of the catch block:
```typescript
// Reset file input so re-selecting the same file triggers onChange
if (fileInputRef.current) fileInputRef.current.value = '';
```

### What Does NOT Change

- Backend API (`planalign_api/routers/files.py`) — already regenerates warnings correctly
- Backend service (`planalign_api/services/file_service.py`) — validation logic is correct
- API types (`services/api.ts`) — no interface changes
- Path validation handler (lines 411-457) — uses text input, not file input; not affected

## Complexity Tracking

No violations. This is a minimal, targeted fix.
