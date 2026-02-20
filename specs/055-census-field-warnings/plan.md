# Implementation Plan: Census Field Validation Warnings

**Branch**: `055-census-field-warnings` | **Date**: 2026-02-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/055-census-field-warnings/spec.md`

## Summary

Enhance the census file upload workflow to show clear, tiered warnings when expected fields are missing. The backend gains structured warning objects with severity tiers (critical/optional) and human-readable impact descriptions. The frontend replaces the inaccurate static "Required Census Columns" info box with dynamic warning panels — amber for critical fields, blue for optional. Warnings are informational only; they do not block simulation execution.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend API), Pydantic v2 (validation/models), React 18 + Vite (frontend)
**Storage**: N/A (no database changes; warnings are computed at validation time)
**Testing**: pytest (backend), manual verification (frontend)
**Target Platform**: Linux server (API), modern browsers (frontend)
**Project Type**: Web application (backend + frontend)
**Performance Goals**: No measurable impact — adds metadata to existing validation pass
**Constraints**: Backward-compatible API response (existing `validation_warnings: List[str]` preserved)
**Scale/Scope**: 3 backend files modified, 2 frontend files modified, 1 new test file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | No event store changes |
| II. Modular Architecture | PASS | Changes contained to file service layer (service, models, router) and one frontend component. No new modules exceed 600 lines. |
| III. Test-First Development | PASS | New test file for structured warning generation. Tests cover all tiers, alias detection, edge cases. |
| IV. Enterprise Transparency | PASS | Impact descriptions provide audit-quality explanations of what's affected. |
| V. Type-Safe Configuration | PASS | Pydantic v2 `StructuredWarning` model on backend. TypeScript interface on frontend. |
| VI. Performance & Scalability | PASS | No performance impact — metadata added to existing validation pass. |

**Pre-design gate**: PASS
**Post-design gate**: PASS (no violations introduced)

## Project Structure

### Documentation (this feature)

```text
specs/055-census-field-warnings/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: research findings
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: implementation quickstart
├── contracts/
│   └── api-contracts.md # Phase 1: API request/response contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── files.py                    # Add StructuredWarning model; update response models
├── services/
│   └── file_service.py             # Add CRITICAL_COLUMNS, FIELD_IMPACT_DESCRIPTIONS; enhance warning generation
└── routers/
    └── files.py                    # Wire structured warnings through handlers

planalign_studio/
├── services/
│   └── api.ts                      # Add StructuredWarning interface; update response types
└── components/config/
    └── DataSourcesSection.tsx      # Remove static info box; add tiered warning panel

tests/api/
└── test_file_validation.py         # New: test structured warnings, tiers, impacts, aliases
```

**Structure Decision**: Web application pattern — existing backend/frontend split. All changes fit within existing file boundaries except one new test file.

## Complexity Tracking

No constitution violations — this table is intentionally empty.
