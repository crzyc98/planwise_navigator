# Implementation Plan: Fix Vesting Analytics Endpoint AttributeError

**Branch**: `029-fix-vesting-endpoint` | **Date**: 2026-01-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/029-fix-vesting-endpoint/spec.md`

## Summary

Fix AttributeError in vesting analytics endpoint where a Pydantic `Scenario` model is incorrectly accessed using dictionary `.get()` method. The fix requires changing line 70 in `planalign_api/routers/vesting.py` from `scenario.get("name", scenario_id)` to `scenario.name or scenario_id` to properly access Pydantic model attributes.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, Pydantic v2
**Storage**: N/A (bug fix, no storage changes)
**Testing**: pytest with FastAPI TestClient
**Target Platform**: Linux server (planalign_api backend)
**Project Type**: Web application (FastAPI backend)
**Performance Goals**: N/A (bug fix)
**Constraints**: Must maintain existing API contract and error responses
**Scale/Scope**: Single file change, 1 line fix

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Bug fix does not affect event store |
| II. Modular Architecture | PASS | Change is isolated to single endpoint |
| III. Test-First Development | PASS | Existing tests will validate fix; no new tests required |
| IV. Enterprise Transparency | PASS | Error handling behavior preserved |
| V. Type-Safe Configuration | PASS | Fix improves type safety by using proper Pydantic attribute access |
| VI. Performance & Scalability | N/A | No performance impact |

**Gate Status**: PASS - All applicable principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/029-fix-vesting-endpoint/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output (minimal for this fix)
├── tasks.md             # Task list
├── checklists/
│   └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
planalign_api/
├── routers/
│   └── vesting.py       # FIX: Line 70 - Pydantic attribute access
├── models/
│   └── scenario.py      # Scenario Pydantic model (no changes needed)
└── storage/
    └── workspace_storage.py  # Returns Scenario model (no changes needed)

tests/
├── integration/
│   └── test_vesting_api.py   # Existing tests validate the fix
└── unit/
    └── test_vesting_service.py
```

**Structure Decision**: Existing structure preserved. Single-line fix in `planalign_api/routers/vesting.py`.

## Complexity Tracking

No violations - this is a minimal bug fix.

## Implementation Details

### Root Cause

In `planalign_api/routers/vesting.py:70`:
```python
# CURRENT (broken):
scenario_name = scenario.get("name", scenario_id)

# FIX:
scenario_name = scenario.name or scenario_id
```

The `workspace_storage.get_scenario()` method returns a `Scenario` Pydantic model instance (defined in `planalign_api/models/scenario.py`), not a dictionary. Pydantic models don't have a `.get()` method, causing the `AttributeError`.

### Verification

1. Existing test `test_invalid_workspace_returns_404` will pass (currently fails at line 70 before reaching workspace check)
2. Manual verification: POST to `/api/workspaces/{valid_workspace}/scenarios/{valid_scenario}/analytics/vesting` should return 200 instead of 500

### Codebase Review

Searched for similar patterns - `.get("name"` in `workspace_storage.py` operates on dictionaries (salvaged JSON data), not Pydantic models, so those are correct.
